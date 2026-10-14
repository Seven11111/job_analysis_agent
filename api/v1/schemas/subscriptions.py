"""Contracts for local job-search subscriptions."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SubscriptionFrequency = Literal["manual", "daily", "weekdays", "weekly", "interval", "monthly"]


class SubscriptionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: dict[str, Any]
    frequency: SubscriptionFrequency = "manual"
    schedule_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int | None = Field(default=None, ge=1, le=7, description="ISO weekday: Monday=1, Sunday=7")
    interval_days: int | None = Field(default=None, ge=2, le=30)
    month_day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def validate_weekly_day(self) -> "SubscriptionCreateRequest":
        if self.frequency == "weekly" and self.weekday is None:
            self.weekday = 1
        if self.frequency == "interval" and self.interval_days is None:
            self.interval_days = 3
        if self.frequency == "monthly" and self.month_day is None:
            self.month_day = 1
        return self


class SubscriptionPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filters: dict[str, Any] | None = None
    frequency: SubscriptionFrequency | None = None
    schedule_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int | None = Field(default=None, ge=1, le=7)
    interval_days: int | None = Field(default=None, ge=2, le=30)
    month_day: int | None = Field(default=None, ge=1, le=31)
    enabled: bool | None = None


class SubscriptionRunSummaryResponse(BaseModel):
    id: int
    subscription_id: int
    trigger: Literal["manual", "scheduled"]
    status: Literal["running", "succeeded", "no_new", "partial_failed", "failed", "interrupted"]
    total_count: int
    new_count: int
    provider_results: list[dict[str, Any]]
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class JobSubscriptionResponse(BaseModel):
    id: int
    name: str
    filters: dict[str, Any]
    frequency: SubscriptionFrequency
    schedule_time: str
    weekday: int | None
    interval_days: int | None
    month_day: int | None
    timezone: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    latest_run: SubscriptionRunSummaryResponse | None = None


class SubscriptionListResponse(BaseModel):
    items: list[JobSubscriptionResponse]


class SubscriptionRunItemResponse(BaseModel):
    id: int
    provider: str
    is_new: bool
    job: dict[str, Any]
    saved_job_id: int | None


class SubscriptionRunDetailResponse(SubscriptionRunSummaryResponse):
    items: list[SubscriptionRunItemResponse]
    total_items: int
    page: int
    limit: int
    preview_expired: bool = False


class SubscriptionRunListResponse(BaseModel):
    items: list[SubscriptionRunSummaryResponse]
    total: int
    page: int
    limit: int


class SubscriptionSaveResponse(BaseModel):
    item_id: int
    job_id: int
    application_id: int
    already_saved: bool
