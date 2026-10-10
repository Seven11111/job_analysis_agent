"""Structured model output for public job-page extraction."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobPageExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_job_posting: bool
    confidence: float = Field(ge=0, le=1)
    title: str | None = Field(default=None, max_length=300)
    company_name: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    job_type: str | None = Field(default=None, max_length=64)
    published_date: date | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_unit: str | None = Field(default=None, max_length=32)
    salary_status: Literal["disclosed", "undisclosed", "unknown", "negotiable"] = "unknown"
    education: str | None = Field(default=None, max_length=128)
    internship_months: float | None = Field(default=None, ge=0)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    conversion_chance: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=10000)
    requirements: str | None = Field(default=None, max_length=10000)
    responsibilities: str | None = Field(default=None, max_length=10000)
    field_evidence: dict[str, str] = Field(default_factory=dict)
