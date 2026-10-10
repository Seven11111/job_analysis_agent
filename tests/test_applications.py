from test_jobs import make_client


def seed_job(client):
    response = client.post("/api/v1/jobs/search", json={"published_range": "all"})
    assert response.status_code == 200
    token = response.json()["items"][0]["result_token"]
    saved = client.post(f"/api/v1/jobs/search-results/{token}/save")
    assert saved.status_code == 200
    return saved.json()["id"]


def test_save_job_and_change_status_keeps_timeline(tmp_path):
    client, _ = make_client(tmp_path)
    job_id = seed_job(client)

    statuses = client.get("/api/v1/applications/status-definitions")
    assert statuses.status_code == 200
    assert len(statuses.json()) == 6
    applied_status = next(item for item in statuses.json() if item["name"] == "已投递")

    saved = client.post(
        "/api/v1/applications",
        json={"job_id": job_id, "note": "先准备简历"},
    )
    assert saved.status_code == 200
    application_id = saved.json()["id"]
    assert saved.json()["current_status"]["name"] == "已保存"

    duplicate = client.post("/api/v1/applications", json={"job_id": job_id})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "already_exists"

    changed = client.post(
        f"/api/v1/applications/{application_id}/status",
        json={
            "to_status_id": applied_status["id"],
            "effective_at": "2099-09-22T09:00:00+08:00",
            "note": "已经投递官网申请",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["application"]["current_status"]["name"] == "已投递"
    assert changed.json()["status_event"]["from_status"]["name"] == "已保存"

    listing = client.get("/api/v1/applications?tab=all")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["note"] == "已经投递官网申请"
    assert client.get("/api/v1/applications?tab=pending_analysis").json()["total"] == 1
    assert client.get("/api/v1/applications?tab=analyzed").json()["total"] == 0

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    filtered = client.get(
        "/api/v1/applications",
        params={"q": job["title"][:5], "city": job["city"], "status_id": applied_status["id"]},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert client.get("/api/v1/applications", params={"q": "这不是岗位关键词"}).json()["total"] == 0
    assert client.get("/api/v1/applications", params={"city": "不存在的城市"}).json()["total"] == 0

    timeline = client.get(f"/api/v1/applications/{application_id}/timeline")
    assert timeline.status_code == 200
    assert [item["to_status"]["name"] for item in timeline.json()] == ["已投递", "已保存"]


def test_custom_status_can_be_created_and_disabled(tmp_path):
    client, _ = make_client(tmp_path)
    created = client.post(
        "/api/v1/applications/status-definitions",
        json={"name": "等待回复", "color": "orange", "sort_order": 25},
    )
    assert created.status_code == 200
    status_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/applications/status-definitions/{status_id}",
        json={"name": "HR 沟通中", "color": "violet", "sort_order": 15},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "HR 沟通中"
    assert updated.json()["color"] == "violet"
    assert updated.json()["sort_order"] == 15

    disabled = client.delete(f"/api/v1/applications/status-definitions/{status_id}")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False


def test_historical_status_event_can_be_edited_and_transition_chain_rebuilt(tmp_path):
    client, _ = make_client(tmp_path)
    job_id = seed_job(client)
    statuses = client.get("/api/v1/applications/status-definitions").json()
    applied_status = next(item for item in statuses if item["name"] == "已投递")
    renamed_status = client.post(
        "/api/v1/applications/status-definitions",
        json={"name": "简历已筛选", "color": "teal", "sort_order": 25},
    ).json()
    saved = client.post("/api/v1/applications", json={"job_id": job_id})
    application_id = saved.json()["id"]
    client.post(
        f"/api/v1/applications/{application_id}/status",
        json={"to_status_id": applied_status["id"], "effective_at": "2026-09-22T09:00:00+08:00"},
    )
    timeline = client.get(f"/api/v1/applications/{application_id}/timeline").json()
    original_save_event = next(item for item in timeline if item["to_status"]["name"] == "已保存")

    updated = client.patch(
        f"/api/v1/applications/{application_id}/timeline/{original_save_event['id']}",
        json={
            "to_status_id": renamed_status["id"],
            "effective_at": "2026-09-20T12:30:00+08:00",
            "note": "更正历史进度",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status_event"]["to_status"]["name"] == "简历已筛选"
    assert updated.json()["status_event"]["effective_at"].startswith("2026-09-20T04:30:00")
    assert updated.json()["application"]["current_status"]["name"] == "已投递"

    refreshed = client.get(f"/api/v1/applications/{application_id}/timeline").json()
    applied_event = next(item for item in refreshed if item["to_status"]["name"] == "已投递")
    assert applied_event["from_status"]["name"] == "简历已筛选"


def test_removing_application_preserves_shared_job_and_snapshots(tmp_path):
    client, engine = make_client(tmp_path)
    job_id = seed_job(client)
    application = client.post("/api/v1/applications", json={"job_id": job_id}).json()

    removed = client.delete(f"/api/v1/applications/{application['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/applications/{application['id']}").status_code == 404
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM applications").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM application_status_events").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_snapshots").scalar_one() == 1
