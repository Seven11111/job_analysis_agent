"""Saved jobs and user-maintained application lifecycle endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.schemas.applications import (
    ApplicationCreate,
    ApplicationDetailResponse,
    ApplicationJobResponse,
    ApplicationListResponse,
    ApplicationPatch,
    ApplicationResponse,
    ApplicationStatusChange,
    ApplicationStatusEventPatch,
    ApplicationStatusResponse,
    StatusDefinitionCreate,
    StatusDefinitionPatch,
    StatusDefinitionResponse,
    StatusEventResponse,
)
from src.db.models import Application, ApplicationStatusDefinition, ApplicationStatusEvent
from src.services.application_service import (
    ApplicationNotFound,
    ApplicationService,
    DuplicateApplication,
    JobNotFound,
    StatusNotFound,
)

router = APIRouter(prefix="/applications", tags=["applications"])
service = ApplicationService()


def serialize_status(status_definition: ApplicationStatusDefinition | None) -> dict | None:
    if status_definition is None:
        return None
    return {
        "id": status_definition.id,
        "name": status_definition.name,
        "color": status_definition.color,
        "sort_order": status_definition.sort_order,
        "is_success": status_definition.is_success,
        "is_terminal": status_definition.is_terminal,
        "enabled": status_definition.enabled,
    }


def serialize_job(application: Application) -> dict:
    return {
        "id": application.job.id,
        "title": application.job.title,
        "company_name": application.job.company_name,
        "city": application.job.city,
        "published_date": application.job.published_date.isoformat() if application.job.published_date else None,
        "detail_url": application.job.detail_url,
    }


def serialize_application(application: Application) -> dict:
    return {
        "id": application.id,
        "job": serialize_job(application),
        "current_status": serialize_status(application.current_status),
        "saved_at": application.saved_at,
        "last_status_changed_at": application.last_status_changed_at,
        "note": application.note,
        "latest_match": None,
    }


def serialize_event(event: ApplicationStatusEvent) -> dict:
    return {
        "id": event.id,
        "from_status": serialize_status(event.from_status),
        "to_status": serialize_status(event.to_status),
        "effective_at": event.effective_at,
        "note": event.note,
        "created_at": event.created_at,
    }


def raise_service_error(exc: Exception) -> None:
    if isinstance(exc, (ApplicationNotFound, JobNotFound, StatusNotFound)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    if isinstance(exc, DuplicateApplication):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "already_exists", "message": str(exc)},
        ) from exc
    raise exc


@router.get("/status-definitions", response_model=list[StatusDefinitionResponse], summary="查询投递状态定义")
def list_status_definitions(session: Session = Depends(db_session)) -> list[dict]:
    return [serialize_status(item) for item in service.statuses(session)]


@router.post("/status-definitions", response_model=StatusDefinitionResponse, summary="创建自定义投递状态")
def create_status_definition(
    request: StatusDefinitionCreate, session: Session = Depends(db_session)
) -> dict:
    try:
        return serialize_status(service.create_status(session, **request.model_dump()))
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.patch("/status-definitions/{status_id}", response_model=StatusDefinitionResponse, summary="修改投递状态")
def update_status_definition(
    status_id: int, request: StatusDefinitionPatch, session: Session = Depends(db_session)
) -> dict:
    try:
        return serialize_status(
            service.update_status(session, status_id, **request.model_dump(exclude_unset=True))
        )
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.delete("/status-definitions/{status_id}", response_model=StatusDefinitionResponse, summary="停用投递状态")
def disable_status_definition(status_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_status(service.disable_status(session, status_id))
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.get("", response_model=ApplicationListResponse, summary="查询已收藏岗位")
def list_applications(
    tab: str = Query(default="all", pattern="^(all|pending_analysis|analyzed)$"),
    status_id: int | None = Query(default=None, gt=0),
    q: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(db_session),
) -> dict:
    items, total = service.list(
        session,
        tab=tab,
        status_id=status_id,
        q=q,
        city=city,
        page=page,
        limit=limit,
    )
    return {"items": [serialize_application(item) for item in items], "total": total, "page": page, "limit": limit}


@router.post("", response_model=ApplicationResponse, summary="收藏岗位")
def create_application(request: ApplicationCreate, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_application(
            service.create(session, job_id=request.job_id, status_id=request.status_id, note=request.note)
        )
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.get("/{application_id}", response_model=ApplicationDetailResponse, summary="查询收藏岗位详情")
def get_application(application_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        application = service.get(session, application_id)
        timeline = service.repository.list_timeline(session, application_id)
        return {**serialize_application(application), "timeline": [serialize_event(event) for event in timeline]}
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.patch("/{application_id}", response_model=ApplicationResponse, summary="修改收藏备注")
def update_application(
    application_id: int, request: ApplicationPatch, session: Session = Depends(db_session)
) -> dict:
    try:
        return serialize_application(service.update_note(session, application_id, request.note))
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT, summary="从岗位管理移除岗位")
def delete_application(application_id: int, session: Session = Depends(db_session)) -> Response:
    try:
        service.delete(session, application_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.post("/{application_id}/status", response_model=ApplicationStatusResponse, summary="修改投递状态")
def change_application_status(
    application_id: int, request: ApplicationStatusChange, session: Session = Depends(db_session)
) -> dict:
    try:
        application, event = service.change_status(
            session,
            application_id,
            to_status_id=request.to_status_id,
            effective_at=request.effective_at,
            note=request.note,
        )
        return {"application": serialize_application(application), "status_event": serialize_event(event)}
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.get("/{application_id}/timeline", response_model=list[StatusEventResponse], summary="查询状态时间线")
def application_timeline(application_id: int, session: Session = Depends(db_session)) -> list[dict]:
    try:
        service.get(session, application_id)
        return [serialize_event(event) for event in service.repository.list_timeline(session, application_id)]
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.patch(
    "/{application_id}/timeline/{event_id}",
    response_model=ApplicationStatusResponse,
    summary="修订状态历史的状态、时间或备注",
)
def update_application_timeline_event(
    application_id: int,
    event_id: int,
    request: ApplicationStatusEventPatch,
    session: Session = Depends(db_session),
) -> dict:
    try:
        application, event = service.update_status_event(
            session,
            application_id,
            event_id,
            to_status_id=request.to_status_id,
            effective_at=request.effective_at,
            note=request.note,
            update_fields=set(request.model_fields_set),
        )
        return {"application": serialize_application(application), "status_event": serialize_event(event)}
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")
