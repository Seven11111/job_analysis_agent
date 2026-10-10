"""Schemas for local provider authentication state."""

from datetime import datetime

from pydantic import BaseModel


class BossProviderStatusResponse(BaseModel):
    provider: str
    installed: bool
    authenticated: bool
    status: str
    message: str
    active_login_id: str | None
    can_start: bool


class OfferXianshengProviderStatusResponse(BaseModel):
    provider: str
    configured: bool
    status: str
    message: str


class BossLoginStartResponse(BaseModel):
    run_id: str
    status: str
    message: str
    started_at: datetime
    ended_at: datetime | None
    reused: bool = False


class BossLoginEvent(BaseModel):
    sequence: int
    type: str
    status: str
    message: str
    timestamp: datetime
