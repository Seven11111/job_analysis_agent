"""Regression tests for temporary, evidence-grounded job recommendations."""

import json
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from src.db.models import CandidateProfile, ResumeVersion
from src.data_provider.base import JobRecord

from tests.test_jobs import make_client


def _add_candidate_context(engine, *, directions=None, cities=None, resume_text="Python FastAPI"):
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory() as session:
        profile = CandidateProfile(
            target_directions=json.dumps(directions or ["后端开发"], ensure_ascii=False),
            target_cities=json.dumps(cities or ["杭州"], ensure_ascii=False),
            desired_industries=json.dumps(["互联网"], ensure_ascii=False),
            education="本科",
            days_per_week=4,
            internship_months=3,
            active=True,
        )
        session.add(profile)
        session.flush()
        session.add(
            ResumeVersion(
                profile_id=profile.id,
                title="当前在线简历",
                raw_text=resume_text,
                structured_content=json.dumps(
                    {
                        "basics": {"education": "本科"},
                        "skills": ["Python", "FastAPI"],
                    },
                    ensure_ascii=False,
                ),
                is_current=True,
            )
        )
        session.commit()


def test_recommendations_use_profile_and_current_resume_but_explicit_city_wins(tmp_path):
    client, engine = make_client(tmp_path)
    _add_candidate_context(engine, cities=["杭州"])

    response = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海"], "published_range": "all", "providers": ["fixture"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_context"]["personalized"] is True
    assert payload["recommendation_context"]["profile_used"] is True
    assert payload["recommendation_context"]["resume_used"] is True
    assert payload["items"][0]["title"] == "Python 后端开发实习生"
    recommendation = payload["items"][0]["recommendation"]
    assert recommendation["score"] is not None
    assert any("后端开发" in point for point in recommendation["matched_points"])
    assert any("本次指定城市" in point for point in recommendation["matched_points"])
    assert not any("与已填写目标城市未匹配" in point for point in recommendation["missing_points"])
    assert any("简历与岗位内容均提及" in point for point in recommendation["matched_points"])


def test_recommendation_marks_resume_gap_as_unverified_and_unknown_fields_explicitly(tmp_path, monkeypatch):
    from api.v1.endpoints import jobs as job_endpoints

    client, engine = make_client(tmp_path)
    _add_candidate_context(engine, directions=["后端开发"], cities=["上海"], resume_text="Python")

    class SparseProvider:
        def search(self, *, keyword=None, city=None):
            return [
                JobRecord(
                    source_job_id="sparse-1",
                    title="后端开发实习生",
                    company_name="示例企业",
                    city="上海",
                    detail_url="https://example.com/jobs/sparse-1",
                    published_date=date.today(),
                    description="参与后端 API 开发。",
                    requirements="熟悉 Python 和 SQL。",
                )
            ]

    monkeypatch.setitem(job_endpoints.service.providers, "fixture", SparseProvider())

    response = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海"], "published_range": "all", "providers": ["fixture"]},
    )

    backend = response.json()["items"][0]
    recommendation = backend["recommendation"]
    assert any("未检索到对应证据" in point for point in recommendation["missing_points"])
    assert any("岗位未说明学历要求" in point for point in recommendation["unknown_points"])
    assert any("岗位未说明每周到岗天数" in point for point in recommendation["unknown_points"])


def test_explicit_keyword_suppresses_conflicting_long_term_direction_sort(tmp_path):
    client, engine = make_client(tmp_path)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory() as session:
        session.add(
            CandidateProfile(
                target_directions=json.dumps(["后端开发"], ensure_ascii=False),
                target_cities="[]",
                desired_industries="[]",
                active=True,
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/jobs/search",
        json={"keyword": "开发", "cities": ["上海"], "published_range": "all", "providers": ["fixture"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_context"]["personalized"] is False
    assert payload["items"][0]["recommendation"]["score"] is None
    assert all(
        not any("目标岗位方向" in point for point in item["recommendation"]["missing_points"])
        for item in payload["items"]
    )


def test_feedback_is_temporary_reversible_and_does_not_save_job_or_change_profile(tmp_path):
    client, engine = make_client(tmp_path)
    search = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海"], "published_range": "all", "providers": ["fixture"]},
    ).json()
    token = search["items"][0]["result_token"]
    assert search["recommendation_context"]["personalized"] is False
    assert search["items"][0]["recommendation"]["score"] is None

    marked = client.put(f"/api/v1/jobs/search-results/{token}/feedback", json={"feedback": "interested"})
    assert marked.status_code == 200
    assert marked.json()["feedback"] == "interested"
    detail = client.get(f"/api/v1/jobs/search-results/{token}")
    assert detail.json()["recommendation"]["feedback"] == "interested"

    # Explicit feedback affects only this cached recommendation run: liked jobs
    # are promoted and disliked jobs are demoted while moving across pages.
    client.put(f"/api/v1/jobs/search-results/{token}/feedback", json={"feedback": "not_interested"})
    page_two = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海"], "published_range": "all", "providers": ["fixture"], "limit": 1, "page": 2},
    ).json()
    assert page_two["items"][0]["result_token"] == token

    undone = client.put(f"/api/v1/jobs/search-results/{token}/feedback", json={"feedback": None})
    assert undone.status_code == 200
    assert undone.json()["feedback"] is None
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM candidate_profiles").scalar_one() == 0


def test_feedback_for_expired_or_unknown_result_returns_404(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.put(
        "/api/v1/jobs/search-results/expired-result/feedback",
        json={"feedback": "not_interested"},
    )
    assert response.status_code == 404


def test_feedback_does_not_change_newest_sort_order(tmp_path):
    client, _ = make_client(tmp_path)
    search = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海"], "published_range": "all", "providers": ["fixture"], "sort_by": "newest", "limit": 1},
    ).json()
    first_result = search["items"][0]
    assert first_result["title"] == "AI 应用开发实习生"

    feedback = client.put(
        f"/api/v1/jobs/search-results/{first_result['result_token']}/feedback",
        json={"feedback": "interested"},
    )
    assert feedback.status_code == 200
    assert "切换到智能推荐排序时" in feedback.json()["message"]

    second_page = client.post(
        "/api/v1/jobs/search",
        json={"cities": ["上海"], "published_range": "all", "providers": ["fixture"], "sort_by": "newest", "limit": 1, "page": 2},
    ).json()
    assert second_page["items"][0]["title"] == "Python 后端开发实习生"
