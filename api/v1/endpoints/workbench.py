"""Real-data job-search dashboard and personal planning endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.schemas.workbench import (
    InterviewCreate,
    InterviewListResponse,
    InterviewPatch,
    InterviewResponse,
    TodoCreate,
    TodoFilter,
    TodoListResponse,
    TodoPatch,
    TodoResponse,
    WorkbenchOverviewResponse,
)
from src.db.models import Application, InterviewEvent, JobTodo
from src.services.workbench_service import (
    InvalidWorkbenchRequest,
    WorkbenchApplicationNotFound,
    WorkbenchItemNotFound,
    WorkbenchService,
)


router = APIRouter(prefix="/workbench", tags=["workbench"])
service = WorkbenchService()


def serialize_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_application_ref(application: Application | None) -> dict | None:
    if application is None:
        return None
    return {
        "id": application.id,
        "job_id": application.job.id,
        "title": application.job.title,
        "company_name": application.job.company_name,
        "city": application.job.city,
    }


def serialize_todo(todo: JobTodo) -> dict:
    return {
        "id": todo.id,
        "title": todo.title,
        "application": serialize_application_ref(todo.application),
        "due_at": serialize_time(todo.due_at),
        "priority": todo.priority,
        "completed": todo.completed,
        "completed_at": serialize_time(todo.completed_at),
        "note": todo.note,
        "created_at": serialize_time(todo.created_at),
        "updated_at": serialize_time(todo.updated_at),
    }


def serialize_interview(interview: InterviewEvent) -> dict:
    application = interview.application
    return {
        "id": interview.id,
        "title": interview.title,
        "application": serialize_application_ref(application),
        "company_name": interview.company_name or (application.job.company_name if application else None),
        "position_title": interview.position_title or (application.job.title if application else None),
        "starts_at": serialize_time(interview.starts_at),
        "ends_at": serialize_time(interview.ends_at),
        "timezone": interview.timezone,
        "interview_format": interview.interview_format,
        "location": interview.location,
        "meeting_url": interview.meeting_url,
        "note": interview.note,
        "created_at": serialize_time(interview.created_at),
        "updated_at": serialize_time(interview.updated_at),
    }


def raise_workbench_error(exc: Exception) -> None:
    if isinstance(exc, WorkbenchItemNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    if isinstance(exc, WorkbenchApplicationNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "related_application_not_found", "message": str(exc)},
        ) from exc
    if isinstance(exc, InvalidWorkbenchRequest):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "validation_error", "message": str(exc)},
        ) from exc
    raise exc


@router.get("/overview", response_model=WorkbenchOverviewResponse, summary="查询工作台数据与真实统计")
def get_workbench_overview(session: Session = Depends(db_session)) -> dict:
    return service.overview(session)


@router.get("/todos", response_model=TodoListResponse, summary="查询求职待办")
def list_todos(
    status_filter: TodoFilter = Query(default="open", alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(db_session),
) -> dict:
    items, total = service.list_todos(session, status_filter=status_filter, page=page, limit=limit)
    return {"items": [serialize_todo(item) for item in items], "total": total, "page": page, "limit": limit}


@router.post("/todos", response_model=TodoResponse, status_code=status.HTTP_201_CREATED, summary="新增求职待办")
def create_todo(request: TodoCreate, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_todo(service.create_todo(session, request.model_dump()))
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")


@router.patch("/todos/{todo_id}", response_model=TodoResponse, summary="修改或完成求职待办")
def update_todo(todo_id: int, request: TodoPatch, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_todo(service.update_todo(session, todo_id, request.model_dump(exclude_unset=True)))
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")


@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除求职待办")
def delete_todo(todo_id: int, session: Session = Depends(db_session)) -> Response:
    try:
        service.delete_todo(session, todo_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")


@router.get("/interviews", response_model=InterviewListResponse, summary="按时间范围查询面试安排")
def list_interviews(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    session: Session = Depends(db_session),
) -> dict:
    try:
        items, total = service.list_interviews(session, start_at=start_at, end_at=end_at)
        return {"items": [serialize_interview(item) for item in items], "total": total}
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/interviews",
    response_model=InterviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增面试安排",
)
def create_interview(request: InterviewCreate, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_interview(service.create_interview(session, request.model_dump()))
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")


@router.patch("/interviews/{interview_id}", response_model=InterviewResponse, summary="修改面试安排")
def update_interview(
    interview_id: int,
    request: InterviewPatch,
    session: Session = Depends(db_session),
) -> dict:
    try:
        return serialize_interview(
            service.update_interview(session, interview_id, request.model_dump(exclude_unset=True))
        )
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除面试安排")
def delete_interview(interview_id: int, session: Session = Depends(db_session)) -> Response:
    try:
        service.delete_interview(session, interview_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        raise_workbench_error(exc)
        raise AssertionError("unreachable")
