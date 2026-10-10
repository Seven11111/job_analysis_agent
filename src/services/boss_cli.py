"""Compatibility boundary for the locally installed ``boss-agent-cli``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess

from src.config import PROJECT_ROOT


class BossCliUnavailable(RuntimeError):
    """The configured BOSS CLI executable cannot be resolved."""


class BossCliIncompatible(RuntimeError):
    """The installed BOSS CLI cannot satisfy this adapter's safe contract."""


@dataclass(frozen=True)
class BossCliInspection:
    executable: str
    version: str | None
    root_options: frozenset[str]
    search_options: frozenset[str]
    login_options: frozenset[str]


def resolve_boss_cli(command: str) -> str:
    """Resolve a PATH command or an explicitly configured executable path."""
    configured = command.strip()
    if not configured:
        raise BossCliUnavailable("BOSS_CLI_COMMAND 未配置")

    candidate = Path(configured).expanduser()
    if not candidate.is_absolute() and "/" in configured:
        candidate = PROJECT_ROOT / candidate
    if candidate.is_absolute() or "/" in configured:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate.resolve())
        raise BossCliUnavailable(f"未找到可执行的 BOSS CLI：{configured}")

    executable = shutil.which(configured)
    if executable:
        return str(Path(executable).resolve())
    raise BossCliUnavailable(f"未找到 BOSS CLI：{configured}")


def _extract_options(help_text: str) -> frozenset[str]:
    options: set[str] = set()
    option_line = re.compile(
        r"^\s*(?:-[a-z0-9],\s*)?(--[a-z][a-z0-9-]*(?:\s*/\s*--[a-z][a-z0-9-]*)*)",
        re.IGNORECASE,
    )
    for line in help_text.splitlines():
        match = option_line.match(line)
        if match:
            options.update(re.findall(r"--[a-z][a-z0-9-]*", match.group(1).lower()))
    return frozenset(options)


def _run_probe(executable: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


@lru_cache(maxsize=16)
def _inspect_cached(executable: str, mtime_ns: int, size: int) -> BossCliInspection:
    del mtime_ns, size  # included in the cache key so upgrades invalidate probes
    try:
        version_result = _run_probe(executable, "--version")
        root_result = _run_probe(executable, "--help")
        search_result = _run_probe(executable, "search", "--help")
        login_result = _run_probe(executable, "login", "--help")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BossCliIncompatible(f"无法读取 BOSS CLI 命令能力：{exc}") from exc

    root_help = "\n".join((root_result.stdout or "", root_result.stderr or ""))
    search_help = "\n".join((search_result.stdout or "", search_result.stderr or ""))
    login_help = "\n".join((login_result.stdout or "", login_result.stderr or ""))
    if root_result.returncode != 0 or not root_help.strip():
        raise BossCliIncompatible("无法读取 `boss --help`；请确认配置的是 boss-agent-cli 的可执行文件")
    if search_result.returncode != 0 or not search_help.strip():
        raise BossCliIncompatible("BOSS CLI 未提供可识别的 `search` 子命令")
    if login_result.returncode != 0 or not login_help.strip():
        raise BossCliIncompatible("BOSS CLI 未提供可识别的 `login` 子命令")

    version_output = " ".join((version_result.stdout or "", version_result.stderr or ""))
    version_match = re.search(r"\b(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)\b", version_output)
    return BossCliInspection(
        executable=executable,
        version=version_match.group(1) if version_match else None,
        root_options=_extract_options(root_help),
        search_options=_extract_options(search_help),
        login_options=_extract_options(login_help),
    )


def inspect_boss_cli(command: str) -> BossCliInspection:
    executable = resolve_boss_cli(command)
    try:
        stat = Path(executable).stat()
    except OSError as exc:
        raise BossCliUnavailable(f"无法读取 BOSS CLI：{command}") from exc
    return _inspect_cached(executable, stat.st_mtime_ns, stat.st_size)


def compatibility_problems(
    inspection: BossCliInspection,
    *,
    browser_source: str,
) -> list[str]:
    """List unsupported features required for safe read-only search/login."""
    problems: list[str] = []
    if browser_source != "existing-browser":
        problems.append("BOSS_BROWSER_SOURCE 必须设置为 existing-browser")

    for option, label in (
        ("--cdp-url", "指定本机 Chrome CDP 地址"),
        ("--json", "稳定输出 JSON 信封"),
    ):
        if option not in inspection.root_options:
            problems.append(f"CLI 不支持 {option}（{label}）")
    for option, label in (
        ("--city", "按用户选择的城市筛选"),
        ("--job-type", "将搜索范围限制为实习岗位"),
        ("--no-cache", "保证每次读取最新搜索结果"),
    ):
        if option not in inspection.search_options:
            problems.append(f"CLI 的 search 不支持 {option}（{label}）")
    for option, label in (
        ("--cdp", "限定为本机浏览器登录"),
        ("--timeout", "控制登录等待时长"),
    ):
        if option not in inspection.login_options:
            problems.append(f"CLI 的 login 不支持 {option}（{label}）")
    return problems


def require_compatible_boss_cli(
    inspection: BossCliInspection,
    *,
    browser_source: str,
) -> BossCliInspection:
    problems = compatibility_problems(inspection, browser_source=browser_source)
    if problems:
        version = f"（检测版本 {inspection.version}）" if inspection.version else ""
        details = "；".join(problems)
        raise BossCliIncompatible(
            f"当前 BOSS CLI{version} 与只读适配不兼容：{details}。"
            "请更新 boss-agent-cli，或在 BOSS_CLI_COMMAND 中指定兼容版本的可执行文件。"
        )
    return inspection


def build_boss_prefix(
    inspection: BossCliInspection,
    *,
    browser_source: str,
    cdp_url: str,
) -> list[str]:
    """Build global options before a CLI subcommand."""
    command = [inspection.executable]
    # Some CLI releases expose an explicit source selector; current releases
    # may expose only --cdp-url. In that case login still uses --cdp and never
    # falls back to launching a different/headless browser channel.
    if "--browser-source" in inspection.root_options:
        command.extend(["--browser-source", browser_source])
    command.extend(["--cdp-url", cdp_url, "--json"])
    return command
