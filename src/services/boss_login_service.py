"""Local, user-initiated BOSS login orchestration.

The service never accepts credentials and never exposes CLI stdout verbatim.
It only starts the locally installed ``boss login`` command, redacts progress
messages, and exposes a small in-memory event stream for the local web UI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from src.config import Settings, get_settings
from src.services.boss_cli import (
    BossCliIncompatible,
    BossCliInspection,
    BossCliUnavailable,
    build_boss_prefix,
    inspect_boss_cli,
    require_compatible_boss_cli,
    resolve_boss_cli,
)


TERMINAL_STATES = {"succeeded", "failed", "canceled"}
BOSS_LOGIN_URL = "https://www.zhipin.com/web/geek/job"
CDP_PAGE_TYPES = {"page"}
_SENSITIVE_VALUE = re.compile(
    r"(?i)(cookie|token|secret|security[_ -]?id|手机号|phone)(\s*[=:：]\s*)[^\s,;]+"
)


class LoginRunNotFound(KeyError):
    """A login run id is not present in the local process."""


@dataclass
class LoginRun:
    run_id: str
    status: str = "starting"
    message: str = "正在启动 BOSS 登录流程"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    return_code: int | None = None
    process: subprocess.Popen[str] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_event(self, event_type: str, *, status: str, message: str) -> None:
        with self.lock:
            self.status = status
            self.message = message
            self.events.append(
                {
                    "sequence": len(self.events) + 1,
                    "type": event_type,
                    "status": status,
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    def snapshot(self, after_sequence: int = 0) -> tuple[list[dict[str, Any]], bool]:
        with self.lock:
            events = [item for item in self.events if item["sequence"] > after_sequence]
            return events, self.status in TERMINAL_STATES


class BossLoginService:
    """Starts and observes one local BOSS login process at a time."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._runs: dict[str, LoginRun] = {}
        self._lock = threading.Lock()

    @property
    def command(self) -> str:
        return self.settings.boss_cli_command

    def _executable(self) -> str | None:
        try:
            return resolve_boss_cli(self.command)
        except BossCliUnavailable:
            return None

    def _active_run(self) -> LoginRun | None:
        with self._lock:
            for run in reversed(list(self._runs.values())):
                if run.status not in TERMINAL_STATES:
                    return run
        return None

    def start(self) -> tuple[LoginRun, bool]:
        inspection = require_compatible_boss_cli(
            inspect_boss_cli(self.command),
            browser_source=self.settings.boss_browser_source,
        )

        active = self._active_run()
        if active is not None:
            return active, True

        run = LoginRun(run_id=f"boss_login_{uuid.uuid4().hex}")
        with self._lock:
            self._runs[run.run_id] = run
        thread = threading.Thread(target=self._run_login, args=(run, inspection), daemon=True)
        thread.start()
        return run, False

    def _run_login(self, run: LoginRun, inspection: BossCliInspection) -> None:
        run.add_event("started", status="waiting_user", message="登录流程已启动，请在官方 BOSS 页面完成扫码或手机号登录")
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        try:
            self._ensure_visible_browser(run)
            process = subprocess.Popen(
                build_boss_prefix(
                    inspection,
                    browser_source=self.settings.boss_browser_source,
                    cdp_url=self.settings.boss_cdp_url,
                )
                + ["login", "--cdp", "--timeout", str(self.settings.boss_login_timeout_seconds)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            run.process = process
            stdout_thread = threading.Thread(
                target=self._collect_output,
                args=(process.stdout, stdout_lines, run),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._collect_output,
                args=(process.stderr, stderr_lines, run),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            try:
                run.return_code = process.wait(timeout=self.settings.boss_login_timeout_seconds + 20)
            except subprocess.TimeoutExpired:
                process.kill()
                run.return_code = None
                self._finish(run, "failed", "BOSS 登录等待超时，请重新发起登录", event_type="failed")
                return
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            if run.status == "canceled":
                return
            envelope = self._parse_envelope(stdout_lines)
            if run.return_code == 0 and envelope.get("ok") is True:
                local_status = self._read_local_status(inspection)
                if local_status["authenticated"]:
                    self._finish(run, "succeeded", "BOSS 登录成功，已检测到可用本地登录态", event_type="succeeded")
                else:
                    self._finish(run, "failed", "CLI 已退出，但没有检测到可用登录态，请重新登录", event_type="failed")
            else:
                error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
                message = self._safe_text(error.get("message") or "BOSS 登录未完成")
                self._finish(run, "failed", message, event_type="failed")
        except FileNotFoundError:
            self._finish(run, "failed", f"未找到 BOSS CLI：{self.command}", event_type="failed")
        except BossCliIncompatible as exc:
            self._finish(run, "failed", self._safe_text(str(exc)), event_type="failed")
        except Exception as exc:  # pragma: no cover - defensive process boundary
            self._finish(run, "failed", f"登录进程启动失败：{self._safe_text(str(exc))}", event_type="failed")
        finally:
            run.process = None

    @staticmethod
    def _collect_output(stream: Any, lines: list[str], run: LoginRun) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            lines.append(line)
            message = BossLoginService._safe_text(line.strip())
            if message and not message.startswith("{"):
                run.add_event("progress", status="waiting_user", message=message)

    @staticmethod
    def _parse_envelope(lines: list[str]) -> dict[str, Any]:
        for line in reversed(lines):
            try:
                value = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _safe_text(value: Any) -> str:
        text = str(value or "").strip()
        return _SENSITIVE_VALUE.sub(r"\1=***", text)[:500]

    def _read_local_status(self, inspection: BossCliInspection | None = None) -> dict[str, Any]:
        try:
            inspection = inspection or inspect_boss_cli(self.command)
            inspection = require_compatible_boss_cli(
                inspection,
                browser_source=self.settings.boss_browser_source,
            )
        except (BossCliUnavailable, BossCliIncompatible) as exc:
            return {"authenticated": False, "message": self._safe_text(str(exc))}
        try:
            result = subprocess.run(
                build_boss_prefix(
                    inspection,
                    browser_source=self.settings.boss_browser_source,
                    cdp_url=self.settings.boss_cdp_url,
                )
                + ["status"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"authenticated": False, "message": "BOSS 本地登录状态检查超时"}
        envelope = self._parse_envelope(result.stdout.splitlines())
        if envelope.get("ok") is True:
            data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
            auth_state = data.get("auth_state")
            auth_summary = data.get("auth_summary")
            if self.settings.boss_browser_source == "existing-browser":
                # A cached CLI login is not enough: searches attach to the
                # user's visible CDP tab. Requiring an actual BOSS page avoids
                # reporting "available" when Chrome is stopped or has no page
                # target (the CLI then fails with BROWSER_SESSION_NOT_FOUND).
                if not self._cdp_ready() or not self._cdp_boss_page_ready():
                    return {
                        "authenticated": False,
                        "status": "browser_session_missing",
                        "message": "本机登录缓存存在，但项目 Chrome 中没有可复用的 BOSS 页面；请打开 Chrome 登录页后再搜索",
                    }
                if data.get("logged_in") is True:
                    if auth_state in {"partial", "missing", "broken"} or auth_summary in {"degraded", "broken"}:
                        return {
                            "authenticated": True,
                            "message": "已检测到 Chrome 中的 BOSS 登录态；本地缓存不完整但可使用浏览器会话搜索",
                        }
                    return {"authenticated": True, "message": "Chrome 中的 BOSS 登录态可用"}
                return {
                    "authenticated": False,
                    "status": "login_required",
                    "message": "项目 Chrome 中尚未登录 BOSS，请在该窗口完成扫码或手机号登录",
                }
            if auth_state in {"partial", "missing", "broken"} or auth_summary in {"degraded", "broken"}:
                return {
                    "authenticated": False,
                    "status": "login_required",
                    "message": "BOSS 登录态不完整，请通过可见 Chrome 登录窗口重新登录",
                }
            return {"authenticated": data.get("logged_in") is not False, "message": "已检测到可用本地登录态"}
        error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
        return {
            "authenticated": False,
            "status": "login_required",
            "message": self._safe_text(error.get("message") or "尚未登录 BOSS"),
        }

    def _ensure_visible_browser(self, run: LoginRun) -> None:
        if self._cdp_boss_page_ready():
            run.add_event("browser_ready", status="waiting_user", message="已连接本机可见 Chrome 登录窗口")
            return
        if self._cdp_ready():
            run.add_event("browser_opening_page", status="waiting_user", message="正在项目专用 Chrome 中打开 BOSS 官方登录页")
            if self._open_boss_page_in_cdp():
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if self._cdp_boss_page_ready():
                        run.add_event("browser_ready", status="waiting_user", message="BOSS 官方登录页已在 Chrome 打开，请在该窗口完成扫码或手机号登录")
                        return
                    time.sleep(0.3)
            raise RuntimeError("Chrome 调试会话已连接，但无法打开 BOSS 页面；请重新启动登录流程")
        if not self.settings.boss_auto_start_chrome:
            raise RuntimeError("未检测到可用 Chrome CDP 窗口，请启动带 9222 调试端口的 Chrome")

        chrome_path = self._chrome_path()
        if chrome_path is None:
            raise RuntimeError("未找到 Google Chrome，无法启动可见登录窗口")
        profile_path = Path(self.settings.boss_chrome_profile_path).expanduser()
        profile_path.mkdir(parents=True, exist_ok=True)
        run.add_event("browser_starting", status="waiting_user", message="正在启动独立 Chrome 登录窗口，请稍候")
        chrome_args = [
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={self._cdp_port()}",
            f"--user-data-dir={profile_path}",
            BOSS_LOGIN_URL,
        ]
        launch_command = self._chrome_launch_command(chrome_path, chrome_args)
        subprocess.Popen(
            launch_command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self._cdp_boss_page_ready():
                run.add_event("browser_ready", status="waiting_user", message="Chrome 登录窗口已打开，请完成 BOSS 扫码或手机号登录")
                return
            time.sleep(0.4)
        raise RuntimeError("Chrome 登录窗口启动超时，请确认 Chrome 已打开后重试")

    @staticmethod
    def _chrome_launch_command(chrome_path: str, chrome_args: list[str]) -> list[str]:
        if sys.platform == "darwin":
            app_path = str(Path(chrome_path).parents[2])
            return ["open", "-na", app_path, "--args", *chrome_args]
        return [chrome_path, *chrome_args]

    def _cdp_ready(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.settings.boss_cdp_url.rstrip('/')}/json/version", timeout=1):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _cdp_targets(self) -> list[dict[str, Any]] | None:
        try:
            with urllib.request.urlopen(f"{self.settings.boss_cdp_url.rstrip('/')}/json/list", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None
        return [target for target in payload if isinstance(target, dict)] if isinstance(payload, list) else None

    @staticmethod
    def _is_boss_page_target(target: dict[str, Any]) -> bool:
        if target.get("type") not in CDP_PAGE_TYPES:
            return False
        host = urlparse(str(target.get("url") or "")).hostname or ""
        return host == "zhipin.com" or host.endswith(".zhipin.com")

    def _cdp_boss_page_ready(self) -> bool:
        targets = self._cdp_targets()
        return bool(targets is not None and any(self._is_boss_page_target(target) for target in targets))

    def _open_boss_page_in_cdp(self) -> bool:
        encoded_url = quote(BOSS_LOGIN_URL, safe=":/?=&")
        request = urllib.request.Request(
            f"{self.settings.boss_cdp_url.rstrip('/')}/json/new?{encoded_url}",
            method="PUT",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                target = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return False
        return isinstance(target, dict) and self._is_boss_page_target(target)

    def _cdp_port(self) -> int:
        parsed = urlparse(self.settings.boss_cdp_url)
        return parsed.port or 9222

    def _chrome_path(self) -> str | None:
        configured = self.settings.boss_chrome_path.strip()
        candidates = [configured] if configured else []
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        )
        for candidate in candidates:
            if candidate:
                from pathlib import Path
                path = Path(candidate).expanduser()
                if path.exists():
                    return str(path)
        return shutil.which("google-chrome") or shutil.which("google-chrome-stable")

    def status(self) -> dict[str, Any]:
        try:
            inspection = inspect_boss_cli(self.command)
        except BossCliUnavailable as exc:
            return {
                "provider": "boss_agent_cli",
                "installed": False,
                "authenticated": False,
                "status": "not_installed",
                "message": self._safe_text(str(exc)),
                "active_login_id": None,
                "can_start": False,
            }
        try:
            inspection = require_compatible_boss_cli(
                inspection,
                browser_source=self.settings.boss_browser_source,
            )
        except BossCliIncompatible as exc:
            return {
                "provider": "boss_agent_cli",
                "installed": True,
                "authenticated": False,
                "status": "incompatible",
                "message": self._safe_text(str(exc)),
                "active_login_id": None,
                "can_start": False,
            }
        active = self._active_run()
        if active is not None:
            return {
                "provider": "boss_agent_cli",
                "installed": True,
                "authenticated": False,
                "status": active.status,
                "message": active.message,
                "active_login_id": active.run_id,
                "can_start": False,
            }
        local_status = self._read_local_status(inspection)
        return {
            "provider": "boss_agent_cli",
            "installed": True,
            "authenticated": local_status["authenticated"],
            "status": local_status.get("status") or ("available" if local_status["authenticated"] else "login_required"),
            "message": local_status["message"],
            "active_login_id": None,
            "can_start": True,
        }

    def describe(self, run: LoginRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "status": run.status,
            "message": run.message,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
        }

    def events(self, run_id: str, after_sequence: int = 0) -> tuple[list[dict[str, Any]], bool]:
        run = self._runs.get(run_id)
        if run is None:
            raise LoginRunNotFound(run_id)
        return run.snapshot(after_sequence)

    def cancel(self, run_id: str) -> LoginRun:
        run = self._runs.get(run_id)
        if run is None:
            raise LoginRunNotFound(run_id)
        if run.status in TERMINAL_STATES:
            return run
        process = run.process
        if process is not None and process.poll() is None:
            process.kill()
        self._finish(run, "canceled", "登录流程已由用户取消", event_type="canceled")
        return run

    @staticmethod
    def _finish(run: LoginRun, status: str, message: str, *, event_type: str) -> None:
        run.ended_at = datetime.now(timezone.utc)
        run.add_event(event_type, status=status, message=message)


# The web API and Agent share the same in-memory login run so the existing
# status/SSE endpoints can observe a login started from either entry point.
boss_login_service = BossLoginService()
