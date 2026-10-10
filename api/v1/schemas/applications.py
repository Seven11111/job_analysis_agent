"""API schemas for saved jobs and user-maintained application status."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ApplicationTab = Literal["all", "pending_analysis", "analyzed"]


class StatusDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default="blue", max_length=16)
    sort_order: int = Field(default=0, ge=0)
    is_success: bool = False
    is_terminal: bool = False


class StatusDefinitionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)
    sort_order: int | None = Field(default=None, ge=0)
    is_success: bool | None = None
    is_terminal: bool | None = None
    enabled: bool | None = None


class StatusDefinitionResponse(BaseModel):
    id: int
    name: str
    color: str | None
    sort_order: int
    is_success: bool
    is_terminal: bool
    enabled: bool


class ApplicationCreate(BaseModel):
    job_id: int = Field(gt=0)
    status_id: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=2000)


class ApplicationPatch(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ApplicationStatusChange(BaseModel):
    to_status_id: int = Field(gt=0)
    effective_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class ApplicationStatusEventPatch(BaseModel):
    to_status_id: int | None = Field(default=None, gt=0)
    effective_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class ApplicationJobResponse(BaseModel):
    id: int
    title: str
    company_name: str
    city: str
    published_date: str | None
    detail_url: str


class ApplicationResponse(BaseModel):
    id: int
    job: ApplicationJobResponse
    current_status: StatusDefinitionResponse
    saved_at: datetime
    last_status_changed_at: datetime | None
    note: str | None
    latest_match: dict | None = None


class StatusEventResponse(BaseModel):
    id: int
    from_status: StatusDefinitionResponse | None
    to_status: StatusDefinitionResponse
    effective_at: datetime
    note: str | None
    created_at: datetime


class ApplicationDetailResponse(ApplicationResponse):
    timeline: list[StatusEventResponse]


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int
    limit: int


class ApplicationStatusResponse(BaseModel):
    application: ApplicationResponse
    status_event: StatusEventResponse
