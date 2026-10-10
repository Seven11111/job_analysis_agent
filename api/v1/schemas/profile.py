"""API schemas for candidate profile, resume versions and profile facts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.schemas.resume import ResumeStructuredContent


class ProfileUpdate(BaseModel):
    school: str | None = Field(default=None, max_length=200)
    major: str | None = Field(default=None, max_length=200)
    education: str | None = Field(default=None, max_length=64)
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)
    target_directions: list[str] = Field(default_factory=list, max_length=20)
    target_cities: list[str] = Field(default_factory=list, max_length=20)
    available_period: str | None = Field(default=None, max_length=128)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    internship_months: float | None = Field(default=None, ge=0)
    desired_industries: list[str] = Field(default_factory=list, max_length=20)


class ResumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    raw_text: str = Field(min_length=1, max_length=100_000)
    structured_content: ResumeStructuredContent | None = None
    set_current: bool = False
    source_attachment_id: int | None = Field(default=None, gt=0)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("简历名称不能为空")
        return value


class ResumeResponse(BaseModel):
    id: int
    title: str
    is_current: bool
    created_at: datetime
    updated_at: datetime
    text_preview: str
    has_content: bool
    source_attachment_id: int | None = None


class ResumeDetailResponse(ResumeResponse):
    raw_text: str
    structured_content: dict | None = None


class ResumeAttachmentConfirmRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    structured_content: ResumeStructuredContent
    set_current: bool = True

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("简历名称不能为空")
        return value


class ResumeAttachmentResponse(BaseModel):
    id: int
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    parse_status: str
    created_at: datetime
    linked_resume_version_id: int | None = None
    draft_content: ResumeStructuredContent | None = None


class ResumeAttachmentDeleteResponse(BaseModel):
    id: int
    deleted: bool


class ProfileFactCreate(BaseModel):
    fact_type: str = Field(min_length=1, max_length=64)
    fact_key: str = Field(min_length=1, max_length=128)
    fact_value: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="user", max_length=32)
    confirmed: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)
    valid_from: date | None = None
    valid_to: date | None = None


class ProfileFactPatch(BaseModel):
    fact_value: str | None = Field(default=None, min_length=1, max_length=4000)
    status: Literal["active", "superseded", "temporary", "deleted"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    valid_from: date | None = None
    valid_to: date | None = None


class ProfileFactResponse(BaseModel):
    id: int
    fact_type: str
    fact_key: str
    fact_value: str
    status: str
    source: str
    confidence: float | None
    confirmed_at: datetime | None
    valid_from: date | None
    valid_to: date | None
    created_at: datetime
    updated_at: datetime


class ProfileConfirmRequest(BaseModel):
    fact_ids: list[int] = Field(min_length=1)
    replace_fact_ids: list[int] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    id: int
    school: str | None
    major: str | None
    education: str | None
    graduation_year: int | None
    target_directions: list[str]
    target_cities: list[str]
    available_period: str | None
    days_per_week: int | None
    internship_months: float | None
    desired_industries: list[str]
    resumes: list[ResumeResponse]
    active_facts: list[ProfileFactResponse]
