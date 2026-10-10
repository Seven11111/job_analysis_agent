"""Job Agent sessions, native tool-calling stream and confirmed actions."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.schemas.agent import (
    AgentActionResolveRequest,
    AgentChatRequest,
    AgentEventResponse,
    AgentMessageResponse,
    AgentSessionCreate,
    AgentSessionDetail,
    AgentSessionRename,
    AgentSessionSummary,
)
from src.db.models import AgentMessage, AgentRunEvent, AgentSession
from src.services.agent_service import (
    AGENT_TOOLS,
    AgentActionConflict,
    AgentActionNotFound,
    AgentRunNotFound,
    AgentService,
    AgentSessionNotFound,
)


router = APIRouter(prefix="/agent", tags=["job-agent"])
service = AgentService()


def _message_response(message: AgentMessage) -> dict:
    try:
        structured = json.loads(message.structured_content) if message.structured_content else None
    except json.JSONDecodeError:
        structured = None
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content_text,
        "structured_content": structured,
        "created_at": message.created_at,
    }


def _event_response(event: AgentRunEvent) -> dict:
    try:
        payload = json.loads(event.payload) if event.payload else None
    except json.JSONDecodeError:
        payload = None
    return {
        "id": event.id,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "name": event.name,
        "status": event.status,
        "payload": payload,
        "error_message": event.error_message,
        "started_at": event.started_at,
        "completed_at": event.completed_at,
    }


def _session_summary(record: AgentSession) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "message_count": getattr(record, "_message_count", len(record.messages) if "messages" in record.__dict__ else 0),
    }


@router.get("/tools", summary="查看 Agent 可用工具")
def list_agent_tools() -> list[dict]:
    return [
        {
            "name": item["function"]["name"],
            "description": item["function"]["description"],
            "parameters": item["function"]["parameters"],
        }
        for item in AGENT_TOOLS
    ]


@router.get("/sessions", response_model=list[AgentSessionSummary], summary="查询历史对话")
def list_sessions(session: Session = Depends(db_session)) -> list[dict]:
    return [_session_summary(item) for item in service.list_sessions(session)]


@router.post("/sessions", response_model=AgentSessionSummary, status_code=status.HTTP_201_CREATED, summary="新建对话")
def create_session(request: AgentSessionCreate, session: Session = Depends(db_session)) -> dict:
    return _session_summary(service.create_session(session, request.title))


@router.get("/sessions/{session_id}", response_model=AgentSessionDetail, summary="读取对话及运行事件")
def get_session(session_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        record = service.get_session(session, session_id)
        events = service.events(session, session_id, limit=200)
        return {
            **_session_summary(record),
            "messages": [_message_response(item) for item in sorted(record.messages, key=lambda item: item.id)],
            "events": [_event_response(item) for item in events],
        }
    except AgentSessionNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


@router.patch("/sessions/{session_id}", response_model=AgentSessionSummary, summary="重命名对话")
def rename_session(session_id: int, request: AgentSessionRename, session: Session = Depends(db_session)) -> dict:
    try:
        return _session_summary(service.rename_session(session, session_id, request.title))
    except AgentSessionNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


@router.get("/sessions/{session_id}/events", response_model=list[AgentEventResponse], summary="查询对话运行事件")
def list_events(
    session_id: int,
    run_id: str | None = Query(default=None, max_length=64),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    session: Session = Depends(db_session),
) -> list[dict]:
    if after_sequence and not run_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "run_id_required", "message": "使用 after_sequence 时必须同时提供 run_id。"},
        )
    try:
        return [_event_response(item) for item in service.events(
            session, session_id, run_id=run_id, after_sequence=after_sequence, limit=limit
        )]
    except AgentSessionNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc


@router.post("/chat/stream", summary="发送消息并通过 SSE 流式接收 Agent 回答")
def chat_stream(request: AgentChatRequest, session: Session = Depends(db_session)) -> StreamingResponse:
    if request.session_id is not None:
        try:
            service.get_session(session, request.session_id)
            pending_actions = service.pending_actions(session, request.session_id)
        except AgentSessionNotFound as exc:
            raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": str(exc)}) from exc
        if pending_actions:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "pending_action_confirmation",
                    "message": "请先确认或取消当前对话中的待处理操作，再继续发送消息。",
                    "pending_action_ids": [event.id for event in pending_actions],
                },
            )
        if service.is_session_running(request.session_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "run_in_progress",
                    "message": "当前对话仍在处理中，请等待本轮回答完成后再发送。",
                },
            )
    return StreamingResponse(
        service.stream(
            session,
            message=request.message.strip(),
            session_id=request.session_id,
            search_providers=request.search_providers,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/runs/{run_id}/cancel", summary="停止正在运行的 Agent 回答")
def cancel_run(session_id: int, run_id: str, session: Session = Depends(db_session)) -> dict[str, str]:
    try:
        return service.cancel_run(session, session_id=session_id, run_id=run_id)
    except AgentSessionNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": str(exc)}) from exc
    except AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "run_not_found", "message": str(exc)}) from exc


@router.post("/actions/{event_id}/resolve", summary="确认或取消 Agent 待执行操作")
def resolve_action(
    event_id: int,
    request: AgentActionResolveRequest,
    session: Session = Depends(db_session),
) -> dict:
    try:
        return service.resolve_action(session, event_id=event_id, confirm=request.confirm)
    except AgentActionNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except AgentActionConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "already_resolved", "message": str(exc)}) from exc
