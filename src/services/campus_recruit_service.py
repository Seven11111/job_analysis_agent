"""Application service for temporary Offer 先生 campus-recruit searches."""

from __future__ import annotations

from api.v1.schemas.campus_recruit import CampusRecruitSearchRequest
from src.config import Settings, get_settings
from src.data_provider.offer_xiansheng_provider import OfferXianshengProvider


class CampusRecruitService:
    """Search notice-level records without writing them to the internship job database."""

    def __init__(self, settings: Settings | None = None, provider: OfferXianshengProvider | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or OfferXianshengProvider(self.settings)

    def status(self) -> dict:
        configured = bool(self.settings.offer_xiansheng_api.strip())
        return {
            "provider": "offer_xiansheng",
            "configured": configured,
            "status": "configured" if configured else "not_configured",
            "message": "API Key 已配置；实际可用性将在搜索时确认。" if configured else "请在后端 .env 配置 OFFER_XIANSHENG_API。",
        }

    def search(self, request: CampusRecruitSearchRequest) -> dict:
        page = self.provider.search(filters=request.model_dump(exclude_none=True))
        return {
            "items": [item.__dict__ for item in page.items],
            "count": len(page.items),
            "limit": request.limit,
            "next_cursor": page.next_cursor,
            "has_more": page.has_more,
            "source": {
                "provider": "offer_xiansheng",
                "name": "Offer 先生校招资讯",
                "data_type": "campus_recruit_notice",
            },
        }
