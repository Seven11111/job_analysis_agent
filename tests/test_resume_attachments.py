from io import BytesIO

from docx import Document

from src.schemas.resume import ResumeStructuredContent
from src.services import profile_service as profile_service_module
from src.services.resume_parser import ResumeParserService

from test_jobs import make_client


def make_docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def parsed_resume() -> ResumeStructuredContent:
    return ResumeStructuredContent.model_validate(
        {
            "basics": {"school": "某大学", "major": "计算机科学", "education": "本科", "graduation_year": 2027},
            "education": [{"school": "某大学", "degree": "本科", "major": "计算机科学", "start_date": "2023", "end_date": "2027", "description": ""}],
            "experience": [],
            "projects": [{"name": "求职 Agent", "role": "后端开发", "technologies": ["Python", "FastAPI"]}],
            "skills": ["Python", "FastAPI"],
            "certificates": [],
            "summary": "计算机专业学生。",
        }
    )


def test_upload_parse_review_confirm_and_delete_attachment(tmp_path, monkeypatch):
    from api.v1.endpoints import profile as profile_endpoints

    monkeypatch.setattr(profile_service_module, "ATTACHMENT_DIRECTORY", tmp_path / "resume_attachments")
    client, engine = make_client(tmp_path)

    class FakeResumeParser:
        def parse(self, text):
            assert "13800138000" in text  # raw extracted text stays local; masking happens inside ResumeParserService
            return parsed_resume()

    monkeypatch.setattr(profile_endpoints.service, "resume_parser", FakeResumeParser())
    source = "某大学计算机科学本科。项目：求职 Agent。电话 13800138000，邮箱 peng@example.com。"
    uploaded = client.post(
        "/api/v1/profile/resume-attachments/parse",
        data={"consent_to_model": "true"},
        files={"file": ("backend-resume.docx", make_docx(source), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert uploaded.status_code == 200, uploaded.text
    attachment = uploaded.json()
    assert attachment["parse_status"] == "pending_review"
    assert attachment["draft_content"]["projects"][0]["name"] == "求职 Agent"
    assert attachment["linked_resume_version_id"] is None
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM resume_versions").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM resume_attachments").scalar_one() == 1

    confirmed = client.post(
        f"/api/v1/profile/resume-attachments/{attachment['id']}/confirm",
        json={"title": "后端实习简历", "structured_content": attachment["draft_content"], "set_current": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    resume = confirmed.json()
    assert resume["is_current"] is True
    assert resume["source_attachment_id"] == attachment["id"]

    detail = client.get(f"/api/v1/profile/resumes/{resume['id']}")
    assert detail.status_code == 200
    assert detail.json()["structured_content"]["basics"]["school"] == "某大学"
    assert "13800138000" in detail.json()["raw_text"]  # original file text stays local for the user

    attachment_list = client.get("/api/v1/profile/resume-attachments").json()
    assert attachment_list[0]["parse_status"] == "confirmed"
    assert attachment_list[0]["draft_content"] is None
    assert attachment_list[0]["linked_resume_version_id"] == resume["id"]
    downloaded = client.get(f"/api/v1/profile/resume-attachments/{attachment['id']}/file")
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"PK")

    stored_file = next((tmp_path / "resume_attachments").glob("*.docx"))
    assert stored_file.is_file()
    deleted = client.delete(f"/api/v1/profile/resume-attachments/{attachment['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": attachment["id"], "deleted": True}
    assert not stored_file.exists()
    assert client.get(f"/api/v1/profile/resumes/{resume['id']}").json()["source_attachment_id"] is None
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM resume_versions").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM resume_attachments").scalar_one() == 0


def test_resume_upload_requires_explicit_model_consent(tmp_path, monkeypatch):
    from api.v1.endpoints import profile as profile_endpoints

    monkeypatch.setattr(profile_service_module, "ATTACHMENT_DIRECTORY", tmp_path / "resume_attachments")
    client, engine = make_client(tmp_path)

    class NeverCalledParser:
        def parse(self, _text):
            raise AssertionError("parser must not run without consent")

    monkeypatch.setattr(profile_endpoints.service, "resume_parser", NeverCalledParser())
    response = client.post(
        "/api/v1/profile/resume-attachments/parse",
        data={"consent_to_model": "false"},
        files={"file": ("resume.docx", make_docx("Python FastAPI"), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "consent_required"
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM resume_attachments").scalar_one() == 0


def test_resume_upload_rejects_unsupported_or_unreadable_file(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post(
        "/api/v1/profile/resume-attachments/parse",
        data={"consent_to_model": "true"},
        files={"file": ("resume.jpg", b"not a supported resume", "image/jpeg")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_resume_file"


def test_confirm_resume_rejects_blank_title(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post(
        "/api/v1/profile/resume-attachments/1/confirm",
        json={"title": "   ", "structured_content": parsed_resume().model_dump()},
    )

    assert response.status_code == 422


def test_resume_parser_masks_sensitive_text_before_model(tmp_path):
    observed = {}

    class InspectingAdapter:
        def generate_structured(self, *, prompt, response_type):
            observed["prompt"] = prompt
            return response_type()

    parser = ResumeParserService(llm_adapter=InspectingAdapter())
    parsed = parser.parse("姓名：张三\n电话 13800138000，邮箱 peng@example.com，身份证 11010519491231002X。技能 Python。")

    assert "13800138000" not in observed["prompt"]
    assert "peng@example.com" not in observed["prompt"]
    assert "张三" not in observed["prompt"]
    assert "11010519491231002X" not in observed["prompt"]
    assert "[手机号已脱敏]" in observed["prompt"]
    assert "[邮箱已脱敏]" in observed["prompt"]
    assert parsed.basics.full_name == "张三"
    assert parsed.basics.phone == "13800138000"
    assert parsed.basics.email == "peng@example.com"


def test_resume_parser_masks_sensitive_values_returned_by_model():
    class AdapterWithSensitiveOutput:
        def generate_structured(self, *, prompt, response_type):
            return response_type(summary="电话 13800138000，邮箱 peng@example.com")

    parsed = ResumeParserService(llm_adapter=AdapterWithSensitiveOutput()).parse("技能 Python")

    assert "13800138000" not in parsed.summary
    assert "peng@example.com" not in parsed.summary
    assert "[手机号已脱敏]" in parsed.summary
    assert "[邮箱已脱敏]" in parsed.summary


def test_resume_parse_model_failure_does_not_persist_attachment(tmp_path, monkeypatch):
    from api.v1.endpoints import profile as profile_endpoints
    from src.llm.adapter import LLMGenerationError

    monkeypatch.setattr(profile_service_module, "ATTACHMENT_DIRECTORY", tmp_path / "resume_attachments")
    client, engine = make_client(tmp_path)

    class BrokenResumeParser:
        def parse(self, _text):
            raise LLMGenerationError("mock model failure")

    monkeypatch.setattr(profile_endpoints.service, "resume_parser", BrokenResumeParser())
    response = client.post(
        "/api/v1/profile/resume-attachments/parse",
        data={"consent_to_model": "true"},
        files={"file": ("resume.docx", make_docx("Python FastAPI"), "application/octet-stream")},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "generation_failed"
    assert not (tmp_path / "resume_attachments").exists()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM resume_attachments").scalar_one() == 0
