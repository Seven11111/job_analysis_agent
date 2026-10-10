"""Persistence operations for normalized jobs and their source snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from src.data_provider.base import JobRecord
from src.db.models import Job, JobSnapshot, JobSource


class JobRepository:
    def get_or_create_source(
        self,
        session: Session,
        *,
        provider: str,
        name: str,
        source_type: str | None = None,
        authorization_mode: str | None = None,
        terms_url: str | None = None,
    ) -> JobSource:
        source = session.scalar(select(JobSource).where(JobSource.provider == provider))
        if source is None:
            source = JobSource(
                name=name,
                provider=provider,
                source_type=source_type or ("fixture" if provider == "fixture" else "provider"),
                authorization_mode=authorization_mode or ("offline" if provider == "fixture" else "unknown"),
                terms_url=terms_url,
                quality_status="healthy",
            )
            session.add(source)
            session.flush()
        else:
            source.name = name
            if source_type is not None:
                source.source_type = source_type
            if authorization_mode is not None:
                source.authorization_mode = authorization_mode
            if terms_url is not None:
                source.terms_url = terms_url
        return source

    def upsert_record(self, session: Session, *, source: JobSource, record: JobRecord) -> Job:
        job = session.scalar(
            select(Job).where(Job.source_id == source.id, Job.source_job_id == record.source_job_id)
        )
        now = datetime.utcnow()
        if job is None:
            job = Job(source_id=source.id, source_job_id=record.source_job_id, first_seen_at=now)
            session.add(job)

        job.title = record.title
        job.company_name = record.company_name
        job.city = record.city
        job.district = record.district
        job.job_type = record.job_type
        job.salary_min = record.salary_min
        job.salary_max = record.salary_max
        job.salary_unit = record.salary_unit
        job.salary_status = record.salary_status
        job.education = record.education
        job.internship_months = record.internship_months
        job.days_per_week = record.days_per_week
        job.conversion_chance = record.conversion_chance
        job.detail_url = record.detail_url
        job.published_date = record.published_date
        job.lifecycle_status = "active"
        job.last_seen_at = now
        session.flush()

        snapshot_payload = {
            "description": record.description,
            "requirements": record.requirements,
            "responsibilities": record.responsibilities,
            "salary_text": self.salary_text(record),
            "source_job_id": record.source_job_id,
            "detail_url": record.detail_url,
        }
        if record.raw_payload is not None:
            snapshot_payload["raw_payload"] = record.raw_payload
        content_hash = hashlib.sha256(
            json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        existing_snapshot = session.scalar(
            select(JobSnapshot).where(JobSnapshot.job_id == job.id, JobSnapshot.content_hash == content_hash)
        )
        if existing_snapshot is None:
            session.add(
                JobSnapshot(
                    job_id=job.id,
                    description=record.description,
                    requirements=record.requirements,
                    responsibilities=record.responsibilities,
                    salary_text=self.salary_text(record),
                    raw_payload=json.dumps(snapshot_payload, ensure_ascii=False),
                    extraction_method=record.extraction_method,
                    content_hash=content_hash,
                )
            )
        source.last_synced_at = now
        session.flush()
        return job

    @staticmethod
    def salary_text(record: JobRecord) -> str | None:
        if record.salary_status == "undisclosed":
            return "薪资未公开"
        if record.salary_status == "unknown":
            return None
        if record.salary_min is not None and record.salary_max is not None:
            return f"{record.salary_min:g}-{record.salary_max:g} {record.salary_unit or ''}".strip()
        return "面议" if record.salary_status == "negotiable" else None

    def count(self, session: Session, statement) -> int:
        return int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)

    def search(
        self,
        session: Session,
        *,
        keyword: str | None,
        city: str | None,
        published_after: date | None,
        salary_mode: str,
        salary_min: float | None,
        internship_type: str | None,
        education: str | None,
        internship_months: float | None,
        days_per_week: int | None,
        conversion_chance: str | None,
        page: int,
        limit: int,
    ) -> tuple[list[Job], int]:
        statement = select(Job).options(joinedload(Job.source)).order_by(Job.published_date.desc(), Job.id.desc())
        if keyword:
            pattern = f"%{keyword.strip()}%"
            statement = statement.where(
                or_(Job.title.ilike(pattern), Job.company_name.ilike(pattern))
            )
        if city:
            statement = statement.where(Job.city == city.strip())
        if published_after is not None:
            statement = statement.where(Job.published_date.is_not(None), Job.published_date >= published_after)
        if salary_mode == "disclosed_only":
            statement = statement.where(Job.salary_status == "disclosed")
        elif salary_mode == "minimum":
            statement = statement.where(Job.salary_status == "disclosed", Job.salary_min >= salary_min)
        if internship_type:
            statement = statement.where(Job.job_type == internship_type)
        if education:
            statement = statement.where(Job.education == education)
        if internship_months is not None:
            statement = statement.where(Job.internship_months >= internship_months)
        if days_per_week is not None:
            statement = statement.where(Job.days_per_week >= days_per_week)
        if conversion_chance:
            statement = statement.where(Job.conversion_chance == conversion_chance)

        total = self.count(session, statement)
        items = list(session.scalars(statement.offset((page - 1) * limit).limit(limit)).unique())
        return items, total

    def get_detail(self, session: Session, job_id: int) -> Job | None:
        return session.scalar(
            select(Job)
            .options(joinedload(Job.source), joinedload(Job.snapshots))
            .where(Job.id == job_id)
        )
