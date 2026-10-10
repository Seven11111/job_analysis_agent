"""Read-only adapter for the open-source ``job-pro`` public-API client.

``job-pro`` is intentionally kept behind a subprocess boundary.  The learning
project owns normalization and filtering, while the third-party client owns
the individual company adapters.  The adapter never writes to the database
and does not attempt to bypass login, CAPTCHA, or anti-bot controls.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT, Settings, get_settings
from src.data_provider.base import JobRecord


class JobProProvider:
    provider_name = "job_pro"

    COMPANY_NAMES = {
        "tencent": "腾讯",
        "bytedance": "字节跳动",
        "alibaba": "阿里巴巴",
        "meituan": "美团",
        "xiaohongshu": "小红书",
        "jd": "京东",
        "kuaishou": "快手",
        "baidu": "百度",
        "netease": "网易",
        "didi": "滴滴",
        "bilibili": "哔哩哔哩",
        "pdd": "拼多多",
        "huawei": "华为",
        "weibo": "微博",
        "mihoyo": "米哈游",
        "pingan": "平安",
        "trip": "携程",
        "unitree": "宇树科技",
        "byd": "比亚迪",
        "antgroup": "蚂蚁集团",
        "liauto": "理想汽车",
        "sf": "顺丰",
        "oppo": "OPPO",
        "xiaomi": "小米",
        "nio": "蔚来",
        "minimax": "MiniMax",
        "moonshot": "月之暗面",
        "zhipu": "智谱AI",
        "iqiyi": "爱奇艺",
        "agibot": "智元机器人",
        "lilith": "莉莉丝",
        "zerooneai": "零一万物",
        "baichuan": "百川智能",
        "sensetime": "商汤科技",
        "horizonrobotics": "地平线",
        "vivo": "vivo",
        "iflytek": "科大讯飞",
        "megvii": "旷视",
        "deepseek": "深度求索",
        "galaxyuniversal": "银河通用",
        "stepfun": "阶跃星辰",
        "cambricon": "寒武纪",
        "geely": "吉利",
        "xpeng": "小鹏汽车",
        "weride": "文远知行",
        "hoyoverse": "米哈游国际",
        "hikvision": "海康威视",
        "cicc": "中金",
        "cainiao": "菜鸟",
        "webank": "微众银行",
    }
    COMPANY_ALIASES = {
        "b站": "bilibili",
        "米哈游国际": "hoyoverse",
        "宇树": "unitree",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def search(
        self,
        *,
        keyword: str | None = None,
        city: str | None = None,
        company: str | None = None,
    ) -> list[JobRecord]:
        companies = [item.strip() for item in self.settings.job_pro_companies.split(",") if item.strip()]
        if company and company.strip():
            company_id = self.company_id(company)
            if not company_id:
                raise RuntimeError(f"job-pro 暂不支持公司“{company.strip()}”，请使用已配置的公司来源")
            if companies and company_id not in companies:
                raise RuntimeError(f"公司“{company.strip()}”未包含在 JOB_PRO_COMPANIES 配置中")
            companies = [company_id]

        executable = resolve_job_pro_cli(self.settings.job_pro_command)
        if executable is None:
            raise RuntimeError(
                "未找到 job-pro。请先安装 @ha7ch/job-pro（Node.js >= 18），"
                "然后确认 JOB_PRO_COMMAND 指向项目内 .tools/job-pro 下的可执行文件。"
            )

        command = [
            executable,
            "find",
            (keyword or "实习岗位").strip(),
            "--scope",
            self.settings.job_pro_scope,
            "--limit",
            "50",
            "--compact",
        ]
        if companies:
            command.extend(["--companies", ",".join(companies)])

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.settings.job_pro_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("job-pro 岗位搜索超时，请稍后重试") from exc

        output = (completed.stdout or completed.stderr).strip()
        if completed.returncode != 0:
            raise RuntimeError(self._error_message(output, completed.returncode))
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("job-pro 返回了无法解析的 JSON") from exc
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(str(payload.get("error") or "job-pro 返回失败"))

        rows = self._find_rows(payload)
        records = [self._to_record(row, company=company, city=city) for company, row in rows]
        records = [record for record in records if record is not None]
        if not records:
            failed = self._failed_sources(payload)
            if failed:
                raise RuntimeError(f"job-pro 来源失败：{'；'.join(failed)[:260]}")
        return records
    @classmethod
    def company_id(cls, company: str) -> str | None:
        normalized = company.strip().casefold()
        if normalized in cls.COMPANY_ALIASES:
            return cls.COMPANY_ALIASES[normalized]
        for company_id, label in cls.COMPANY_NAMES.items():
            if normalized in {company_id.casefold(), label.casefold()}:
                return company_id
        return None

    @staticmethod
    def _error_message(output: str, returncode: int) -> str:
        try:
            payload = json.loads(output)
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    return str(error.get("message") or error.get("code") or "job-pro 返回失败")
                if error:
                    return str(error)
        except json.JSONDecodeError:
            pass
        return output[:300] or f"job-pro 退出码 {returncode}"

    @classmethod
    def _find_rows(cls, payload: Any) -> list[tuple[str, dict[str, Any]]]:
        """Flatten ``find``'s company results into ``(company, position)``."""
        if not isinstance(payload, dict):
            return []
        result_rows: list[tuple[str, dict[str, Any]]] = []
        results = payload.get("results")
        if not isinstance(results, list):
            return result_rows
        for company_result in results:
            if not isinstance(company_result, dict) or company_result.get("ok") is False:
                continue
            company = str(company_result.get("company") or company_result.get("source") or "未说明")
            positions = company_result.get("positions") or company_result.get("jobs") or []
            if not isinstance(positions, list):
                continue
            for position in positions:
                if isinstance(position, dict):
                    result_rows.append((company, position))
        return result_rows

    @staticmethod
    def _failed_sources(payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return []
        failed = payload.get("failed") or []
        if not isinstance(failed, list):
            return [str(failed)]
        messages: list[str] = []
        for item in failed:
            if isinstance(item, dict):
                name = item.get("company") or item.get("source") or "来源"
                message = item.get("error") or item.get("message") or "请求失败"
                messages.append(f"{name}: {message}")
            else:
                messages.append(str(item))
        return messages

    @classmethod
    def _to_record(cls, row: dict[str, Any], *, company: str, city: str | None) -> JobRecord | None:
        title = cls._first(row, "title", "name", "position")
        detail_url = cls._first(row, "apply_url", "detail_url", "url", "link")
        post_id = cls._first(row, "post_id", "job_id", "id")
        if not title or not detail_url or not post_id:
            return None

        work_cities = str(cls._first(row, "work_cities", "city", "cities", "location") or "未说明")
        if city and city.strip() not in work_cities:
            return None
        display_city = city.strip() if city and city.strip() in work_cities else cls._first_city(work_cities)
        company_key = company.strip().lower()
        company_name = cls.COMPANY_NAMES.get(company_key, company)
        published = cls._parse_date(cls._first(row, "published_date", "publish_date", "date_posted"))
        salary_min, salary_max, salary_unit = cls._parse_salary(str(cls._first(row, "salary", "salary_text") or ""))
        return JobRecord(
            source_job_id=f"{company_key}:{post_id}",
            title=str(title),
            company_name=company_name,
            city=display_city,
            detail_url=str(detail_url),
            published_date=published,
            job_type="实习生",
            salary_min=salary_min,
            salary_max=salary_max,
            salary_unit=salary_unit,
            salary_status="disclosed" if salary_min is not None else "unknown",
            extraction_method="job_pro",
            raw_payload={"company": company, "work_cities": work_cities, "position": row},
        )

    @staticmethod
    def _first(row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _first_city(value: str) -> str:
        parts = re.split(r"[，,、/|\s]+", value.strip())
        return next((part.strip() for part in parts if part.strip()), "未说明")

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
        return (numbers[0], numbers[1] if len(numbers) > 1 else numbers[0], unit)


def resolve_job_pro_cli(command: str) -> str | None:
    """Resolve a PATH command or a path anchored to this project root."""
    configured = command.strip()
    if not configured:
        return None

    candidate = Path(configured).expanduser()
    if not candidate.is_absolute() and "/" in configured:
        candidate = PROJECT_ROOT / candidate
    if candidate.is_absolute() or "/" in configured:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate.resolve())
        return None

    executable = shutil.which(configured)
    return str(Path(executable).resolve()) if executable else None
