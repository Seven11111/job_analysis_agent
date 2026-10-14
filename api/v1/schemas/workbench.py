"""Contracts for the personal job-search workbench."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Priority = Literal["high", "normal", "low"]
InterviewFormat = Literal["online", "in_person", "phone", "unknown"]
TodoFilter = Literal["all", "open", "completed"]


def require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("时间必须包含时区，例如 +08:00")
    return value


class WorkbenchApplicationRef(BaseModel):
    id: int
    job_id: int
    title: str
    company_name: str
    city: str


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    application_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    priority: Priority = "normal"
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("due_at")
    @classmethod
    def validate_due_at_timezone(cls, value: datetime | None) -> datetime | None:
        return require_timezone(value)


class TodoPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    application_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    priority: Priority | None = None
    completed: bool | None = None
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("due_at")
    @classmethod
    def validate_due_at_timezone(cls, value: datetime | None) -> datetime | None:
        return require_timezone(value)


class TodoResponse(BaseModel):
    id: int
    title: str
    application: WorkbenchApplicationRef | None
    due_at: datetime | None
    priority: Priority
    completed: bool
    completed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class TodoListResponse(BaseModel):
    items: list[TodoResponse]
    total: int
    page: int
    limit: int


class InterviewCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    application_id: int | None = Field(default=None, gt=0)
    company_name: str | None = Field(default=None, max_length=200)
    position_title: str | None = Field(default=None, max_length=300)
    starts_at: datetime
    ends_at: datetime | None = None
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    interview_format: InterviewFormat = "unknown"
    location: str | None = Field(default=None, max_length=500)
    meeting_url: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime | None) -> datetime | None:
        return require_timezone(value)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class InterviewPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    application_id: int | None = Field(default=None, gt=0)
    company_name: str | None = Field(default=None, max_length=200)
    position_title: str | None = Field(default=None, max_length=300)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    interview_format: InterviewFormat | None = None
    location: str | None = Field(default=None, max_length=500)
    meeting_url: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=4000)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def validate_datetime_timezone(cls, value: datetime | None) -> datetime | None:
        return require_timezone(value)


class InterviewApplicationRef(BaseModel):
    id: int
    job_id: int
    title: str
    company_name: str
    city: str


class InterviewResponse(BaseModel):
    id: int
    title: str
    application: InterviewApplicationRef | None
    company_name: str | None
    position_title: str | None
    starts_at: datetime
    ends_at: datetime | None
    timezone: str
    interview_format: InterviewFormat
    location: str | None
    meeting_url: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class InterviewListResponse(BaseModel):
    items: list[InterviewResponse]
    total: int


class WorkbenchStatusCount(BaseModel):
    id: int
    name: str
    color: str | None
    sort_order: int
    enabled: bool
    count: int


class WeeklyStatusEventCount(BaseModel):
    week_start: str
    count: int


class WorkbenchOverviewResponse(BaseModel):
    generated_at: datetime
    application_count: int
    todo_open_count: int
    todo_overdue_count: int
    todo_completed_count: int
    interview_upcoming_count: int
    interview_next_7_days_count: int
    status_counts: list[WorkbenchStatusCount]
    weekly_status_events: list[WeeklyStatusEventCount]
