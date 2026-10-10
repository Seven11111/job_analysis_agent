"""Official campus-recruit notice search; separate from internship jobs."""

from fastapi import APIRouter, HTTPException

from api.v1.schemas.campus_recruit import CampusRecruitSearchRequest, CampusRecruitSearchResponse
from src.data_provider.offer_xiansheng_provider import OfferXianshengProviderError
from src.services.campus_recruit_service import CampusRecruitService


router = APIRouter(prefix="/campus-recruit", tags=["campus-recruit"])
service = CampusRecruitService()


@router.post("/search", response_model=CampusRecruitSearchResponse, summary="搜索 Offer 先生校招资讯")
def search_campus_recruit(request: CampusRecruitSearchRequest) -> dict:
    try:
        return service.search(request)
    except OfferXianshengProviderError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
