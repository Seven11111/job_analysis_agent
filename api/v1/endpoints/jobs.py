"""Search and inspect normalized job records."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.schemas.jobs import (
    JobDetailResponse,
    JobImportConfirmRequest,
    JobImportPreviewRequest,
    JobImportPreviewResponse,
    JobSearchRequest,
    JobSearchResponse,
)
from src.services.job_service import (
    InvalidImport,
    JobProviderUnavailable,
    JobSearchService,
    SearchResultNotFound,
)
from src.llm.adapter import LLMGenerationError, LLMNotConfiguredError


router = APIRouter(prefix="/jobs", tags=["jobs"])
service = JobSearchService()


@router.post("/search", response_model=JobSearchResponse, summary="搜索岗位")
def search_jobs(request: JobSearchRequest, session: Session = Depends(db_session)) -> JobSearchResponse:
    try:
        return service.search(session, request)
    except JobProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "provider_unavailable", "message": str(exc), "quality": exc.quality},
        ) from exc


@router.post("/import/preview", response_model=JobImportPreviewResponse, summary="预览岗位链接提取结果")
def preview_job_import(request: JobImportPreviewRequest) -> dict:
    try:
        return service.preview_import(request.detail_url)
    except InvalidImport as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_job_link", "message": str(exc)},
        ) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_not_configured", "message": str(exc)},
        ) from exc
    except LLMGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "generation_failed", "message": str(exc)},
        ) from exc


@router.post("/import/{preview_token}/confirm", response_model=JobDetailResponse, summary="确认并保存岗位链接导入")
def confirm_job_import(
    preview_token: str,
    request: JobImportConfirmRequest,
    session: Session = Depends(db_session),
) -> dict:
    try:
        return service.confirm_import(session, preview_token, request.model_dump(exclude_unset=True))
    except InvalidImport as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "incomplete_job", "message": str(exc)},
        ) from exc
    except SearchResultNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "preview_expired", "message": str(exc)},
        ) from exc


@router.get("/search-results/{result_token}", response_model=JobDetailResponse, summary="查询临时搜索结果详情")
def get_search_result(result_token: str) -> dict:
    try:
        return service.get_search_result(result_token)
    except SearchResultNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "search_result_expired", "message": str(exc)},
        ) from exc


@router.post("/search-results/{result_token}/save", response_model=JobDetailResponse, summary="确认保存临时搜索结果")
def save_search_result(result_token: str, session: Session = Depends(db_session)) -> dict:
    try:
        return service.save_search_result(session, result_token)
    except SearchResultNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "search_result_expired", "message": str(exc)},
        ) from exc


@router.get("/{job_id}", response_model=JobDetailResponse, summary="查询岗位详情")
def get_job(job_id: int, session: Session = Depends(db_session)) -> JobDetailResponse:
    result = service.get_detail(session, job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "岗位不存在"},
        )
    return result
