"""Read-only adapter for Offer 先生's official campus-recruit API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from src.config import Settings, get_settings


API_URL = "https://openapi.offerxiansheng.com/backend-service/open/v1/campus-recruit/search"


class OfferXianshengProviderError(RuntimeError):
    """Safe, user-facing provider error without request credentials or body."""

    def __init__(self, message: str, *, code: str, http_status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class CampusRecruitNotice:
    id: str
    recruit_info_name: str | None
    company_name: str | None
    graduation_year: int | None
    recruitment_batch: str | None
    industry: str | None
    company_nature: str | None
    application_start_date: date | None
    application_end_date: date | None
    test_time: str | None
    publicity_time: str | None
    interview_start_time: str | None
    interview_end_time: str | None
    domestic_graduation_date: str | None
    domestic_graduation_time: str | None
    overseas_graduation_date: str | None
    overseas_graduation_time: str | None
    domestic_education: str | None
    overseas_education: str | None
    position_categories: list[str]
    cities: list[str]
    content: str | None
    application_url: str | None
    announcement_url: str | None
    release_source: str | None
    updated_at: str | None


@dataclass(frozen=True)
class CampusRecruitPage:
    items: list[CampusRecruitNotice]
    next_cursor: str | None
    has_more: bool


class _PlainTextParser(HTMLParser):
    """Extract text only; untrusted vendor HTML is never sent to the browser."""

    _IGNORED = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._IGNORED:
            self._ignored_depth += 1
        elif tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._IGNORED:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        elif tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


class OfferXianshengProvider:
    """Fetch one cursor page of campus recruitment notices; never persists data."""

    provider_name = "offer_xiansheng"
    MAX_CONTENT_LENGTH = 12_000

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport

    def search(self, *, filters: dict[str, Any]) -> CampusRecruitPage:
        api_key = self.settings.offer_xiansheng_api.strip()
        if not api_key:
            raise OfferXianshengProviderError(
                "未配置 Offer 先生 API Key，请在后端 .env 设置 OFFER_XIANSHENG_API 并重启服务。",
                code="provider_not_configured",
                http_status=503,
            )

        try:
            with httpx.Client(
                timeout=self.settings.offer_xiansheng_timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=self._request_payload(filters),
                )
        except httpx.TimeoutException as exc:
            raise OfferXianshengProviderError(
                "Offer 先生请求超时，请稍后重试。", code="provider_timeout", http_status=504
            ) from exc
        except httpx.RequestError as exc:
            raise OfferXianshengProviderError(
                "无法连接 Offer 先生 API，请检查网络后重试。", code="provider_unavailable"
            ) from exc

        if response.status_code == 429:
            raise OfferXianshengProviderError(
                "Offer 先生请求频率受限；已停止本次请求，请降低频率后再试。",
                code="provider_rate_limited",
                http_status=429,
            )
        if response.status_code in {401, 403}:
            raise OfferXianshengProviderError(
                "Offer 先生 API Key 无效、已撤销或当前账号无权访问。",
                code="provider_authentication_failed",
                http_status=502,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise OfferXianshengProviderError(
                f"Offer 先生 API 返回 HTTP {response.status_code}。", code="provider_unavailable"
            )

        try:
            envelope = response.json()
        except ValueError as exc:
            raise OfferXianshengProviderError(
                "Offer 先生返回了无法解析的数据。", code="provider_invalid_response"
            ) from exc
        if not isinstance(envelope, dict):
            raise OfferXianshengProviderError(
                "Offer 先生返回了不符合接口约定的数据。", code="provider_invalid_response"
            )
        if envelope.get("code") != 1000:
            self._raise_api_error(envelope.get("code"))

        data = envelope.get("data")
        rows = data.get("items") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise OfferXianshengProviderError(
                "Offer 先生响应缺少校招信息列表。", code="provider_invalid_response"
            )
        has_more = bool(data.get("hasMore"))
        cursor = data.get("nextCursor")
        if has_more and not isinstance(cursor, str):
            raise OfferXianshengProviderError(
                "Offer 先生响应缺少下一页游标。", code="provider_invalid_response"
            )
        return CampusRecruitPage(
            items=[record for row in rows if (record := self._to_notice(row)) is not None],
            next_cursor=cursor if isinstance(cursor, str) and cursor else None,
            has_more=has_more,
        )

    @staticmethod
    def _request_payload(filters: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "keyword": "keywords",
            "company": "companyName",
            "position_name": "positionName",
            "function_name": "functionName",
            "industry": "industry",
            "graduation_year": "graduationYear",
            "education_level": "educationLevel",
            "company_nature": "companyNature",
            "recruitment_batch": "recruitmentBatch",
            "start_time": "startTime",
            "end_time": "endTime",
            "cursor": "cursor",
            "limit": "limit",
        }
        payload = {
            target: (filters[source].isoformat() if isinstance(filters[source], date) else filters[source])
            for source, target in mapping.items()
            if filters.get(source) is not None
        }
        cities = [str(city).strip() for city in filters.get("cities", []) if str(city).strip()]
        if cities:
            payload["city"] = ",".join(cities)
        return payload

    @classmethod
    def _to_notice(cls, row: Any) -> CampusRecruitNotice | None:
        if not isinstance(row, dict):
            return None
        identifier = cls._string(row.get("id"))
        if not identifier:
            return None
        graduation_year = cls._integer(row.get("date"))
        return CampusRecruitNotice(
            id=identifier,
            recruit_info_name=cls._string(row.get("recruitInfoName")),
            company_name=cls._string(row.get("enterpriseName")),
            graduation_year=graduation_year,
            recruitment_batch=cls._string(row.get("tag")),
            industry=cls._string(row.get("recruitBusinessName")),
            company_nature=cls._string(row.get("companyType")),
            application_start_date=cls._date(row.get("beginTime")),
            application_end_date=cls._date(row.get("endTime")),
            test_time=cls._string(row.get("testTime")),
            publicity_time=cls._string(row.get("publicityTime")),
            interview_start_time=cls._string(row.get("interviewTime")),
            interview_end_time=cls._string(row.get("interviewTimeEnd")),
            domestic_graduation_date=cls._string(row.get("domesticGraduationDate")),
            domestic_graduation_time=cls._string(row.get("domesticGraduationTime")),
            overseas_graduation_date=cls._string(row.get("overseasGraduationDate")),
            overseas_graduation_time=cls._string(row.get("overseasGraduationTime")),
            domestic_education=cls._string(row.get("domesticEducation")),
            overseas_education=cls._string(row.get("overseasEducation")),
            position_categories=cls._split_values(row.get("recruitPosInfoNameList")),
            cities=cls._split_values(row.get("cityNameList")),
            content=cls._plain_text(row.get("content") or row.get("richText")),
            application_url=cls._https_url(row.get("url")),
            announcement_url=cls._https_url(row.get("announcementUrl")),
            release_source=cls._string(row.get("releaseSource")),
            updated_at=cls._string(row.get("updateTime")),
        )

    @staticmethod
    def _raise_api_error(api_code: Any) -> None:
        code = str(api_code)
        messages = {
            "7001": ("Offer 先生 API Key 无效。", "provider_authentication_failed", 502),
            "7002": ("Offer 先生 API Key 已撤销。", "provider_authentication_failed", 502),
            "7003": ("Offer 先生本月调用额度已用完；请等待额度恢复或联系平台。", "provider_quota_exhausted", 429),
            "7004": ("Offer 先生请求频率受限；已停止本次请求，请降低频率后再试。", "provider_rate_limited", 429),
        }
        message, error_code, http_status = messages.get(
            code, (f"Offer 先生返回业务错误（code {code[:32]}）。", "provider_request_failed", 502)
        )
        raise OfferXianshengProviderError(message, code=error_code, http_status=http_status)

    @staticmethod
    def _string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _split_values(cls, value: Any) -> list[str]:
        text = cls._string(value)
        if not text:
            return []
        return list(dict.fromkeys(item.strip() for item in re.split(r"[,，、]", text) if item.strip()))

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value is not None and str(value).strip() else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _date(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @classmethod
    def _plain_text(cls, value: Any) -> str | None:
        text = cls._string(value)
        if not text:
            return None
        parser = _PlainTextParser()
        try:
            parser.feed(text)
            parser.close()
            text = " ".join(" ".join(parser.parts).split())
        except Exception:
            text = re.sub(r"<[^>]*>", " ", text)
        return text[: cls.MAX_CONTENT_LENGTH] or None

    @staticmethod
    def _https_url(value: Any) -> str | None:
        text = str(value).strip() if value is not None else ""
        parsed = urlparse(text)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        return text[:2000]
