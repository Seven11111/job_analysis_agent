"""API schemas for Phase 1 job search."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


PublishedRange = Literal["all", "1d", "3d", "7d", "30d"]
SalaryMode = Literal["any", "disclosed_only", "minimum"]


class JobSearchRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=100)
    company: str | None = Field(default=None, max_length=100, description="按公司名称进行包含匹配")
    # ``city`` remains accepted for backward compatibility. New clients should
    # use ``cities`` so one search can fan out to several locations.
    city: str | None = Field(default=None, max_length=64)
    cities: list[str] = Field(default_factory=list, max_length=10)
    published_range: PublishedRange = "all"
    salary_mode: SalaryMode = "any"
    salary_min: float | None = Field(default=None, ge=0)
    internship_type: str | None = Field(default=None, max_length=64)
    education: str | None = Field(default=None, max_length=128)
    internship_months: float | None = Field(default=None, ge=0)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    conversion_chance: str | None = Field(default=None, max_length=32)
    providers: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_salary_filter(self) -> "JobSearchRequest":
        if self.city and not self.cities:
            self.cities = [self.city]
        self.cities = list(dict.fromkeys(item.strip() for item in self.cities if item.strip()))
        if self.salary_min is not None and self.salary_mode != "minimum":
            raise ValueError("salary_min 只有 salary_mode=minimum 时有效")
        if self.salary_mode == "minimum" and self.salary_min is None:
            raise ValueError("salary_mode=minimum 时必须提供 salary_min")
        return self


class SalaryResponse(BaseModel):
    min: float | None
    max: float | None
    unit: str | None
    status: str
    display: str


class SourceResponse(BaseModel):
    name: str
    provider: str
    quality_status: str
    source_type: str = "provider"
    authorization_mode: str = "unknown"
    terms_url: str | None = None


class JobSummaryResponse(BaseModel):
    id: int | None
    result_token: str | None = None
    title: str
    company_name: str
    city: str
    district: str | None
    job_type: str
    published_date: date | None
    salary: SalaryResponse
    education: str | None
    internship_months: float | None
    days_per_week: int | None
    conversion_chance: str | None
    detail_url: str
    source: SourceResponse
    extraction_method: str
    is_saved: bool = False
    application: dict | None = None
    latest_match: dict | None = None


class JobDetailResponse(JobSummaryResponse):
    description: str | None
    requirements: str | None
    responsibilities: str | None
    snapshot_fetched_at: datetime | None


class JobImportPreviewRequest(BaseModel):
    detail_url: str = Field(min_length=8, max_length=1000)


class JobImportPreviewResponse(BaseModel):
    preview_token: str
    job: JobDetailResponse
    warnings: list[str] = Field(default_factory=list)


class JobImportConfirmRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=64)
    district: str | None = Field(default=None, max_length=64)
    job_type: str | None = Field(default=None, max_length=64)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_unit: str | None = Field(default=None, max_length=32)
    salary_status: str | None = Field(default=None, max_length=32)
    published_date: date | None = None
    education: str | None = Field(default=None, max_length=128)
    internship_months: float | None = Field(default=None, ge=0)
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    conversion_chance: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=10000)
    requirements: str | None = Field(default=None, max_length=10000)
    responsibilities: str | None = Field(default=None, max_length=10000)


class ProviderQuality(BaseModel):
    provider: str
    status: str
    count: int = 0
    error: str | None = None


class SearchQuality(BaseModel):
    undisclosed_salary_count: int
    missing_published_date_count: int
    providers: list[ProviderQuality]


class JobSearchResponse(BaseModel):
    items: list[JobSummaryResponse]
    total: int
    page: int
    limit: int
    quality: SearchQuality
