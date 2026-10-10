import json

from test_jobs import make_client
from src.config import Settings
from src.db.models import AgentRunEvent
from src.services.job_service import JobSearchService
from api.v1.endpoints import agent as agent_endpoints
from sqlalchemy.orm import Session


def text_chunks(text):
    return [
        {"choices": [{"delta": {"content": text[index:index + 12]}, "finish_reason": None}]}
        for index in range(0, len(text), 12)
    ] + [{"choices": [{"delta": {}, "finish_reason": "stop"}]}]


def tool_chunks(name, arguments, call_id="call_1"):
    encoded = json.dumps(arguments, ensure_ascii=False)
    return [
        {
            "choices": [{
                "delta": {"tool_calls": [{
                    "index": 0,
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": encoded},
                }]},
                "finish_reason": "tool_calls",
            }]
        }
    ]


class ScriptedAgentAdapter:
    def __init__(self, first, final="已根据当前数据完成查询。", inspect=None):
        self.first = first
        self.final = final
        self.inspect = inspect
        self.calls = 0

    def stream_chat(self, *, messages, tools):
        self.calls += 1
        if self.inspect:
            self.inspect(messages, tools)
        if self.calls > 1:
            return iter(text_chunks(self.final))
        return iter(self.first)


def decode_sse(text):
    decoded = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name = next((line.removeprefix("event: ") for line in block.splitlines() if line.startswith("event: ")), None)
        data_line = next((line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")), None)
        if event_name and data_line:
            decoded.append((event_name, json.loads(data_line)))
    return decoded


def start_stream_until_action(engine, message):
    db = Session(engine)
    stream = agent_endpoints.service.stream(db, message=message)
    events = []
    while True:
        try:
            chunk = next(stream)
        except StopIteration as exc:
            db.close()
            raise AssertionError("Agent did not produce an action proposal") from exc
        decoded = decode_sse(chunk)
        events.extend(decoded)
        proposal = next((payload for name, payload in decoded if name == "action_proposed"), None)
        if proposal is not None:
            return db, stream, events, proposal


def finish_stream(stream):
    events = []
    for chunk in stream:
        events.extend(decode_sse(chunk))
    return events


def setup_agent(*, adapter=None):
    from src.services.agent_service import AgentService

    agent_endpoints.service = AgentService(settings=Settings(litellm_model="test/mock"))
    agent_endpoints.service.job_service = JobSearchService(settings=Settings(job_provider="fixture"))
    if adapter is not None:
        agent_endpoints.service.llm_adapter = adapter


def test_agent_persists_messages_and_can_resume_a_renamed_session(tmp_path):
    observed = []
    adapter = ScriptedAgentAdapter(
        first=text_chunks("你好，我可以帮你搜索和管理实习岗位。"),
        final="第二轮仍在同一个会话中。",
        inspect=lambda messages, tools: observed.append(messages),
    )
    setup_agent(adapter=adapter)
    client, _ = make_client(tmp_path)

    first_response = client.post("/api/v1/agent/chat/stream", json={"message": "你好"})
    first_events = decode_sse(first_response.text)
    run_started = next(payload for name, payload in first_events if name == "run_started")
    session_id = run_started["payload"]["session_id"]
    run_id = run_started["run_id"]
    assert first_response.status_code == 200
    assert any(name == "assistant_completed" for name, _ in first_events)

    renamed = client.patch(f"/api/v1/agent/sessions/{session_id}", json={"title": "求职规划"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "求职规划"

    second_response = client.post(
        "/api/v1/agent/chat/stream",
        json={"session_id": session_id, "message": "那我还可以做什么？"},
    )
    assert second_response.status_code == 200
    detail = client.get(f"/api/v1/agent/sessions/{session_id}")
    assert detail.status_code == 200
    assert [item["role"] for item in detail.json()["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail.json()["messages"][-1]["content"] == "第二轮仍在同一个会话中。"
    assert any(message["content"] == "你好" for message in observed[-1])
    assert len(client.get("/api/v1/agent/sessions").json()) == 1
    stopped = client.post(f"/api/v1/agent/sessions/{session_id}/runs/{run_id}/cancel")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "already_finished"


def test_agent_streams_early_deltas_and_cancel_persists_partial_answer(tmp_path):
    setup_agent(adapter=ScriptedAgentAdapter(first=text_chunks("这是一次实时生成的部分回答，停止后这段内容也应该保存。")))
    client, engine = make_client(tmp_path)
    db = Session(engine)
    stream = agent_endpoints.service.stream(db, message="请给我一些求职建议")

    started = decode_sse(next(stream))[0][1]
    session_id = started["payload"]["session_id"]
    run_id = started["run_id"]
    first_delta = decode_sse(next(stream))[0]

    assert first_delta[0] == "assistant_delta"
    assert first_delta[1]["payload"]["text"]
    assert len(first_delta[1]["payload"]["text"]) < len("这是一次实时生成的部分回答，停止后这段内容也应该保存。")

    cancellation = agent_endpoints.service.cancel_run(db, session_id=session_id, run_id=run_id)
    assert cancellation["status"] == "cancellation_requested"
    cancelled = decode_sse(next(stream))[0]
    assert cancelled[0] == "run_cancelled"
    stream.close()

    detail = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assistant_message = next(item for item in detail["messages"] if item["role"] == "assistant")
    assert assistant_message["structured_content"]["interrupted"] is True
    assert assistant_message["content"] == first_delta[1]["payload"]["text"]
    assert detail["events"][-1]["event_type"] == "run_cancelled"
    db.close()


def test_agent_uses_native_tool_call_to_query_saved_jobs(tmp_path):
    observed = []
    adapter = ScriptedAgentAdapter(
        first=tool_chunks("list_saved_jobs", {"limit": 5}),
        inspect=lambda messages, tools: observed.append((messages, tools)),
    )
    setup_agent(adapter=adapter)
    client, _ = make_client(tmp_path)

    response = client.post("/api/v1/agent/chat/stream", json={"message": "我收藏了哪些岗位？"})

    events = decode_sse(response.text)
    tool_completed = [payload for name, payload in events if name == "tool_completed"]
    assert response.status_code == 200
    assert tool_completed[0]["payload"]["tool"] == "list_saved_jobs"
    assert tool_completed[0]["payload"]["result"]["count"] == 0
    assert any(tool["function"]["name"] == "list_saved_jobs" for tool in observed[0][1])
    assert client.get("/api/v1/agent/tools").status_code == 200


def test_agent_previews_link_then_waits_for_confirmation_before_saving(tmp_path):
    from datetime import date

    from src.data_provider.base import JobRecord

    url = "https://careers.example.com/jobs/backend-intern"

    class FakeImporter:
        def fetch(self, detail_url):
            assert detail_url == url
            return JobRecord(
                source_job_id="job-link-1",
                title="后端开发实习生",
                company_name="示例科技",
                city="杭州",
                detail_url=url,
                published_date=date(2026, 10, 1),
                job_type="日常实习",
                salary_status="unknown",
                description="参与服务端功能开发。",
                requirements="熟悉 Python 或 Go。",
                extraction_method="json_ld",
            )

    class PreviewThenSaveAdapter:
        def __init__(self):
            self.calls = 0

        def stream_chat(self, *, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return iter(tool_chunks("preview_job_link", {"detail_url": url}))
            if self.calls == 2:
                tool_result = next(item["content"] for item in reversed(messages) if item["role"] == "tool")
                preview = json.loads(tool_result)
                return iter(tool_chunks("propose_save_job", {
                    "result_token": preview["preview_token"],
                    "overrides": {"title": "后端开发实习生（已校对）", "city": "上海"},
                }))
            return iter(text_chunks("岗位已完成解析；用户确认后保存。"))

    adapter = PreviewThenSaveAdapter()
    setup_agent(adapter=adapter)
    client, engine = make_client(tmp_path)
    agent_endpoints.service.job_service.import_provider = FakeImporter()

    tools = client.get("/api/v1/agent/tools").json()
    assert any(item["name"] == "preview_job_link" for item in tools)

    db, stream, streamed_events, proposal = start_stream_until_action(
        engine,
        f"请解析并收藏这个岗位链接，先展示确认：{url}",
    )
    preview_event = next(
        payload for name, payload in streamed_events
        if name == "tool_completed" and payload.get("name") == "preview_job_link"
    )
    preview = preview_event["payload"]["result"]
    assert preview["job"]["title"] == "后端开发实习生"
    assert preview["job"]["detail_url"] == url
    assert preview["warnings"]
    assert proposal["payload"]["data"]["result_token"] == preview["preview_token"]
    assert proposal["payload"]["data"]["overrides"] == {"title": "后端开发实习生（已校对）", "city": "上海"}
    assert proposal["status"] == "pending"

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM applications").scalar_one() == 0

    confirmed = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": True})
    completed_events = finish_stream(stream)
    db.close()

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "succeeded"
    assert any(name == "assistant_completed" for name, _ in completed_events)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_snapshots").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM applications").scalar_one() == 1
        saved_job = connection.exec_driver_sql("SELECT title, city FROM jobs").one()
        assert tuple(saved_job) == ("后端开发实习生（已校对）", "上海")


def test_agent_compares_only_saved_jobs_in_the_current_profile(tmp_path):
    setup_agent(adapter=ScriptedAgentAdapter(first=tool_chunks("compare_saved_jobs", {"application_ids": [1, 2]})))
    client, _ = make_client(tmp_path)
    search = client.post("/api/v1/jobs/search", json={"published_range": "all", "limit": 5})
    assert search.status_code == 200
    result_items = search.json()["items"]
    assert len(result_items) >= 2

    application_ids = []
    for item in result_items[:2]:
        saved_job = client.post(f"/api/v1/jobs/search-results/{item['result_token']}/save")
        assert saved_job.status_code == 200
        application = client.post("/api/v1/applications", json={"job_id": saved_job.json()["id"]})
        assert application.status_code == 200
        application_ids.append(application.json()["id"])

    agent_endpoints.service.llm_adapter = ScriptedAgentAdapter(
        first=tool_chunks("compare_saved_jobs", {"application_ids": application_ids}),
    )
    response = client.post("/api/v1/agent/chat/stream", json={"message": "对比我保存的两个岗位"})
    events = decode_sse(response.text)
    completed = next(payload["payload"] for name, payload in events if name == "tool_completed")

    assert response.status_code == 200
    assert completed["tool"] == "compare_saved_jobs"
    assert len(completed["result"]["items"]) == 2
    assert {item["application_id"] for item in completed["result"]["items"]} == set(application_ids)


def test_agent_searches_real_provider_adapter_without_saving_results(tmp_path):
    adapter = ScriptedAgentAdapter(
        first=tool_chunks("search_jobs", {
            "keyword": "后端",
            "company": "示例科技",
            "cities": ["上海"],
            "published_range": "all",
            "providers": ["fixture"],
            "limit": 5,
        }),
        final="我找到了岗位，可以先查看来源链接；搜索结果尚未收藏。",
    )
    setup_agent(adapter=adapter)
    client, engine = make_client(tmp_path)

    response = client.post("/api/v1/agent/chat/stream", json={"message": "帮我找上海后端实习"})
    events = decode_sse(response.text)
    completed_tool = next(payload["payload"] for name, payload in events if name == "tool_completed")
    assert "result" in completed_tool, completed_tool
    result = completed_tool["result"]

    assert response.status_code == 200
    assert result["total"] > 0
    assert result["filters"]["company"] == "示例科技"
    assert all(item["company"] == "示例科技" for item in result["items"])
    assert all(item["url"].startswith("https://") for item in result["items"])
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0


def test_agent_can_narrow_search_to_an_explicitly_requested_selected_provider(tmp_path):
    from src.data_provider.base import JobRecord

    observed = []

    class BossProvider:
        def search(self, *, keyword=None, city=None):
            observed.append((keyword, city))
            return [JobRecord(
                source_job_id="boss-agent-selected-1",
                title="Agent 开发实习生",
                company_name="示例科技",
                city=city or "上海",
                detail_url="https://www.zhipin.com/job_detail/boss-agent-selected-1.html",
                published_date=None,
            )]

    setup_agent(adapter=ScriptedAgentAdapter(
        first=tool_chunks("search_jobs", {
            "keyword": "Agent 开发",
            "cities": ["上海"],
            "providers": ["boss_agent_cli"],
            "published_range": "all",
            "limit": 5,
        }),
    ))
    agent_endpoints.service.job_service = JobSearchService(
        providers={"boss_agent_cli": BossProvider()},
        settings=Settings(job_provider="fixture"),
    )
    client, engine = make_client(tmp_path)

    response = client.post(
        "/api/v1/agent/chat/stream",
        json={"message": "只搜 BOSS 直聘里上海的 Agent 开发实习", "search_providers": ["boss_agent_cli", "job_pro"]},
    )
    events = decode_sse(response.text)
    completed_event = next(payload for name, payload in events if name == "tool_completed")
    completed = completed_event["payload"]

    assert response.status_code == 200
    assert completed_event["status"] == "succeeded"
    assert observed == [("Agent 开发", "上海")]
    assert completed["result"]["quality"]["providers"] == [
        {"provider": "boss_agent_cli", "status": "success", "count": 1, "error": None}
    ]
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0


def test_agent_refuses_a_requested_provider_not_selected_on_job_search_page(tmp_path):
    calls = []

    class BossProvider:
        def search(self, *, keyword=None, city=None):
            calls.append((keyword, city))
            return []

    setup_agent(adapter=ScriptedAgentAdapter(
        first=tool_chunks("search_jobs", {"keyword": "Agent", "providers": ["boss_agent_cli"]}),
    ))
    agent_endpoints.service.job_service = JobSearchService(
        providers={"boss_agent_cli": BossProvider()},
        settings=Settings(job_provider="fixture"),
    )
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/v1/agent/chat/stream",
        json={"message": "只搜 BOSS 的 Agent 实习", "search_providers": ["job_pro"]},
    )
    events = decode_sse(response.text)
    failed_event = next(payload for name, payload in events if name == "tool_completed")

    assert response.status_code == 200
    assert failed_event["status"] == "failed"
    assert "先在岗位搜索页勾选该来源" in failed_event["payload"]["summary"]
    assert calls == []


def test_agent_does_not_fall_back_to_fixture_when_no_source_is_selected(tmp_path):
    calls = []

    class FixtureSpy:
        def search(self, *, keyword=None, city=None):
            calls.append((keyword, city))
            return []

    setup_agent(adapter=ScriptedAgentAdapter(
        first=tool_chunks("search_jobs", {"keyword": "Agent", "providers": ["fixture"]}),
    ))
    agent_endpoints.service.job_service = JobSearchService(
        providers={"fixture": FixtureSpy()},
        settings=Settings(job_provider="fixture"),
    )
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/v1/agent/chat/stream",
        json={"message": "搜索 Agent 实习", "search_providers": []},
    )
    events = decode_sse(response.text)
    failed_event = next(payload for name, payload in events if name == "tool_completed")

    assert response.status_code == 200
    assert failed_event["status"] == "failed"
    assert "先到岗位搜索页至少选择一个岗位来源" in failed_event["payload"]["summary"]
    assert calls == []


def test_agent_separates_company_keyword_and_city_for_job_pro(tmp_path):
    from src.data_provider.base import JobRecord

    observed = []

    class CompanyProvider:
        def search(self, *, keyword=None, city=None, company=None):
            observed.append((keyword, city, company))
            return [JobRecord(
                source_job_id="xiaohongshu-agent-1",
                title="Agent开发实习生",
                company_name="小红书",
                city="上海",
                detail_url="https://job.xiaohongshu.com/position/xhs-agent-1",
                published_date=None,
                raw_payload={"work_cities": "上海、杭州"},
            )]

    setup_agent(adapter=ScriptedAgentAdapter(
        first=tool_chunks("search_jobs", {
            "keyword": "Agent 开发",
            "company": "小红书",
            "cities": ["杭州"],
            "published_range": "all",
            "limit": 5,
        }),
    ))
    agent_endpoints.service.job_service = JobSearchService(
        providers={"job_pro": CompanyProvider()},
        settings=Settings(job_provider="fixture"),
    )
    client, _ = make_client(tmp_path)

    response = client.post("/api/v1/agent/chat/stream", json={"message": "找小红书在杭州的 Agent 开发实习"})
    events = decode_sse(response.text)
    result = next(payload["payload"]["result"] for name, payload in events if name == "tool_completed")

    assert response.status_code == 200
    assert observed == [("Agent 开发", None, "小红书")]
    assert result["filters"] == {"company": "小红书", "keyword": "Agent 开发", "cities": ["杭州"]}
    assert result["items"][0]["company"] == "小红书"
    assert result["items"][0]["city"] == "杭州"


def test_agent_application_change_waits_for_explicit_confirmation(tmp_path):
    from test_applications import seed_job

    adapter = ScriptedAgentAdapter(
        first=tool_chunks("propose_application_update", {"application_id": 1, "status_name": "已投递"}),
        final="我已经生成修改卡片，请确认后才会更新。",
    )
    setup_agent(adapter=adapter)
    client, engine = make_client(tmp_path)
    job_id = seed_job(client)
    saved = client.post("/api/v1/applications", json={"job_id": job_id})
    assert saved.status_code == 200
    application_id = saved.json()["id"]
    # The seeded application is the first one in this fresh test database.
    assert application_id == 1

    db, stream, events, proposal = start_stream_until_action(engine, "请把这个岗位状态改成已投递")
    assert proposal["status"] == "pending"
    assert agent_endpoints.service.llm_adapter.calls == 1
    assert client.get(f"/api/v1/applications/{application_id}").json()["current_status"]["name"] == "已保存"

    confirmed = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": True})
    completed_events = finish_stream(stream)
    db.close()
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "succeeded"
    assert any(name == "assistant_completed" for name, _ in completed_events)
    assert agent_endpoints.service.llm_adapter.calls == 2
    assert client.get(f"/api/v1/applications/{application_id}").json()["current_status"]["name"] == "已投递"
    duplicate_confirm = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": True})
    assert duplicate_confirm.status_code == 409


def test_agent_preserves_pending_actions_and_blocks_follow_up_until_resolved(tmp_path):
    setup_agent(adapter=ScriptedAgentAdapter(
        first=tool_chunks("propose_profile_update", {"major": "软件工程"}),
        final="画像修改已准备好，请确认后生效。",
    ))
    client, engine = make_client(tmp_path)

    db, stream, streamed_events, proposal = start_stream_until_action(engine, "把我的专业改成软件工程")
    session_id = next(payload["payload"]["session_id"] for name, payload in streamed_events if name == "run_started")

    with Session(engine) as db:
        db.add_all([
            AgentRunEvent(
                session_id=session_id,
                run_id=f"older-history-{index}",
                sequence=1,
                event_type="tool_completed",
                name="fixture_event",
                status="succeeded",
            )
            for index in range(205)
        ])
        db.commit()

    detail = client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert len(detail["events"]) == 201
    assert any(event["id"] == proposal["id"] and event["status"] == "pending" for event in detail["events"])

    blocked = client.post(
        "/api/v1/agent/chat/stream",
        json={"session_id": session_id, "message": "继续聊聊"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "pending_action_confirmation"
    assert blocked.json()["detail"]["pending_action_ids"] == [proposal["id"]]
    assert len(client.get(f"/api/v1/agent/sessions/{session_id}").json()["messages"]) == 1

    rejected = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": False})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    still_running = client.post(
        "/api/v1/agent/chat/stream",
        json={"session_id": session_id, "message": "继续聊聊"},
    )
    assert still_running.status_code == 409
    assert still_running.json()["detail"]["code"] == "run_in_progress"
    assert any(name == "tool_completed" for name, _ in finish_stream(stream))
    db.close()

    agent_endpoints.service.llm_adapter = ScriptedAgentAdapter(first=text_chunks("操作已处理，我们可以继续。"))
    resumed = client.post(
        "/api/v1/agent/chat/stream",
        json={"session_id": session_id, "message": "继续聊聊"},
    )
    assert resumed.status_code == 200


def test_agent_profile_update_waits_for_confirmation_and_only_patches_requested_fields(tmp_path):
    adapter = ScriptedAgentAdapter(
        first=tool_chunks("propose_profile_update", {"major": "软件工程", "target_cities": ["上海", "杭州"]}),
    )
    setup_agent(adapter=adapter)
    client, engine = make_client(tmp_path)
    client.put("/api/v1/profile", json={"school": "某大学", "major": "计算机", "target_cities": ["上海"]})

    db, stream, _, proposal = start_stream_until_action(engine, "把我的专业改成软件工程，并增加杭州意向")
    before = client.get("/api/v1/profile").json()
    assert before["major"] == "计算机"
    assert before["target_cities"] == ["上海"]

    confirmed = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": True})
    completed_events = finish_stream(stream)
    db.close()
    after = client.get("/api/v1/profile").json()
    assert confirmed.status_code == 200
    assert any(name == "assistant_completed" for name, _ in completed_events)
    assert after["school"] == "某大学"
    assert after["major"] == "软件工程"
    assert after["target_cities"] == ["上海", "杭州"]


def test_agent_resume_update_creates_new_version_and_keeps_private_basics_local(tmp_path):
    adapter = ScriptedAgentAdapter(
        first=tool_chunks("propose_resume_update", {
            "changes": {"skills": ["Python", "FastAPI", "PostgreSQL"]},
        }),
    )
    setup_agent(adapter=adapter)
    client, engine = make_client(tmp_path)
    created = client.post("/api/v1/profile/resumes", json={
        "title": "后端实习简历",
        "raw_text": "张三，电话 13800138000，邮箱 test@example.com。熟悉 Python。",
        "structured_content": {
            "basics": {"full_name": "张三", "phone": "13800138000", "email": "test@example.com", "school": "某大学"},
            "skills": ["Python"],
        },
        "set_current": True,
    })
    assert created.status_code == 200

    db, stream, _, proposal = start_stream_until_action(engine, "把我的简历技能补充 FastAPI 和 PostgreSQL")
    assert "13800138000" not in json.dumps(proposal, ensure_ascii=False)

    confirmed = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": True})
    completed_events = finish_stream(stream)
    db.close()
    resumes = client.get("/api/v1/profile/resumes").json()
    current = next(item for item in resumes if item["is_current"])
    detail = client.get(f"/api/v1/profile/resumes/{current['id']}").json()
    assert confirmed.status_code == 200
    assert any(name == "assistant_completed" for name, _ in completed_events)
    assert current["id"] != created.json()["id"]
    assert detail["structured_content"]["basics"]["full_name"] == "张三"
    assert detail["structured_content"]["basics"]["phone"] == "13800138000"
    assert detail["structured_content"]["skills"] == ["Python", "FastAPI", "PostgreSQL"]


def test_agent_remove_saved_job_requires_confirmation_and_preserves_job_source_data(tmp_path):
    from test_applications import seed_job

    setup_agent(adapter=ScriptedAgentAdapter(
        first=tool_chunks("propose_remove_saved_job", {"application_id": 1}),
    ))
    client, engine = make_client(tmp_path)
    job_id = seed_job(client)
    saved = client.post("/api/v1/applications", json={"job_id": job_id}).json()

    db, stream, _, proposal = start_stream_until_action(engine, "把这个岗位从岗位管理移除")
    assert client.get(f"/api/v1/applications/{saved['id']}").status_code == 200

    confirmed = client.post(f"/api/v1/agent/actions/{proposal['id']}/resolve", json={"confirm": True})
    completed_events = finish_stream(stream)
    db.close()
    assert confirmed.status_code == 200
    assert any(name == "assistant_completed" for name, _ in completed_events)
    assert client.get(f"/api/v1/applications/{saved['id']}").status_code == 404
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_snapshots").scalar_one() == 1


def test_agent_masks_sensitive_user_text_before_sending_to_model(tmp_path):
    captured = {}

    def inspect(messages, _tools):
        captured["messages"] = messages

    setup_agent(adapter=ScriptedAgentAdapter(first=text_chunks("已收到。"), inspect=inspect))
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/v1/agent/chat/stream",
        json={"message": "请记住我的电话 13800138000，顺便介绍下 Agent 能做什么"},
    )

    assert response.status_code == 200
    sent = json.dumps(captured["messages"], ensure_ascii=False)
    assert "13800138000" not in sent
    assert "[手机号已脱敏]" in sent
    session_id = next(payload["payload"]["session_id"] for name, payload in decode_sse(response.text) if name == "run_started")
    local_history = client.get(f"/api/v1/agent/sessions/{session_id}").json()["messages"]
    assert "13800138000" in local_history[0]["content"]


def test_agent_masks_sensitive_data_returned_from_local_tools_before_model_use(tmp_path):
    from test_applications import seed_job

    captured = []
    adapter = ScriptedAgentAdapter(
        first=tool_chunks("get_saved_job_detail", {"application_id": 1}),
        inspect=lambda messages, _tools: captured.append(messages),
    )
    setup_agent(adapter=adapter)
    client, _ = make_client(tmp_path)
    job_id = seed_job(client)
    client.post("/api/v1/applications", json={"job_id": job_id, "note": "备用电话 13800138000"})

    first_response = client.post("/api/v1/agent/chat/stream", json={"message": "查看这个岗位的详情"})
    assert first_response.status_code == 200
    assert len(captured) >= 2
    assert "13800138000" not in json.dumps(captured[1], ensure_ascii=False)
    assert "[手机号已脱敏]" in json.dumps(captured[1], ensure_ascii=False)

    session_id = next(payload["payload"]["session_id"] for name, payload in decode_sse(first_response.text) if name == "run_started")
    follow_up_capture = {}
    agent_endpoints.service.llm_adapter = ScriptedAgentAdapter(
        first=text_chunks("好的。"),
        inspect=lambda messages, _tools: follow_up_capture.setdefault("messages", messages),
    )
    second_response = client.post("/api/v1/agent/chat/stream", json={"session_id": session_id, "message": "继续聊聊"})

    assert second_response.status_code == 200
    assert "13800138000" not in json.dumps(follow_up_capture["messages"], ensure_ascii=False)
