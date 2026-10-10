"""Business rules for saving jobs and maintaining user-owned status history."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Application, ApplicationStatusDefinition, ApplicationStatusEvent, Job
from src.repositories.application_repository import ApplicationRepository


class ApplicationNotFound(Exception):
    pass


class JobNotFound(Exception):
    pass


class StatusNotFound(Exception):
    pass


class DuplicateApplication(Exception):
    pass


def normalize_utc_naive(value: datetime | None) -> datetime:
    effective = value or datetime.now(timezone.utc)
    if effective.tzinfo is not None:
        effective = effective.astimezone(timezone.utc).replace(tzinfo=None)
    return effective


class ApplicationService:
    def __init__(self, repository: ApplicationRepository | None = None):
        self.repository = repository or ApplicationRepository()

    def create(self, session: Session, *, job_id: int, status_id: int | None, note: str | None) -> Application:
        profile = self.repository.ensure_profile(session)
        job = session.scalar(select(Job).where(Job.id == job_id))
        if job is None:
            raise JobNotFound("岗位不存在")
        if self.repository.get_by_job(session, profile.id, job_id) is not None:
            raise DuplicateApplication("岗位已经收藏")
        status = self.repository.get_status(session, status_id) if status_id else self.repository.list_statuses(session)[0]
        if status is None:
            raise StatusNotFound("状态不存在或不可用")
        application = self.repository.create_application(
            session, profile=profile, job=job, status=status, note=note
        )
        session.commit()
        return application

    def list(
        self,
        session: Session,
        *,
        tab: str,
        status_id: int | None,
        q: str | None,
        city: str | None,
        page: int,
        limit: int,
    ) -> tuple[list[Application], int]:
        items, total = self.repository.list_applications(
            session, tab=tab, status_id=status_id, q=q, city=city, page=page, limit=limit
        )
        session.commit()
        return items, total

    def get(self, session: Session, application_id: int) -> Application:
        application = self.repository.get_application(session, application_id)
        if application is None:
            raise ApplicationNotFound("收藏岗位不存在")
        return application

    def update_note(self, session: Session, application_id: int, note: str | None) -> Application:
        application = self.get(session, application_id)
        application = self.repository.update_note(session, application, note)
        session.commit()
        return application

    def change_status(
        self,
        session: Session,
        application_id: int,
        *,
        to_status_id: int,
        effective_at: datetime | None,
        note: str | None,
    ) -> tuple[Application, ApplicationStatusEvent]:
        application = self.get(session, application_id)
        to_status = self.repository.get_status(session, to_status_id)
        if to_status is None:
            raise StatusNotFound("状态不存在或不可用")
        effective = normalize_utc_naive(effective_at)
        application, event = self.repository.change_status(
            session, application, to_status, effective, note
        )
        session.commit()
        return application, event

    def update_status_event(
        self,
        session: Session,
        application_id: int,
        event_id: int,
        *,
        to_status_id: int | None,
        effective_at: datetime | None,
        note: str | None,
        update_fields: set[str],
    ) -> tuple[Application, ApplicationStatusEvent]:
        application = self.get(session, application_id)
        event = self.repository.get_status_event(session, application_id, event_id)
        if event is None:
            raise ApplicationNotFound("状态历史记录不存在")
        if to_status_id is not None:
            to_status = self.repository.get_status(session, to_status_id)
            if to_status is None:
                raise StatusNotFound("状态不存在或不可用")
            event.to_status_id = to_status.id
        if "effective_at" in update_fields and effective_at is not None:
            event.effective_at = normalize_utc_naive(effective_at)
        if "note" in update_fields:
            event.note = note
        application, events = self.repository.rebuild_status_chain(session, application)
        if events and events[-1].id == event.id and "note" in update_fields:
            application.note = note
        session.commit()
        return self.get(session, application_id), self.repository.get_status_event(session, application_id, event_id)

    def delete(self, session: Session, application_id: int) -> None:
        application = self.get(session, application_id)
        self.repository.delete_application(session, application)
        session.commit()

    def statuses(self, session: Session) -> list[ApplicationStatusDefinition]:
        statuses = self.repository.list_statuses(session)
        session.commit()
        return statuses

    def create_status(self, session: Session, **payload) -> ApplicationStatusDefinition:
        profile = self.repository.ensure_profile(session)
        duplicate = session.scalar(
            select(ApplicationStatusDefinition).where(
                ApplicationStatusDefinition.profile_id == profile.id,
                ApplicationStatusDefinition.name == payload["name"],
            )
        )
        if duplicate is not None:
            raise DuplicateApplication("状态名称已经存在")
        status = ApplicationStatusDefinition(profile_id=profile.id, **payload)
        session.add(status)
        session.commit()
        session.refresh(status)
        return status

    def update_status(self, session: Session, status_id: int, **payload) -> ApplicationStatusDefinition:
        status = self.repository.get_status(session, status_id)
        if status is None:
            raise StatusNotFound("状态不存在或不可用")
        if payload.get("name") is not None:
            duplicate = session.scalar(
                select(ApplicationStatusDefinition).where(
                    ApplicationStatusDefinition.profile_id == status.profile_id,
                    ApplicationStatusDefinition.name == payload["name"],
                    ApplicationStatusDefinition.id != status.id,
                )
            )
            if duplicate is not None:
                raise DuplicateApplication("状态名称已经存在")
        for key, value in payload.items():
            if value is not None:
                setattr(status, key, value)
        session.commit()
        session.refresh(status)
        return status

    def disable_status(self, session: Session, status_id: int) -> ApplicationStatusDefinition:
        status = self.repository.get_status(session, status_id)
        if status is None:
            raise StatusNotFound("状态不存在或不可用")
        status.enabled = False
        session.commit()
        return status
