from datetime import datetime, timedelta, timezone

from test_applications import seed_job
from test_jobs import make_client


def test_workbench_overview_uses_real_application_and_status_event_data(tmp_path):
    client, _ = make_client(tmp_path)
    empty = client.get("/api/v1/workbench/overview")
    assert empty.status_code == 200
    assert empty.json()["application_count"] == 0
    assert empty.json()["todo_open_count"] == 0
    assert len(empty.json()["status_counts"]) == 6
    assert all(status["count"] == 0 for status in empty.json()["status_counts"])

    job_id = seed_job(client)
    saved = client.post("/api/v1/applications", json={"job_id": job_id}).json()
    changed_status = next(
        item for item in client.get("/api/v1/applications/status-definitions").json()
        if item["name"] == "已投递"
    )
    changed = client.post(
        f"/api/v1/applications/{saved['id']}/status",
        json={"to_status_id": changed_status["id"], "effective_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
    )
    assert changed.status_code == 200

    overview = client.get("/api/v1/workbench/overview").json()
    assert overview["application_count"] == 1
    counts = {item["name"]: item["count"] for item in overview["status_counts"]}
    assert counts["已投递"] == 1
    assert sum(item["count"] for item in overview["weekly_status_events"]) == 2


def test_todo_lifecycle_and_overview_counts(tmp_path):
    client, _ = make_client(tmp_path)
    job_id = seed_job(client)
    saved = client.post("/api/v1/applications", json={"job_id": job_id}).json()

    created = client.post("/api/v1/workbench/todos", json={
        "title": "准备岗位面试",
        "application_id": saved["id"],
        "due_at": "2020-01-01T12:00:00+08:00",
        "priority": "high",
        "note": "复习项目设计",
    })
    assert created.status_code == 201
    todo = created.json()
    assert todo["application"]["job_id"] == job_id
    assert datetime.fromisoformat(todo["due_at"].replace("Z", "+00:00")).utcoffset() == timedelta(0)
    assert client.get("/api/v1/workbench/overview").json()["todo_overdue_count"] == 1

    completed = client.patch(f"/api/v1/workbench/todos/{todo['id']}", json={"completed": True})
    assert completed.status_code == 200
    assert completed.json()["completed"] is True
    assert completed.json()["completed_at"] is not None
    overview = client.get("/api/v1/workbench/overview").json()
    assert overview["todo_open_count"] == 0
    assert overview["todo_completed_count"] == 1
    assert overview["todo_overdue_count"] == 0

    updated = client.patch(f"/api/v1/workbench/todos/{todo['id']}", json={"due_at": None, "note": None})
    assert updated.status_code == 200
    assert updated.json()["due_at"] is None
    assert updated.json()["note"] is None
    assert client.get("/api/v1/workbench/todos?status=completed").json()["total"] == 1

    removed = client.delete(f"/api/v1/workbench/todos/{todo['id']}")
    assert removed.status_code == 204
    assert client.get("/api/v1/workbench/todos?status=all").json()["total"] == 0


def test_interview_calendar_crud_and_application_unlink(tmp_path):
    client, _ = make_client(tmp_path)
    job_id = seed_job(client)
    application = client.post("/api/v1/applications", json={"job_id": job_id}).json()
    future = datetime.now(timezone.utc) + timedelta(days=2)
    start_at = future.isoformat(timespec="seconds")
    end_at = (future + timedelta(hours=1)).isoformat(timespec="seconds")

    created = client.post("/api/v1/workbench/interviews", json={
        "title": "技术一面",
        "application_id": application["id"],
        "starts_at": start_at,
        "ends_at": end_at,
        "interview_format": "online",
        "meeting_url": "https://example.com/meeting",
    })
    assert created.status_code == 201
    interview = created.json()
    assert interview["company_name"]
    assert interview["position_title"]
    assert interview["application"]["id"] == application["id"]
    assert datetime.fromisoformat(interview["starts_at"].replace("Z", "+00:00")).utcoffset() == timedelta(0)
    assert client.get("/api/v1/workbench/overview").json()["interview_next_7_days_count"] == 1

    calendar = client.get(
        "/api/v1/workbench/interviews",
        params={"start_at": (future - timedelta(hours=1)).isoformat(), "end_at": (future + timedelta(days=1)).isoformat()},
    )
    assert calendar.status_code == 200
    assert calendar.json()["total"] == 1

    invalid = client.patch(f"/api/v1/workbench/interviews/{interview['id']}", json={"ends_at": "2020-01-01T00:00:00+00:00"})
    assert invalid.status_code == 422

    updated = client.patch(f"/api/v1/workbench/interviews/{interview['id']}", json={"note": "准备项目介绍"})
    assert updated.status_code == 200
    assert updated.json()["note"] == "准备项目介绍"

    client.post("/api/v1/workbench/todos", json={"title": "准备面试", "application_id": application["id"]})
    removed_application = client.delete(f"/api/v1/applications/{application['id']}")
    assert removed_application.status_code == 204
    listed = client.get("/api/v1/workbench/interviews").json()
    assert listed["total"] == 1
    assert listed["items"][0]["application"] is None
    todos = client.get("/api/v1/workbench/todos?status=all").json()
    assert todos["items"][0]["application"] is None

    removed = client.delete(f"/api/v1/workbench/interviews/{interview['id']}")
    assert removed.status_code == 204
    assert client.get("/api/v1/workbench/interviews").json()["total"] == 0


def test_workbench_validates_timezone_and_profile_owned_application(tmp_path):
    client, _ = make_client(tmp_path)
    missing_application = client.post("/api/v1/workbench/todos", json={"title": "Invalid link", "application_id": 999})
    assert missing_application.status_code == 404
    missing_timezone = client.post("/api/v1/workbench/interviews", json={
        "title": "面试", "starts_at": "2026-10-20T10:00:00",
    })
    assert missing_timezone.status_code == 422


def test_weekly_status_events_follow_beijing_calendar_boundary(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path)
    job_id = seed_job(client)
    application = client.post("/api/v1/applications", json={"job_id": job_id}).json()
    initial_event = client.get(f"/api/v1/applications/{application['id']}/timeline").json()[0]
    updated_initial = client.patch(
        f"/api/v1/applications/{application['id']}/timeline/{initial_event['id']}",
        json={"effective_at": "2026-10-01T00:00:00+00:00"},
    )
    assert updated_initial.status_code == 200

    statuses = client.get("/api/v1/applications/status-definitions").json()
    next_status = next(item for item in statuses if item["id"] != application["current_status"]["id"])
    changed = client.post(
        f"/api/v1/applications/{application['id']}/status",
        json={"to_status_id": next_status["id"], "effective_at": "2026-10-11T16:30:00+00:00"},
    )
    assert changed.status_code == 200
    monkeypatch.setattr(
        "src.services.workbench_service.utc_now_naive",
        lambda: datetime(2026, 10, 12, 1, 0),
    )

    weeks = client.get("/api/v1/workbench/overview").json()["weekly_status_events"]
    current_beijing_week = next(item for item in weeks if item["week_start"] == "2026-10-12")
    assert current_beijing_week["count"] == 1
