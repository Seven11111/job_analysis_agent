"""Read-only adapter for the local ``boss-agent-cli`` executable.

The adapter deliberately talks to the CLI boundary instead of importing its
internal modules.  This keeps the learning project decoupled from the tool's
release cadence and makes the Provider unavailable, rather than silently
falling back, when the local tool is not installed or logged in.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import date
from typing import Any

from src.config import Settings, get_settings
from src.data_provider.base import JobRecord
from src.services.boss_cli import (
    BossCliUnavailable,
    build_boss_prefix,
    inspect_boss_cli,
    require_compatible_boss_cli,
)


class BossAgentProvider:
    provider_name = "boss_agent_cli"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._risk_blocked_until = 0.0

    def _risk_cooldown_message(self) -> str | None:
        remaining = int(self._risk_blocked_until - time.monotonic())
        if remaining <= 0:
            return None
        return f"BOSS 来源处于风控冷却中，预计还需 {remaining} 秒；请不要连续重试，先在官方页面完成验证并降低访问频率"

    @staticmethod
    def _is_risk_control(message: str) -> bool:
        normalized = message.lower()
        return "code 37" in normalized or "环境风控" in message or "环境异常" in message

    def _raise_provider_error(self, message: str) -> None:
        if self._is_risk_control(message):
            self._risk_blocked_until = time.monotonic() + self.settings.boss_risk_cooldown_seconds
            raise RuntimeError(
                "BOSS 直聘访问环境风控（code 37），已停止后续请求并进入冷却；"
                "请保留当前专用 Chrome profile，在官方页面确认后降低访问频率再重试"
            )
        raise RuntimeError(message or "BOSS 工具返回失败")

    def search(self, *, keyword: str | None = None, city: str | None = None) -> list[JobRecord]:
        cooldown_message = self._risk_cooldown_message()
        if cooldown_message:
            raise RuntimeError(cooldown_message)
        try:
            inspection = require_compatible_boss_cli(
                inspect_boss_cli(self.settings.boss_cli_command),
                browser_source=self.settings.boss_browser_source,
            )
        except BossCliUnavailable as exc:
            raise RuntimeError(
                "未找到 boss-agent-cli。请先安装 boss-agent-cli 并完成登录；"
                "本项目不会自动登录或保存平台 Cookie。"
            ) from exc

        # Keep every invocation pinned to the user's configured local CDP
        # endpoint. The login flow is separately forced to --cdp and never
        # falls back to another browser or headless login channel.
        command = build_boss_prefix(
            inspection,
            browser_source=self.settings.boss_browser_source,
            cdp_url=self.settings.boss_cdp_url,
        )
        command.extend(["search", (keyword or "实习岗位").strip(), "--job-type", "实习"])
        command.append("--no-cache")
        if city:
            command.extend(["--city", city.strip()])
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.settings.boss_cli_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("BOSS 只读搜索超时，请稍后重试") from exc

        output = (completed.stdout or completed.stderr).strip()
        if completed.returncode != 0:
            self._raise_provider_error(self._error_message(output, completed.returncode))
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("BOSS 工具返回了无法解析的结果") from exc

        if isinstance(payload, dict) and payload.get("ok") is False:
            error = payload.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            code = error.get("code") if isinstance(error, dict) else None
            self._raise_provider_error(f"{message or 'BOSS 工具返回失败'}" + (f" (code {code})" if code else ""))

        rows = self._find_rows(payload)
        return [self._to_record(row, city=city) for row in rows if self._valid_row(row)]

    @staticmethod
    def _error_message(output: str, returncode: int) -> str:
        try:
            payload = json.loads(output)
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            message = error.get("message") if isinstance(error, dict) else None
            if message:
                code = error.get("code") if isinstance(error, dict) else None
                return f"{message} (code {code})" if code else str(message)
        except json.JSONDecodeError:
            pass
        return output[:300] or f"BOSS 工具退出码 {returncode}"

    @classmethod
    def _find_rows(cls, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("results", "jobs", "items", "list", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict):
                nested = cls._find_rows(value)
                if nested:
                    return nested
        return []

    @staticmethod
    def _valid_row(row: dict[str, Any]) -> bool:
        return bool(
            BossAgentProvider._first(
                row,
                "title",
                "job_title",
                "jobTitle",
                "job_name",
                "jobName",
                "position",
                "name",
            )
            and BossAgentProvider._first(
                row,
                "url",
                "detail_url",
                "detailUrl",
                "job_url",
                "jobUrl",
                "link",
                "job_id",
                "jobId",
                "encryptJobId",
                "encrypt_job_id",
                "security_id",
                "securityId",
            )
        )

    @staticmethod
    def _first(row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _to_record(cls, row: dict[str, Any], *, city: str | None) -> JobRecord:
        title = str(
            cls._first(row, "title", "job_title", "jobTitle", "job_name", "jobName", "position", "name")
            or "岗位"
        )
        company = cls._first(
            row,
            "company",
            "company_name",
            "companyName",
            "brand_name",
            "brandName",
            "brand",
        )
        location = cls._first(row, "city", "city_name", "cityName", "location", "address") or city or "未说明"
        detail_url = cls._detail_url(row)
        source_id = str(
            cls._first(
                row,
                "encryptJobId",
                "encrypt_job_id",
                "job_id",
                "jobId",
                "security_id",
                "securityId",
                "source_job_id",
                "sourceJobId",
                "id",
            )
            or detail_url
        )
        salary_text = str(cls._first(row, "salary", "salary_text", "salaryText", "salary_desc", "salaryDesc") or "")
        salary_min, salary_max, salary_unit = cls._parse_salary(salary_text)
        published = cls._parse_date(
            cls._first(
                row,
                "published_date",
                "publishedDate",
                "date",
                "publish_time",
                "publishTime",
                "last_modify_time",
                "lastModifyTime",
                "posted_date",
                "postedDate",
            )
        )
        description = cls._first(
            row,
            "description",
            "job_description",
            "jobDescription",
            "job_desc",
            "jobDesc",
            "brief",
        )
        education = cls._first(row, "education", "job_degree", "jobDegree", "degree")
        requirements = cls._first(
            row,
            "requirements",
            "requirements_text",
            "requirementsText",
            "job_requirement",
            "jobRequirement",
            "job_experience",
            "jobExperience",
        )
        return JobRecord(
            source_job_id=source_id,
            title=title,
            company_name=str(company or "未说明"),
            city=str(location),
            detail_url=detail_url,
            published_date=published,
            job_type="实习生" if "实习" in title or "实习" in salary_text else "实习生",
            salary_min=salary_min,
            salary_max=salary_max,
            salary_unit=salary_unit,
            salary_status="disclosed" if salary_min is not None else "unknown",
            education=str(education) if education else None,
            description=str(description) if description else None,
            requirements=str(requirements) if requirements else None,
            responsibilities=(
                str(cls._first(row, "responsibilities", "job_responsibilities", "jobResponsibilities", "jobDuty"))
                if cls._first(row, "responsibilities", "job_responsibilities", "jobResponsibilities", "jobDuty")
                else None
            ),
            extraction_method="boss_agent_cli",
            raw_payload=row,
        )

    @classmethod
    def _detail_url(cls, row: dict[str, Any]) -> str:
        explicit_url = cls._first(row, "url", "detail_url", "detailUrl", "job_url", "jobUrl", "link")
        if explicit_url:
            return str(explicit_url)
        # BOSS search responses expose the encrypted job id instead of a
        # browser URL. This is the public, read-only detail route and keeps
        # the source link usable in the search UI without persisting cookies.
        job_id = cls._first(row, "encryptJobId", "encrypt_job_id", "job_id", "jobId", "source_job_id", "sourceJobId")
        if job_id:
            return f"https://www.zhipin.com/job_detail/{job_id}.html"
        security_id = cls._first(row, "security_id", "securityId")
        if security_id:
            return f"https://www.zhipin.com/job_detail/{security_id}.html"
        return "https://www.zhipin.com/"

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", str(value))
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    @staticmethod
    def _parse_salary(value: str) -> tuple[float | None, float | None, str | None]:
        numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]
        if not numbers:
            return None, None, None
        unit = "元/月" if "月" in value else "元/天" if "天" in value else None
        if len(numbers) >= 2:
            return numbers[0], numbers[1], unit
        return numbers[0], numbers[0], unit
