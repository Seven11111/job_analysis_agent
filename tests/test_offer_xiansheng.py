from datetime import date
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from src.config import Settings
from src.data_provider.offer_xiansheng_provider import (
    API_URL,
    OfferXianshengProvider,
    OfferXianshengProviderError,
)
from api.v1.schemas.campus_recruit import CampusRecruitSearchRequest


def sample_notice() -> dict:
    return {
        "id": "encrypted-id-1",
        "recruitInfoName": "2027届秋招",
        "enterpriseName": "示例科技有限公司",
        "date": 2027,
        "tag": "秋招",
        "recruitBusinessName": "互联网/IT",
        "companyType": "民营企业",
        "beginTime": "2026-08-01",
        "endTime": "2026-10-31",
        "domesticEducation": "本科及以上",
        "overseasEducation": "硕士及以上",
        "recruitPosInfoNameList": "技术岗,产品岗,技术岗",
        "cityNameList": "杭州,上海",
        "content": "<p>招聘详情</p><script>ignore()</script><p>请查看岗位原文</p>",
        "url": "https://jobs.example.com/apply",
        "announcementUrl": "https://jobs.example.com/notice",
        "releaseSource": "官网",
        "updateTime": "2026-08-31 09:30:00",
    }


def test_provider_maps_notice_fields_and_sends_secret_only_as_bearer_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"code": 1000, "message": "success", "data": {"items": [sample_notice()], "hasMore": True, "nextCursor": "next-page-token"}},
        )

    provider = OfferXianshengProvider(
        Settings(_env_file=None, offer_xiansheng_api="local-test-key"),
        transport=httpx.MockTransport(handler),
    )
    page = provider.search(filters={"keyword": "Agent", "company": "示例科技", "cities": ["杭州", "上海"], "limit": 20})

    assert captured["url"] == API_URL
    assert captured["authorization"] == "Bearer local-test-key"
    assert captured["payload"] == {"keywords": "Agent", "companyName": "示例科技", "limit": 20, "city": "杭州,上海"}
    assert page.has_more is True
    assert page.next_cursor == "next-page-token"
    assert page.items[0].graduation_year == 2027
    assert page.items[0].recruit_info_name == "2027届秋招"
    assert page.items[0].position_categories == ["技术岗", "产品岗"]
    assert page.items[0].cities == ["杭州", "上海"]
    assert page.items[0].application_start_date == date(2026, 8, 1)
    assert "ignore()" not in (page.items[0].content or "")
    assert "<script>" not in (page.items[0].content or "")


def test_provider_maps_date_filters_to_official_camel_case():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"code": 1000, "data": {"items": [], "hasMore": False, "nextCursor": None}})

    provider = OfferXianshengProvider(
        Settings(_env_file=None, offer_xiansheng_api="local-test-key"),
        transport=httpx.MockTransport(handler),
    )
    provider.search(filters={"keyword": "算法", "start_time": date(2026, 8, 1), "end_time": date(2026, 10, 1), "limit": 50})

    assert captured == {
        "keywords": "算法",
        "startTime": "2026-08-01",
        "endTime": "2026-10-01",
        "limit": 50,
    }


def test_provider_does_not_retry_quota_or_rate_limit_errors():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 7003, "message": "quota exhausted"})

    provider = OfferXianshengProvider(
        Settings(_env_file=None, offer_xiansheng_api="local-test-key"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(OfferXianshengProviderError) as error:
        provider.search(filters={"keyword": "后端", "limit": 20})

    assert calls == 1
    assert error.value.code == "provider_quota_exhausted"
    assert "额度已用完" in str(error.value)


def test_provider_without_key_fails_before_network_request():
    provider = OfferXianshengProvider(Settings(_env_file=None, offer_xiansheng_api=""))
    with pytest.raises(OfferXianshengProviderError) as error:
        provider.search(filters={"keyword": "后端"})
    assert error.value.code == "provider_not_configured"
    assert error.value.http_status == 503


def test_campus_recruit_search_requires_a_filter_and_valid_dates():
    with pytest.raises(ValueError, match="至少填写一个搜索条件"):
        CampusRecruitSearchRequest.model_validate({})
    with pytest.raises(ValueError, match="不能晚于"):
        CampusRecruitSearchRequest.model_validate({"company": "示例", "start_time": "2026-10-01", "end_time": "2026-09-01"})


def test_settings_load_the_existing_offer_xiansheng_env_name(monkeypatch):
    monkeypatch.setenv("OFFER_XIANSHENG_API", "private-test-value")
    settings = Settings(_env_file=None)
    assert settings.offer_xiansheng_api == "private-test-value"


def test_provider_status_does_not_echo_the_api_key(monkeypatch):
    from api.v1.endpoints import providers as endpoint

    monkeypatch.setattr(
        endpoint,
        "get_settings",
        lambda: Settings(_env_file=None, offer_xiansheng_api="private-test-value"),
    )
    response = TestClient(create_app()).get("/api/v1/providers/offer-xiansheng/status")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "private-test-value" not in response.text


def test_campus_recruit_endpoint_is_separate_and_returns_cursor_metadata(monkeypatch):
    from api.v1.endpoints import campus_recruit as endpoint

    class FakeService:
        def search(self, request):
            return {
                "items": [{
                    "id": "encrypted-id-1",
                    "recruit_info_name": "2027届秋招",
                    "company_name": "示例科技有限公司",
                    "graduation_year": 2027,
                    "recruitment_batch": "秋招",
                    "industry": None,
                    "company_nature": None,
                    "application_start_date": "2026-08-01",
                    "application_end_date": "2026-10-31",
                    "test_time": None,
                    "publicity_time": None,
                    "interview_start_time": None,
                    "interview_end_time": None,
                    "domestic_graduation_date": None,
                    "domestic_graduation_time": None,
                    "overseas_graduation_date": None,
                    "overseas_graduation_time": None,
                    "domestic_education": None,
                    "overseas_education": None,
                    "position_categories": ["技术岗"],
                    "cities": ["杭州"],
                    "content": "招聘公告详情",
                    "application_url": "https://jobs.example.com/apply",
                    "announcement_url": "https://jobs.example.com/notice",
                    "release_source": "官网",
                    "updated_at": "2026-08-31 09:30:00",
                }],
                "count": 1,
                "limit": request.limit,
                "next_cursor": "cursor-2",
                "has_more": True,
                "source": {"provider": "offer_xiansheng", "name": "Offer 先生校招资讯", "data_type": "campus_recruit_notice"},
            }

    monkeypatch.setattr(endpoint, "service", FakeService())
    client = TestClient(create_app())
    response = client.post("/api/v1/campus-recruit/search", json={"company": "示例", "limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["data_type"] == "campus_recruit_notice"
    assert payload["items"][0]["graduation_year"] == 2027
    assert payload["has_more"] is True
    assert payload["next_cursor"] == "cursor-2"
