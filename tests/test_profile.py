from test_jobs import make_client


def test_profile_update_and_confirmable_facts(tmp_path):
    client, _ = make_client(tmp_path)

    initial = client.get("/api/v1/profile")
    assert initial.status_code == 200
    assert initial.json()["target_directions"] == []

    updated = client.put(
        "/api/v1/profile",
        json={
            "school": "某大学",
            "major": "计算机科学",
            "target_directions": ["后端", "AI 应用"],
            "target_cities": ["上海"],
            "days_per_week": 4,
            "internship_months": 3,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["target_directions"] == ["后端", "AI 应用"]

    temporary = client.post(
        "/api/v1/profile/facts",
        json={"fact_type": "skill", "fact_key": "python", "fact_value": "熟悉 Python", "confirmed": False},
    )
    assert temporary.status_code == 200
    fact_id = temporary.json()["id"]
    assert temporary.json()["status"] == "temporary"
    assert client.get("/api/v1/profile/facts").json() == []
    assert len(client.get("/api/v1/profile/facts?status=temporary").json()) == 1

    confirmed = client.post("/api/v1/profile/confirm", json={"fact_ids": [fact_id]})
    assert confirmed.status_code == 200
    assert confirmed.json()[0]["status"] == "active"
    assert len(client.get("/api/v1/profile/facts").json()) == 1

    deleted = client.delete(f"/api/v1/profile/facts/{fact_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert client.get("/api/v1/profile/facts").json() == []


def test_resume_versions_and_sensitive_preview(tmp_path):
    client, _ = make_client(tmp_path)
    first = client.post(
        "/api/v1/profile/resumes",
        json={
            "title": "后端实习版",
            "raw_text": "Python FastAPI，电话 13812345678，邮箱 test@example.com",
        },
    )
    assert first.status_code == 200
    assert first.json()["is_current"] is True
    assert "13812345678" not in first.json()["text_preview"]
    assert "test@example.com" not in first.json()["text_preview"]

    second = client.post(
        "/api/v1/profile/resumes",
        json={"title": "通用版", "raw_text": "SQL 和 React 项目经历", "set_current": False},
    )
    assert second.status_code == 200
    assert second.json()["is_current"] is False

    selected = client.post(f"/api/v1/profile/resumes/{second.json()['id']}/select")
    assert selected.status_code == 200
    assert selected.json()["is_current"] is True
    resumes = client.get("/api/v1/profile/resumes").json()
    assert sum(resume["is_current"] for resume in resumes) == 1


def test_online_resume_structured_sections_round_trip(tmp_path):
    client, _ = make_client(tmp_path)
    created = client.post(
        "/api/v1/profile/resumes",
        json={
            "title": "结构化简历",
            "raw_text": "张同学，后端实习求职",
            "structured_content": {
                "basics": {"full_name": "张同学", "city": "上海", "school": "某大学"},
                "job_intent": {"target_positions": ["后端开发实习生"], "target_cities": ["上海"], "days_per_week": 4},
                "campus_experiences": [{"organization": "学生技术社团", "role": "负责人", "achievements": ["组织技术分享"]}],
            },
        },
    )

    assert created.status_code == 200, created.text
    detail = client.get(f"/api/v1/profile/resumes/{created.json()['id']}")

    assert detail.status_code == 200
    structured = detail.json()["structured_content"]
    assert structured["basics"]["full_name"] == "张同学"
    assert structured["job_intent"]["target_positions"] == ["后端开发实习生"]
    assert structured["campus_experiences"][0]["organization"] == "学生技术社团"
    assert structured["education"] == []
