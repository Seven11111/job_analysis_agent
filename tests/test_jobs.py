from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.app import create_app
from api.deps import db_session
from src.config import Settings
from src.db.base import Base
from src.schemas.report import MatchReport


def make_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

    def override_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[db_session] = override_db
    return TestClient(app), engine


def test_fixture_search_keeps_results_ephemeral_until_explicit_save(tmp_path):
    client, engine = make_client(tmp_path)

    response = client.post(
        "/api/v1/jobs/search",
        json={"city": "上海", "published_range": "3d", "internship_type": "实习生"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {item["title"] for item in payload["items"]} == {"Python 后端开发实习生", "AI 应用开发实习生"}
    assert payload["quality"]["undisclosed_salary_count"] == 1
    assert payload["quality"]["providers"] == [{"provider": "fixture", "status": "success", "count": 2, "error": None}]

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
    token = payload["items"][0]["result_token"]
    saved = client.post(f"/api/v1/jobs/search-results/{token}/save")
    assert saved.status_code == 200
    assert saved.json()["id"] is not None
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_snapshots").scalar_one() == 1


def test_salary_filter_and_detail_endpoint(tmp_path):
    client, _ = make_client(tmp_path)
    client.post("/api/v1/jobs/search", json={"published_range": "all"})

    response = client.post(
        "/api/v1/jobs/search",
        json={"salary_mode": "disclosed_only", "published_range": "all"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2

    token = response.json()["items"][0]["result_token"]
    detail = client.get(f"/api/v1/jobs/search-results/{token}")
    assert detail.status_code == 200
    assert detail.json()["description"]
    assert detail.json()["snapshot_fetched_at"] is None
    saved = client.post(f"/api/v1/jobs/search-results/{token}/save")
    assert saved.status_code == 200
    persisted = client.get(f"/api/v1/jobs/{saved.json()['id']}")
    assert persisted.status_code == 200
    assert persisted.json()["snapshot_fetched_at"]


def test_search_accepts_multiple_cities(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海", "杭州"], "published_range": "all", "providers": ["fixture"]},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert {item["city"] for item in response.json()["items"]} == {"上海", "杭州"}


def test_search_can_filter_company_separately_from_role_keyword(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post("/api/v1/jobs/search", json={
        "keyword": "后端",
        "company": "示例科技",
        "cities": ["上海"],
        "published_range": "all",
        "providers": ["fixture"],
    })

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["company_name"] == "示例科技"
    assert response.json()["items"][0]["title"] == "Python 后端开发实习生"


def test_saved_job_can_be_analyzed_and_read_back(tmp_path, monkeypatch):
    from api.v1.endpoints import matches as match_endpoints

    client, engine = make_client(tmp_path)
    search = client.post("/api/v1/jobs/search", json={"published_range": "all"}).json()
    saved = client.post(f"/api/v1/jobs/search-results/{search['items'][0]['result_token']}/save")
    assert saved.status_code == 200

    class FakeMatchAdapter:
        def generate_structured(self, *, prompt, response_type):
            assert "分析上下文：" in prompt
            assert "rule_based_precheck" in prompt
            return response_type(
                summary="候选人具备相关后端项目经历，建议核对岗位到岗要求。",
                match_score=78,
                recommendation="match",
                matched_points=["简历项目与岗位方向相关"],
                missing_points=["简历未说明每周到岗天数"],
                risk_points=["岗位薪资信息未公开"],
                next_actions=["查看来源页面确认岗位仍在招聘"],
            )

    monkeypatch.setattr(match_endpoints.service, "llm_adapter", FakeMatchAdapter())
    monkeypatch.setattr(match_endpoints.service, "settings", Settings(litellm_model="test/mock-model"))
    analyzed = client.post(f"/api/v1/jobs/{saved.json()['id']}/matches", json={})
    assert analyzed.status_code == 200
    assert analyzed.json()["analysis_mode"] == "test/mock-model"
    assert analyzed.json()["match_score"] == 78
    assert analyzed.json()["recommendation"] == "match"

    history = client.get(f"/api/v1/jobs/{saved.json()['id']}/matches")
    assert history.status_code == 200
    assert len(history.json()) == 1
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_matches").scalar_one() == 1


def test_model_failure_does_not_persist_a_successful_match(tmp_path, monkeypatch):
    from api.v1.endpoints import matches as match_endpoints
    from src.llm.adapter import LLMGenerationError

    client, engine = make_client(tmp_path)
    search = client.post("/api/v1/jobs/search", json={"published_range": "all"}).json()
    saved = client.post(f"/api/v1/jobs/search-results/{search['items'][0]['result_token']}/save")

    class BrokenMatchAdapter:
        def generate_structured(self, *, prompt, response_type):
            raise LLMGenerationError("mock timeout")

    monkeypatch.setattr(match_endpoints.service, "llm_adapter", BrokenMatchAdapter())
    monkeypatch.setattr(match_endpoints.service, "settings", Settings(litellm_model="test/mock-model"))
    response = client.post(f"/api/v1/jobs/{saved.json()['id']}/matches", json={})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "generation_failed"
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_matches").scalar_one() == 0


def test_missing_model_configuration_returns_clear_service_error(tmp_path, monkeypatch):
    from api.v1.endpoints import matches as match_endpoints
    from src.llm.litellm_adapter import LiteLLMAdapter

    client, _ = make_client(tmp_path)
    search = client.post("/api/v1/jobs/search", json={"published_range": "all"}).json()
    saved = client.post(f"/api/v1/jobs/search-results/{search['items'][0]['result_token']}/save")
    settings = Settings(litellm_model="")
    monkeypatch.setattr(match_endpoints.service, "settings", settings)
    monkeypatch.setattr(match_endpoints.service, "llm_adapter", LiteLLMAdapter(settings))

    response = client.post(f"/api/v1/jobs/{saved.json()['id']}/matches", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_not_configured"


def test_resume_contact_details_are_masked_before_llm_prompt(tmp_path, monkeypatch):
    from api.v1.endpoints import matches as match_endpoints

    client, _ = make_client(tmp_path)
    search = client.post("/api/v1/jobs/search", json={"published_range": "all"}).json()
    saved = client.post(f"/api/v1/jobs/search-results/{search['items'][0]['result_token']}/save")
    resume_text = "姓名：张三\nPython 后端项目。电话 13800138000，邮箱 peng@example.com。"
    created_resume = client.post(
        "/api/v1/profile/resumes",
        json={
            "title": "测试简历",
            "raw_text": resume_text,
            "structured_content": {"projects": [{"name": "岗位 Agent", "description": "FastAPI 项目"}]},
            "set_current": True,
        },
    )
    assert created_resume.status_code == 200
    observed: dict[str, str] = {}

    class InspectingMatchAdapter:
        def generate_structured(self, *, prompt, response_type):
            observed["prompt"] = prompt
            return response_type(
                summary="简历具备相关项目证据。", match_score=70, recommendation="match",
                matched_points=["有 Python 项目"], missing_points=[], risk_points=[], next_actions=[],
            )

    monkeypatch.setattr(match_endpoints.service, "llm_adapter", InspectingMatchAdapter())
    monkeypatch.setattr(match_endpoints.service, "settings", Settings(litellm_model="test/mock-model"))
    response = client.post(f"/api/v1/jobs/{saved.json()['id']}/matches", json={})

    assert response.status_code == 200
    assert "13800138000" not in observed["prompt"]
    assert "peng@example.com" not in observed["prompt"]
    assert "张三" not in observed["prompt"]
    assert "[手机号已脱敏]" in observed["prompt"]
    assert "[邮箱已脱敏]" in observed["prompt"]
    assert "岗位 Agent" in observed["prompt"]


def test_invalid_minimum_salary_is_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post("/api/v1/jobs/search", json={"salary_min": 200})
    assert response.status_code == 422


def test_unknown_provider_returns_quality_error(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post("/api/v1/jobs/search", json={"providers": ["not-configured"]})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "provider_unavailable"


def test_job_link_preview_reports_missing_llm_configuration(tmp_path, monkeypatch):
    from api.v1.endpoints import jobs as job_endpoints
    from src.llm.adapter import LLMNotConfiguredError

    client, _ = make_client(tmp_path)

    def missing_model(_):
        raise LLMNotConfiguredError("模型未配置")

    monkeypatch.setattr(job_endpoints.service, "preview_import", missing_model)
    response = client.post("/api/v1/jobs/import/preview", json={"detail_url": "https://jobs.example.com/1"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_not_configured"


def test_job_link_preview_reports_model_generation_failure(tmp_path, monkeypatch):
    from api.v1.endpoints import jobs as job_endpoints
    from src.llm.adapter import LLMGenerationError

    client, _ = make_client(tmp_path)

    def failed_model(_):
        raise LLMGenerationError("mock failure")

    monkeypatch.setattr(job_endpoints.service, "preview_import", failed_model)
    response = client.post("/api/v1/jobs/import/preview", json={"detail_url": "https://jobs.example.com/1"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "generation_failed"
