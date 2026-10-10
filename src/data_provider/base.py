"""Provider contracts; implementations must not write to the database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class JobRecord:
    source_job_id: str
    title: str
    company_name: str
    city: str
    detail_url: str
    published_date: date | None
    district: str | None = None
    job_type: str = "实习生"
    salary_min: float | None = None
    salary_max: float | None = None
    salary_unit: str | None = None
    salary_status: str = "unknown"
    education: str | None = None
    internship_months: float | None = None
    days_per_week: int | None = None
    conversion_chance: str | None = None
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    extraction_method: str = "provider_api"
    raw_payload: dict[str, Any] | None = None


class JobProvider(Protocol):
    provider_name: str

    def search(self, *, keyword: str | None = None, city: str | None = None) -> list[JobRecord]:
        """Return normalized source records without persistence side effects."""
