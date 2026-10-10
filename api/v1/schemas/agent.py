"""Contracts for the local job-search assistant and its streamed runs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class AgentSessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    session_id: int | None = Field(default=None, gt=0)
    search_providers: list[Literal["boss_agent_cli", "job_pro"]] | None = Field(default=None, max_length=2)


class AgentActionResolveRequest(BaseModel):
    confirm: bool


class AgentProfilePatch(BaseModel):
    school: str | None = Field(default=None, max_length=200)
    major: str | None = Field(default=None, max_length=200)
    education: str | None = Field(default=None, max_length=64)
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)
    target_directions: list[str] | None = Field(default=None, max_length=20)
    target_cities: list[str] | None = Field(default=None, max_length=20)
    available_period: str | None = Field(default=None, max_length=128)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    internship_months: float | None = Field(default=None, ge=0)
    desired_industries: list[str] | None = Field(default=None, max_length=20)


class AgentMessageResponse(BaseModel):
    id: int
    role: str
    content: str | None
    structured_content: dict[str, Any] | None = None
    created_at: datetime


class AgentEventResponse(BaseModel):
    id: int
    run_id: str
    sequence: int
    event_type: str
    name: str | None
    status: str
    payload: dict[str, Any] | None = None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class AgentSessionSummary(BaseModel):
    id: int
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class AgentSessionDetail(AgentSessionSummary):
    messages: list[AgentMessageResponse]
    events: list[AgentEventResponse]
