from fastapi.testclient import TestClient

from api.app import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["providers"]["fixture"] == "available"


def test_health_recognizes_project_local_job_pro_command(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.v1.endpoints.health.resolve_job_pro_cli",
        lambda command: "/project/.tools/job-pro/node_modules/.bin/job-pro",
    )
    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["providers"]["job_pro"] == "available"
