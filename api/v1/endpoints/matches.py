"""User-triggered job matching endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.schemas.matches import MatchCreateRequest, MatchResponse
from src.services.match_service import (
    MatchGenerationFailed,
    MatchJobNotFound,
    MatchModelNotConfigured,
    MatchNotFound,
    MatchService,
)


router = APIRouter(tags=["matches"])
service = MatchService()


def raise_match_error(exc: Exception) -> None:
    if isinstance(exc, (MatchJobNotFound, MatchNotFound)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": str(exc)}) from exc
    if isinstance(exc, MatchModelNotConfigured):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_not_configured", "message": str(exc)},
        ) from exc
    if isinstance(exc, MatchGenerationFailed):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "generation_failed", "message": str(exc)},
        ) from exc
    raise exc


@router.post("/jobs/{job_id}/matches", response_model=MatchResponse, summary="分析岗位匹配度")
def analyze_job(job_id: int, request: MatchCreateRequest, session: Session = Depends(db_session)) -> dict:
    try:
        return service.analyze(session, job_id, request.resume_version_id)
    except Exception as exc:
        raise_match_error(exc)
        raise AssertionError("unreachable")


@router.get("/jobs/{job_id}/matches", response_model=list[MatchResponse], summary="查询岗位分析历史")
def list_job_matches(job_id: int, session: Session = Depends(db_session)) -> list[dict]:
    try:
        return service.history(session, job_id)
    except Exception as exc:
        raise_match_error(exc)
        raise AssertionError("unreachable")


@router.get("/matches/{match_id}", response_model=MatchResponse, summary="查询岗位分析详情")
def get_match(match_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return service.get(session, match_id)
    except Exception as exc:
        raise_match_error(exc)
        raise AssertionError("unreachable")
