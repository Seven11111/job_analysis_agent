"""API contracts for official campus-recruit notices."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CampusRecruitSearchRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=100)
    company: str | None = Field(default=None, max_length=100)
    position_name: str | None = Field(default=None, max_length=100)
    function_name: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    cities: list[str] = Field(default_factory=list, max_length=10)
    graduation_year: int | None = Field(default=None, ge=2000, le=2100)
    education_level: str | None = Field(default=None, max_length=100)
    company_nature: str | None = Field(default=None, max_length=100)
    recruitment_batch: str | None = Field(default=None, max_length=100)
    start_time: date | None = None
    end_time: date | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_search(self) -> "CampusRecruitSearchRequest":
        self.cities = list(dict.fromkeys(city.strip() for city in self.cities if city.strip()))
        query_values = (
            self.keyword, self.company, self.position_name, self.function_name, self.industry,
            self.graduation_year, self.education_level, self.company_nature,
            self.recruitment_batch, self.start_time, self.end_time,
        )
        if not any(value is not None and str(value).strip() for value in query_values) and not self.cities:
            raise ValueError("至少填写一个搜索条件，避免无条件拉取校招信息")
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("网申开始日期不能晚于截止日期")
        return self


class CampusRecruitNoticeResponse(BaseModel):
    id: str
    recruit_info_name: str | None
    company_name: str | None
    graduation_year: int | None
    recruitment_batch: str | None
    industry: str | None
    company_nature: str | None
    application_start_date: date | None
    application_end_date: date | None
    test_time: str | None
    publicity_time: str | None
    interview_start_time: str | None
    interview_end_time: str | None
    domestic_graduation_date: str | None
    domestic_graduation_time: str | None
    overseas_graduation_date: str | None
    overseas_graduation_time: str | None
    domestic_education: str | None
    overseas_education: str | None
    position_categories: list[str]
    cities: list[str]
    content: str | None
    application_url: str | None
    announcement_url: str | None
    release_source: str | None
    updated_at: str | None


class CampusRecruitSourceInfo(BaseModel):
    provider: str = "offer_xiansheng"
    name: str = "Offer 先生校招资讯"
    data_type: str = "campus_recruit_notice"


class CampusRecruitSearchResponse(BaseModel):
    items: list[CampusRecruitNoticeResponse]
    count: int
    limit: int
    next_cursor: str | None
    has_more: bool
    source: CampusRecruitSourceInfo
