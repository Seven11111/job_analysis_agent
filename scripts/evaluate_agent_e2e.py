#!/usr/bin/env python3
"""Run real-model Agent E2E checks against an isolated temporary database.

The benchmark sends synthetic profile/job data to the configured LiteLLM model.
One case also performs a read-only job-pro search. It never uses or alters the
user's application database and never prints API credentials or full answers.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.app import create_app  # noqa: E402
from api.deps import db_session  # noqa: E402
from api.v1.endpoints import agent as agent_endpoints  # noqa: E402
from api.v1.endpoints import jobs as job_endpoints  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.db import models  # noqa: F401,E402
from src.db.base import Base  # noqa: E402
from src.services.agent_service import AgentService  # noqa: E402
from src.services.job_service import JobSearchService  # noqa: E402


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return round(ordered[index], 1)


def parse_event(event_name: str | None, data: list[str]) -> tuple[str, dict[str, Any]] | None:
    if not event_name or not data:
        return None
    try:
        payload = json.loads("\n".join(data))
    except json.JSONDecodeError:
        return None
    return event_name, payload if isinstance(payload, dict) else {}


def seed_eval_data(client: httpx.Client) -> None:
    profile = client.put(
        "/api/v1/profile",
        json={
            "school": "评测大学",
            "major": "计算机科学与技术",
            "education": "本科",
            "graduation_year": 2027,
            "target_directions": ["Python 后端开发", "Agent 开发"],
            "target_cities": ["上海", "杭州"],
            "available_period": "2026 年冬季学期后",
            "days_per_week": 4,
            "internship_months": 3,
            "desired_industries": ["人工智能", "互联网"],
        },
    )
    profile.raise_for_status()

    resume = client.post(
        "/api/v1/profile/resumes",
        json={
            "title": "E2E 合成简历",
            "raw_text": "合成评测简历：使用 Python、FastAPI、SQLAlchemy 完成岗位研究 Agent 项目。",
            "set_current": True,
            "structured_content": {
                "basics": {"school": "评测大学", "major": "计算机科学与技术", "education": "本科"},
                "skills": ["Python", "FastAPI", "SQLAlchemy", "LiteLLM"],
                "projects": [{
                    "name": "岗位研究 Agent",
                    "role": "个人项目",
                    "description": "基于 Tool Calling 搜索和管理实习岗位。",
                    "highlights": ["通过 SSE 流式返回工具与回答事件"],
                    "technologies": ["Python", "FastAPI", "LiteLLM", "SQLite"],
                }],
            },
        },
    )
    resume.raise_for_status()

    # Seed two saved records outside the Shanghai/Python search used by the
    # confirmation scenario, so that the latter can safely add one new record.
    for city in ("杭州", "北京"):
        search = client.post(
            "/api/v1/jobs/search",
            json={"cities": [city], "published_range": "all", "providers": ["fixture"], "limit": 10},
        )
        search.raise_for_status()
        items = search.json().get("items", [])
        if not items:
            raise RuntimeError(f"fixture seed returned no job for city {city}")
        saved = client.post(f"/api/v1/jobs/search-results/{items[0]['result_token']}/save")
        saved.raise_for_status()
        application = client.post("/api/v1/applications", json={"job_id": saved.json()["id"]})
        application.raise_for_status()

    subscription = client.post("/api/v1/subscriptions", json={
        "name": "评测岗位订阅",
        "filters": {
            "keyword": "Agent",
            "cities": ["杭州"],
            "published_range": "all",
            "salary_mode": "any",
            "providers": ["job_pro"],
        },
        "frequency": "daily",
        "schedule_time": "09:30",
    })
    subscription.raise_for_status()


def make_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "general_chat",
            "prompt": "你好，请用两句话介绍你能帮我做什么。",
            "expected_tools": [],
            "validator": "answer",
        },
        {
            "id": "saved_job_list",
            "prompt": "查询我已收藏的岗位，并列出岗位名称、公司和城市。",
            "expected_tools": ["list_saved_jobs"],
            "validator": "saved_jobs",
        },
        {
            "id": "application_status",
            "prompt": "我目前跟踪了多少个岗位？按投递状态统计一下。",
            "expected_tools": ["get_application_status"],
            "validator": "status",
        },
        {
            "id": "compare_saved_jobs",
            "prompt": "请对比我已经保存的两个岗位，列出岗位名称和工作城市。",
            "expected_tools": ["list_saved_jobs", "compare_saved_jobs"],
            "validator": "comparison",
        },
        {
            "id": "candidate_profile",
            "prompt": "读取我的求职画像，告诉我学校、求职方向和意向城市。",
            "expected_tools": ["get_candidate_profile"],
            "validator": "profile",
        },
        {
            "id": "current_resume",
            "prompt": "读取当前在线简历，告诉我项目名称和核心技能。",
            "expected_tools": ["get_current_resume"],
            "validator": "resume",
        },
        {
            "id": "fixture_search",
            "prompt": "请用离线 Fixture 搜索上海的 Python 后端实习岗位，只查询，不收藏。",
            "expected_tools": ["search_jobs"],
            "validator": "fixture_search",
        },
        {
            "id": "confirmed_save",
            "prompt": "请用离线 Fixture 搜索上海的 Python 后端实习岗位，并将第一条加入岗位管理；需要确认时请发起确认。",
            "expected_tools": ["search_jobs", "propose_save_job"],
            "validator": "confirmed_save",
            "confirm_actions": True,
        },
        {
            "id": "live_job_pro_search",
            "prompt": "只使用 job-pro，搜索小红书在杭州的 Agent 开发实习岗位，不要收藏。",
            "expected_tools": ["search_jobs"],
            "validator": "live_search",
            "search_providers": ["job_pro"],
        },
        {
            "id": "subscription_list",
            "prompt": "请调用岗位订阅查询工具，列出我已配置的岗位查新和频率。",
            "expected_tools": ["list_job_subscriptions"],
            "validator": "subscription_list",
        },
        {
            "id": "confirmed_subscription_pause",
            "prompt": "请调用 propose_job_subscription_update 将编号 1 的岗位查新暂停，生成确认卡片后等用户确认。",
            "expected_tools": ["propose_job_subscription_update"],
            "validator": "confirmed_subscription_pause",
            "confirm_actions": True,
        },
        {
            "id": "confirmed_todo_create",
            "prompt": "新增一个高优先级求职待办，标题是准备技术面试。请通过确认卡片完成。",
            "expected_tools": ["propose_todo_create"],
            "validator": "confirmed_todo_create",
            "confirm_actions": True,
        },
    ]


def validate_case(case_id: str, tools: list[dict[str, Any]], answer: str, confirmation: dict[str, Any] | None) -> bool:
    results = [event.get("payload", {}).get("result") for event in tools]
    results = [item for item in results if isinstance(item, dict)]
    validator = {
        "general_chat": lambda: bool(answer.strip()),
        "saved_job_list": lambda: any(
            item.get("count", 0) >= 2
            and {row.get("city") for row in item.get("items", [])} >= {"杭州", "北京"}
            for item in results
        ),
        "application_status": lambda: any(item.get("total") == 2 for item in results),
        "compare_saved_jobs": lambda: any(len(item.get("items", [])) == 2 for item in results),
        "candidate_profile": lambda: any(
            item.get("profile", {}).get("school") == "评测大学"
            and {"上海", "杭州"} <= set(item.get("profile", {}).get("target_cities", []))
            for item in results
        ),
        "current_resume": lambda: any(
            item.get("resume", {}).get("title") == "E2E 合成简历"
            and "FastAPI" in item.get("resume", {}).get("structured_content", {}).get("skills", [])
            for item in results
        ),
        "fixture_search": lambda: any(
            item.get("filters", {}).get("cities") == ["上海"]
            and "Python" in str(item.get("filters", {}).get("keyword", ""))
            and item.get("total", 0) > 0
            and any(source.get("provider") == "fixture" and source.get("status") == "success"
                    for source in item.get("quality", {}).get("providers", []))
            for item in results
        ),
        "confirmed_save": lambda: bool(confirmation and confirmation.get("status") == "succeeded")
        and any(
            item.get("filters", {}).get("cities") == ["上海"] and item.get("total", 0) > 0
            for item in results
        ),
        "live_job_pro_search": lambda: any(
            item.get("filters", {}).get("company") == "小红书"
            and item.get("filters", {}).get("cities") == ["杭州"]
            and "Agent" in str(item.get("filters", {}).get("keyword", ""))
            and any(source.get("provider") == "job_pro" and source.get("status") == "success"
                    for source in item.get("quality", {}).get("providers", []))
            for item in results
        ),
        "subscription_list": lambda: any(
            item.get("total", 0) >= 1
            and any(row.get("name") == "评测岗位订阅" and row.get("enabled") is True for row in item.get("items", []))
            for item in results
        ),
        "confirmed_subscription_pause": lambda: bool(confirmation and confirmation.get("status") == "succeeded")
        and any(
            item.get("status") == "succeeded"
            and item.get("result", {}).get("subscription_id") == 1
            and item.get("result", {}).get("enabled") is False
            for item in results
        ),
        "confirmed_todo_create": lambda: bool(confirmation and confirmation.get("status") == "succeeded")
        and any(
            item.get("status") == "succeeded" and item.get("result", {}).get("todo_id")
            for item in results
        ),
    }[case_id]
    return bool(validator())


def validate_search_arguments(case_id: str, calls: list[dict[str, Any]]) -> bool | None:
    if case_id not in {"fixture_search", "confirmed_save", "live_job_pro_search"}:
        return None
    if not calls:
        return False
    arguments = calls[0]
    cities = arguments.get("cities") or ([arguments.get("city")] if arguments.get("city") else [])
    keyword = str(arguments.get("keyword") or "").lower()
    company = str(arguments.get("company") or "")
    if case_id == "live_job_pro_search":
        providers = arguments.get("providers") or []
        return (
            "杭州" in cities
            and "Agent".lower() in keyword
            and company == "小红书"
            and "job_pro" in providers
        )
    return "上海" in cities and "python" in keyword and "后端" in keyword


def run_case(
    client: httpx.Client,
    case: dict[str, Any],
    observed_search_arguments: list[dict[str, Any]],
) -> dict[str, Any]:
    observed_search_arguments.clear()
    request_body: dict[str, Any] = {"message": case["prompt"]}
    if case.get("search_providers") is not None:
        request_body["search_providers"] = case["search_providers"]

    started = time.perf_counter()
    first_visible_ms = None
    first_text_ms = None
    event_name = None
    data_lines: list[str] = []
    events: list[tuple[str, dict[str, Any]]] = []
    confirmation: dict[str, Any] | None = None
    transport_error = None
    http_status = None

    try:
        with client.stream("POST", "/api/v1/agent/chat/stream", json=request_body) as response:
            http_status = response.status_code
            if response.status_code != 200:
                response.read()
                transport_error = f"http_{response.status_code}"
            else:
                for line in response.iter_lines():
                    if line == "":
                        parsed = parse_event(event_name, data_lines)
                        event_name, data_lines = None, []
                        if parsed is None:
                            continue
                        name, payload = parsed
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        events.append((name, payload))
                        if name in {"assistant_delta", "tool_started", "action_proposed"} and first_visible_ms is None:
                            first_visible_ms = elapsed_ms
                        if name == "assistant_delta" and first_text_ms is None:
                            first_text_ms = elapsed_ms
                        if name == "action_proposed" and case.get("confirm_actions"):
                            resolved = client.post(f"/api/v1/agent/actions/{payload['id']}/resolve", json={"confirm": True})
                            if resolved.is_success:
                                confirmation = resolved.json()
                            else:
                                confirmation = {"status": "failed", "http_status": resolved.status_code}
                    elif line.startswith("event: "):
                        event_name = line.removeprefix("event: ")
                    elif line.startswith("data: "):
                        data_lines.append(line.removeprefix("data: "))
    except (httpx.HTTPError, OSError) as exc:
        transport_error = type(exc).__name__

    total_ms = (time.perf_counter() - started) * 1000
    tool_names = [payload.get("name") or payload.get("payload", {}).get("tool") for name, payload in events if name == "tool_started"]
    completed_tools = [payload for name, payload in events if name == "tool_completed"]
    final = next((payload for name, payload in reversed(events) if name == "assistant_completed"), {})
    answer = str(final.get("payload", {}).get("text") or "")
    expected_tools = case["expected_tools"]
    exact_tool_sequence = tool_names == expected_tools
    all_tools_succeeded = all(event.get("status") == "succeeded" for event in completed_tools)
    task_valid = validate_case(case["id"], completed_tools, answer, confirmation)
    args_valid = validate_search_arguments(case["id"], observed_search_arguments)
    completed = any(name == "assistant_completed" for name, _ in events)
    success = completed and exact_tool_sequence and all_tools_succeeded and task_valid and transport_error is None

    live_job_count = None
    if case["id"] == "live_job_pro_search":
        search_result = next(
            (event.get("payload", {}).get("result") for event in completed_tools
             if event.get("payload", {}).get("tool") == "search_jobs"),
            None,
        )
        if isinstance(search_result, dict):
            live_job_count = search_result.get("total")

    return {
        "case": case["id"],
        "success": success,
        "expected_tools": expected_tools,
        "actual_tools": tool_names,
        "tool_sequence_correct": exact_tool_sequence,
        "tool_calls_succeeded": all_tools_succeeded,
        "arguments_correct": args_valid,
        "search_arguments": observed_search_arguments.copy(),
        "assistant_completed": completed,
        "confirmation_status": confirmation.get("status") if confirmation else None,
        "confirmation_proposals": sum(name == "action_proposed" for name, _ in events),
        "live_jobs_returned": live_job_count,
        "first_visible_event_ms": round(first_visible_ms, 1) if first_visible_ms is not None else None,
        "first_text_delta_ms": round(first_text_ms, 1) if first_text_ms is not None else None,
        "total_ms": round(total_ms, 1),
        "http_status": http_status,
        "failure": transport_error or (None if success else "task_validation_failed"),
    }


def main() -> int:
    cases = make_cases()
    parser = argparse.ArgumentParser(description="Run the real-model Agent E2E suite against an isolated temporary database.")
    parser.add_argument("--case", choices=[case["id"] for case in cases], help="run one scenario only (useful for targeted prompt/tool regressions)")
    args = parser.parse_args()
    selected_cases = [case for case in cases if args.case is None or case["id"] == args.case]

    configured = get_settings()
    if not configured.litellm_model.strip() or not configured.openai_api_key.strip():
        print("评测未启动：请在项目 .env 配置 LITELLM_MODEL 和 OPENAI_API_KEY。", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="job-agent-e2e-") as temp_dir:
        eval_settings = configured.model_copy(update={
            "database_path": str(Path(temp_dir) / "evaluation.db"),
            "job_provider": "fixture",
        })
        engine = create_engine(eval_settings.database_url, connect_args={"check_same_thread": False}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

        def override_db():
            session = factory()
            try:
                yield session
            finally:
                session.close()

        job_service = JobSearchService(settings=eval_settings)
        agent_service = AgentService(settings=eval_settings, job_service=job_service)
        observed_search_arguments: list[dict[str, Any]] = []
        execute_tool = agent_service._execute_tool

        def capture_search_arguments(db, **kwargs):
            if kwargs.get("name") == "search_jobs":
                observed_search_arguments.append(dict(kwargs.get("arguments") or {}))
            return execute_tool(db, **kwargs)

        agent_service._execute_tool = capture_search_arguments
        agent_endpoints.service = agent_service
        job_endpoints.service = job_service
        app = create_app()
        app.dependency_overrides[db_session] = override_db

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        host, port = sock.getsockname()
        server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="critical", access_log=False, lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()

        timeout = max(configured.llm_timeout_seconds + configured.job_pro_timeout_seconds + 30, 60)
        base_url = f"http://{host}:{port}"
        results: list[dict[str, Any]] = []
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    with httpx.Client(timeout=2) as health_client:
                        response = health_client.get(f"{base_url}/openapi.json")
                        if response.status_code == 200:
                            break
                except httpx.HTTPError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("temporary evaluation API did not start")

            client_timeout = httpx.Timeout(connect=10, read=timeout, write=30, pool=10)
            with httpx.Client(base_url=base_url, timeout=client_timeout) as client:
                seed_eval_data(client)
                for case in selected_cases:
                    results.append(run_case(client, case, observed_search_arguments))
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            sock.close()
            engine.dispose()

    tool_cases = [item for item in results if item["expected_tools"]]
    arg_cases = [item for item in results if item["arguments_correct"] is not None]
    confirmation_cases = [item for item in results if item["confirmation_proposals"] > 0]
    totals = [item["total_ms"] for item in results]
    first_visible = [item["first_visible_event_ms"] for item in results if item["first_visible_event_ms"] is not None]
    first_text = [item["first_text_delta_ms"] for item in results if item["first_text_delta_ms"] is not None]
    summary = {
        "model_route": f"{configured.litellm_provider or 'litellm'}/{configured.litellm_model}",
        "suite": "real LiteLLM Tool Calling + isolated SQLite + fixture and read-only job-pro search",
        "selected_case": args.case,
        "sample_size": len(results),
        "task_success": {"passed": sum(bool(item["success"]) for item in results), "total": len(results)},
        "exact_tool_sequence_accuracy": {
            "correct": sum(bool(item["tool_sequence_correct"]) for item in tool_cases),
            "total": len(tool_cases),
        },
        "search_argument_accuracy": {
            "correct": sum(bool(item["arguments_correct"]) for item in arg_cases),
            "total": len(arg_cases),
        },
        "confirmed_mutation_scenarios": {
            "passed": sum(bool(item["success"]) for item in confirmation_cases),
            "total": len(confirmation_cases),
            "scope": "successful confirmation handoff only; pre-confirmation no-write behavior is asserted by deterministic tests",
        },
        "latency_ms": {
            "total_p50": percentile(totals, 0.50),
            "total_p95_nearest_rank": percentile(totals, 0.95),
            "total_mean": round(sum(totals) / len(totals), 1) if totals else None,
            "first_visible_event_p50": percentile(first_visible, 0.50),
            "first_text_delta_p50": percentile(first_text, 0.50),
        },
        "cases": results,
        "privacy_and_isolation": "synthetic profile/resume/jobs; temporary SQLite; no user DB or full model answers emitted",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(item["success"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
