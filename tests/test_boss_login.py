import json

from api.v1.endpoints import providers as provider_endpoint
from src.config import Settings
from src.services.boss_cli import BossCliInspection
from src.services.boss_login_service import BossLoginService, LoginRun


def compatible_cli_inspection(command="boss"):
    return BossCliInspection(
        executable=command,
        version="3.0.0",
        root_options=frozenset({"--browser-source", "--cdp-url", "--json"}),
        search_options=frozenset({"--city", "--job-type", "--no-cache"}),
        login_options=frozenset({"--cdp", "--timeout"}),
    )


def test_sensitive_login_messages_are_redacted():
    text = "token=abc123 cookie=secret security_id=job-1 手机号=13800000000"
    safe = BossLoginService._safe_text(text)

    assert "abc123" not in safe
    assert "secret" not in safe
    assert "job-1" not in safe
    assert "13800000000" not in safe
    assert "***" in safe


def test_provider_status_endpoint_does_not_expose_credentials(monkeypatch):
    monkeypatch.setattr(
        provider_endpoint.service,
        "status",
        lambda: {
            "provider": "boss_agent_cli",
            "installed": True,
            "authenticated": False,
            "status": "login_required",
            "message": "未登录，请先执行 boss login",
            "active_login_id": None,
            "can_start": True,
        },
    )

    result = provider_endpoint.boss_status()

    assert result["authenticated"] is False
    assert "cookie" not in str(result).lower()
    assert "token" not in str(result).lower()


def test_degraded_cli_status_is_not_reported_as_search_ready(monkeypatch):
    service = BossLoginService(Settings(boss_cli_command="boss"))

    class Completed:
        stdout = json.dumps(
            {
                "ok": True,
                "data": {
                    "logged_in": True,
                    "auth_state": "partial",
                    "auth_summary": "degraded",
                },
            }
        )

    monkeypatch.setattr(service, "_executable", lambda: "boss")
    monkeypatch.setattr(
        "src.services.boss_login_service.inspect_boss_cli",
        lambda _: compatible_cli_inspection(),
    )
    monkeypatch.setattr(service, "_cdp_ready", lambda: False)
    monkeypatch.setattr("src.services.boss_login_service.subprocess.run", lambda *args, **kwargs: Completed())

    result = service._read_local_status()

    assert result["authenticated"] is False
    assert result["status"] == "browser_session_missing"
    assert "Chrome" in result["message"]


def test_existing_browser_session_can_be_search_ready_with_partial_cache(monkeypatch):
    service = BossLoginService(
        Settings(
            boss_cli_command="boss",
            boss_browser_source="existing-browser",
            boss_cdp_url="http://127.0.0.1:9222",
        )
    )

    class Completed:
        stdout = json.dumps(
            {
                "ok": True,
                "data": {
                    "logged_in": True,
                    "auth_state": "partial",
                    "auth_summary": "degraded",
                },
            }
        )

    monkeypatch.setattr(service, "_executable", lambda: "boss")
    monkeypatch.setattr(
        "src.services.boss_login_service.inspect_boss_cli",
        lambda _: compatible_cli_inspection(),
    )
    monkeypatch.setattr(service, "_cdp_ready", lambda: True)
    monkeypatch.setattr(service, "_cdp_boss_page_ready", lambda: True)
    monkeypatch.setattr("src.services.boss_login_service.subprocess.run", lambda *args, **kwargs: Completed())

    result = service._read_local_status()

    assert result["authenticated"] is True
    assert "Chrome" in result["message"]


def test_cached_login_without_boss_page_is_not_reported_as_available(monkeypatch):
    service = BossLoginService(
        Settings(
            boss_cli_command="boss",
            boss_browser_source="existing-browser",
            boss_cdp_url="http://127.0.0.1:9222",
        )
    )

    class Completed:
        stdout = json.dumps({"ok": True, "data": {"logged_in": True, "auth_state": "healthy"}})

    monkeypatch.setattr(service, "_executable", lambda: "boss")
    monkeypatch.setattr(
        "src.services.boss_login_service.inspect_boss_cli",
        lambda _: compatible_cli_inspection(),
    )
    monkeypatch.setattr(service, "_cdp_ready", lambda: True)
    monkeypatch.setattr(service, "_cdp_boss_page_ready", lambda: False)
    monkeypatch.setattr("src.services.boss_login_service.subprocess.run", lambda *args, **kwargs: Completed())

    result = service._read_local_status()

    assert result["authenticated"] is False
    assert result["status"] == "browser_session_missing"


def test_login_opens_boss_page_in_existing_cdp_chrome(monkeypatch):
    service = BossLoginService(Settings(boss_cdp_url="http://127.0.0.1:9222"))
    run = LoginRun(run_id="test-login")
    readiness = iter([False, True])
    monkeypatch.setattr(service, "_cdp_boss_page_ready", lambda: next(readiness))
    monkeypatch.setattr(service, "_cdp_ready", lambda: True)
    monkeypatch.setattr(service, "_open_boss_page_in_cdp", lambda: True)

    service._ensure_visible_browser(run)

    assert any("BOSS 官方登录页已在 Chrome 打开" in event["message"] for event in run.events)
