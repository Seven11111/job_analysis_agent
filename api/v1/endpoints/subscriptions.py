"""CRUD and run endpoints for local job-search subscriptions."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.endpoints.jobs import service as job_search_service
from api.v1.schemas.subscriptions import (
    JobSubscriptionResponse,
    SubscriptionCreateRequest,
    SubscriptionListResponse,
    SubscriptionPatchRequest,
    SubscriptionRunDetailResponse,
    SubscriptionRunListResponse,
    SubscriptionRunSummaryResponse,
    SubscriptionSaveResponse,
)
from src.services.subscription_service import (
    InvalidSubscription,
    JobSubscriptionService,
    SubscriptionBusy,
    SubscriptionNotFound,
)


router = APIRouter(prefix="/subscriptions", tags=["job subscriptions"])
service = JobSubscriptionService(job_search_service)


def raise_service_error(exc: Exception) -> None:
    if isinstance(exc, SubscriptionNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "subscription_not_found", "message": str(exc)},
        ) from exc
    if isinstance(exc, SubscriptionBusy):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "subscription_running", "message": str(exc)},
        ) from exc
    if isinstance(exc, InvalidSubscription):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_subscription", "message": str(exc)},
        ) from exc
    raise exc


@router.get("", response_model=SubscriptionListResponse, summary="查询岗位查新配置")
def list_subscriptions(session: Session = Depends(db_session)) -> dict:
    return {"items": service.list(session)}


@router.post("", response_model=JobSubscriptionResponse, status_code=status.HTTP_201_CREATED, summary="创建岗位查新")
def create_subscription(request: SubscriptionCreateRequest, session: Session = Depends(db_session)) -> dict:
    try:
        created = service.create(session, **request.model_dump())
        return service.get(session, created.id)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.get("/{subscription_id}", response_model=JobSubscriptionResponse, summary="查询岗位查新详情")
def get_subscription(subscription_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return service.get(session, subscription_id)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.patch("/{subscription_id}", response_model=JobSubscriptionResponse, summary="修改或暂停岗位查新")
def update_subscription(
    subscription_id: int,
    request: SubscriptionPatchRequest,
    session: Session = Depends(db_session),
) -> dict:
    try:
        updated = service.update(session, subscription_id, request.model_dump(exclude_unset=True))
        return service.get(session, updated.id)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除岗位查新")
def delete_subscription(subscription_id: int, session: Session = Depends(db_session)) -> Response:
    try:
        service.delete(session, subscription_id)
    except Exception as exc:
        raise_service_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{subscription_id}/runs",
    response_model=SubscriptionRunSummaryResponse,
    summary="立即执行一次岗位查新",
)
def run_subscription(subscription_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return service.run(session, subscription_id, trigger="manual")
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.get("/{subscription_id}/runs", response_model=SubscriptionRunListResponse, summary="查询岗位查新记录")
def list_subscription_runs(
    subscription_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(db_session),
) -> dict:
    try:
        return service.runs(session, subscription_id, page=page, limit=limit)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/{subscription_id}/runs/{run_id}",
    response_model=SubscriptionRunDetailResponse,
    summary="查询岗位查新结果",
)
def get_subscription_run(
    subscription_id: int,
    run_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(db_session),
) -> dict:
    try:
        return service.run_detail(session, subscription_id, run_id, page=page, limit=limit)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/items/{item_id}/save",
    response_model=SubscriptionSaveResponse,
    summary="确认保存订阅岗位到岗位管理",
)
def save_subscription_item(item_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return service.save_item(session, item_id)
    except Exception as exc:
        raise_service_error(exc)
        raise AssertionError("unreachable")
