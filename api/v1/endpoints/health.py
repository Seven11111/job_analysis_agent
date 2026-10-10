"""Health endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from src.config import get_settings
from src.db.session import get_engine
from src.services.boss_cli import (
    BossCliIncompatible,
    BossCliUnavailable,
    compatibility_problems,
    inspect_boss_cli,
)
from src.data_provider.job_pro_provider import resolve_job_pro_cli

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database: str
    providers: dict[str, str]


@router.get("/health", response_model=HealthResponse, summary="健康检查")
def health() -> HealthResponse:
    settings = get_settings()
    database_status = "ok"
    try:
        with get_engine(settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    try:
        boss_cli = inspect_boss_cli(settings.boss_cli_command)
        provider_status_boss = (
            "incompatible"
            if compatibility_problems(boss_cli, browser_source=settings.boss_browser_source)
            else "available"
        )
    except BossCliUnavailable:
        provider_status_boss = "not_installed"
    except BossCliIncompatible:
        provider_status_boss = "incompatible"

    provider_status = {
        "fixture": "available",
        "manual_link": "available",
        "boss_agent_cli": provider_status_boss,
        "job_pro": "available" if resolve_job_pro_cli(settings.job_pro_command) else "not_installed",
        "offer_xiansheng": "configured" if settings.offer_xiansheng_api.strip() else "not_configured",
    }
    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        timestamp=datetime.now(timezone.utc),
        database=database_status,
        providers=provider_status,
    )
