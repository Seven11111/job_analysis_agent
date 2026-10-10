"""Local provider status and user-initiated login workflows."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from api.v1.schemas.providers import (
    BossLoginStartResponse,
    BossProviderStatusResponse,
    OfferXianshengProviderStatusResponse,
)
from src.config import get_settings
from src.services.boss_cli import BossCliIncompatible, BossCliUnavailable
from src.services.boss_login_service import BossLoginService, LoginRunNotFound
from src.services.campus_recruit_service import CampusRecruitService


router = APIRouter(prefix="/providers", tags=["providers"])
service = BossLoginService()


@router.get("/boss/status", response_model=BossProviderStatusResponse, summary="查询 BOSS 登录状态")
def boss_status() -> dict:
    return service.status()


@router.get(
    "/offer-xiansheng/status",
    response_model=OfferXianshengProviderStatusResponse,
    summary="查询 Offer 先生 API 配置状态",
)
def offer_xiansheng_status() -> dict:
    return CampusRecruitService(settings=get_settings()).status()


@router.post("/boss/login/start", response_model=BossLoginStartResponse, summary="启动本机 BOSS 登录流程")
def start_boss_login() -> dict:
    try:
        run, reused = service.start()
    except BossCliUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "provider_not_installed", "message": str(exc)},
        ) from exc
    except BossCliIncompatible as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "provider_incompatible", "message": str(exc)},
        ) from exc
    result = service.describe(run)
    result["reused"] = reused
    return result


@router.get("/boss/login/{run_id}/events", summary="订阅 BOSS 登录进度 SSE")
async def boss_login_events(run_id: str) -> StreamingResponse:
    try:
        service.events(run_id)
    except LoginRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "login_run_not_found", "message": "登录任务不存在或已过期"},
        ) from exc

    async def event_stream():
        cursor = 0
        while True:
            try:
                events, terminal = service.events(run_id, cursor)
            except LoginRunNotFound:
                return
            for event in events:
                cursor = event["sequence"]
                yield f"event: boss_login\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            if terminal:
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/boss/login/{run_id}/cancel", response_model=BossLoginStartResponse, summary="取消 BOSS 登录流程")
def cancel_boss_login(run_id: str) -> dict:
    try:
        run = service.cancel(run_id)
    except LoginRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "login_run_not_found", "message": "登录任务不存在或已过期"},
        ) from exc
    result = service.describe(run)
    result["reused"] = False
    return result
