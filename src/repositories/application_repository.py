"""Persistence operations for saved jobs and user-defined status history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from src.db.models import (
    Application,
    ApplicationStatusDefinition,
    ApplicationStatusEvent,
    CandidateProfile,
    Job,
)


DEFAULT_STATUSES = (
    ("已保存", "blue", 10, False, False),
    ("准备投递", "amber", 20, False, False),
    ("已投递", "indigo", 30, False, False),
    ("面试中", "violet", 40, False, False),
    ("Offer", "green", 50, True, True),
    ("流程终止", "slate", 60, False, True),
)


class ApplicationRepository:
    def ensure_profile(self, session: Session) -> CandidateProfile:
        profile = session.scalar(select(CandidateProfile).where(CandidateProfile.active.is_(True)).order_by(CandidateProfile.id))
        if profile is None:
            profile = CandidateProfile(active=True)
            session.add(profile)
            session.flush()
        self.ensure_default_statuses(session, profile)
        return profile

    def ensure_default_statuses(self, session: Session, profile: CandidateProfile) -> list[ApplicationStatusDefinition]:
        statuses = list(
            session.scalars(
                select(ApplicationStatusDefinition)
                .where(ApplicationStatusDefinition.profile_id == profile.id)
                .order_by(ApplicationStatusDefinition.sort_order, ApplicationStatusDefinition.id)
            )
        )
        if statuses:
            return statuses
        statuses = [
            ApplicationStatusDefinition(
                profile_id=profile.id,
                name=name,
                color=color,
                sort_order=sort_order,
                is_success=is_success,
                is_terminal=is_terminal,
            )
            for name, color, sort_order, is_success, is_terminal in DEFAULT_STATUSES
        ]
        session.add_all(statuses)
        session.flush()
        return statuses

    def list_statuses(self, session: Session) -> list[ApplicationStatusDefinition]:
        profile = self.ensure_profile(session)
        return list(
            session.scalars(
                select(ApplicationStatusDefinition)
                .where(
                    ApplicationStatusDefinition.profile_id == profile.id,
                    ApplicationStatusDefinition.enabled.is_(True),
                )
                .order_by(ApplicationStatusDefinition.sort_order, ApplicationStatusDefinition.id)
            )
        )

    def get_status(self, session: Session, status_id: int) -> ApplicationStatusDefinition | None:
        profile = self.ensure_profile(session)
        return session.scalar(
            select(ApplicationStatusDefinition).where(
                ApplicationStatusDefinition.id == status_id,
                ApplicationStatusDefinition.profile_id == profile.id,
                ApplicationStatusDefinition.enabled.is_(True),
            )
        )

    def get_application(self, session: Session, application_id: int) -> Application | None:
        return session.scalar(
            select(Application)
            .options(
                joinedload(Application.job).joinedload(Job.source),
                joinedload(Application.current_status),
                selectinload(Application.status_events),
            )
            .where(Application.id == application_id)
        )

    def get_by_job(self, session: Session, profile_id: int, job_id: int) -> Application | None:
        return session.scalar(
            select(Application).where(Application.profile_id == profile_id, Application.job_id == job_id)
        )

    def create_application(
        self,
        session: Session,
        *,
        profile: CandidateProfile,
        job: Job,
        status: ApplicationStatusDefinition,
        note: str | None,
    ) -> Application:
        now = datetime.utcnow()
        application = Application(
            job_id=job.id,
            profile_id=profile.id,
            current_status_id=status.id,
            saved_at=now,
            last_status_changed_at=now,
            note=note,
        )
        session.add(application)
        session.flush()
        session.add(
            ApplicationStatusEvent(
                application_id=application.id,
                from_status_id=None,
                to_status_id=status.id,
                effective_at=now,
                note=note,
            )
        )
        session.flush()
        return self.get_application(session, application.id)

    def list_applications(
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
        profile = self.ensure_profile(session)
        statement = (
            select(Application)
            .options(
                joinedload(Application.job).selectinload(Job.matches),
                joinedload(Application.current_status),
            )
            .where(Application.profile_id == profile.id)
            .order_by(Application.saved_at.desc(), Application.id.desc())
        )
        if status_id is not None:
            statement = statement.where(Application.current_status_id == status_id)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            statement = statement.where(
                Application.job.has(Job.title.ilike(pattern) | Job.company_name.ilike(pattern))
            )
        if city and city.strip():
            statement = statement.where(Application.job.has(Job.city.ilike(f"%{city.strip()}%")))
        if tab == "pending_analysis":
            statement = statement.where(~Application.job.has(Job.matches.any()))
        elif tab == "analyzed":
            statement = statement.where(Application.job.has(Job.matches.any()))
        total = int(session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
        items = list(session.scalars(statement.offset((page - 1) * limit).limit(limit)).unique())
        return items, total

    def update_note(self, session: Session, application: Application, note: str | None) -> Application:
        application.note = note
        session.flush()
        return self.get_application(session, application.id)

    def change_status(
        self,
        session: Session,
        application: Application,
        to_status: ApplicationStatusDefinition,
        effective_at: datetime,
        note: str | None,
    ) -> tuple[Application, ApplicationStatusEvent]:
        event = ApplicationStatusEvent(
            application_id=application.id,
            from_status_id=application.current_status_id,
            to_status_id=to_status.id,
            effective_at=effective_at,
            note=note,
        )
        application.current_status_id = to_status.id
        application.last_status_changed_at = effective_at
        if note is not None:
            application.note = note
        session.add(event)
        session.flush()
        application, events = self.rebuild_status_chain(session, application)
        return application, next(item for item in events if item.id == event.id)

    def get_status_event(
        self, session: Session, application_id: int, event_id: int
    ) -> ApplicationStatusEvent | None:
        return session.scalar(
            select(ApplicationStatusEvent)
            .options(
                joinedload(ApplicationStatusEvent.from_status),
                joinedload(ApplicationStatusEvent.to_status),
            )
            .where(
                ApplicationStatusEvent.application_id == application_id,
                ApplicationStatusEvent.id == event_id,
            )
        )

    def rebuild_status_chain(
        self, session: Session, application: Application
    ) -> tuple[Application, list[ApplicationStatusEvent]]:
        """Keep transition ancestry and current state consistent with change order."""
        # Session factories disable autoflush; persist the edited event before rebuilding
        # the transition chain, especially when an event's status was changed.
        session.flush()
        events = list(
            session.scalars(
                select(ApplicationStatusEvent)
                .options(
                    joinedload(ApplicationStatusEvent.from_status),
                    joinedload(ApplicationStatusEvent.to_status),
                )
                .where(ApplicationStatusEvent.application_id == application.id)
                .order_by(ApplicationStatusEvent.id)
            )
        )
        previous_status_id = None
        for event in events:
            event.from_status_id = previous_status_id
            previous_status_id = event.to_status_id
        if events:
            latest = events[-1]
            application.current_status_id = latest.to_status_id
            application.last_status_changed_at = latest.effective_at
        session.flush()
        session.expire(application, ["current_status"])
        for event in events:
            session.expire(event, ["from_status", "to_status"])
        return self.get_application(session, application.id), events

    @staticmethod
    def delete_application(session: Session, application: Application) -> None:
        session.delete(application)

    def list_timeline(self, session: Session, application_id: int) -> list[ApplicationStatusEvent]:
        return list(
            session.scalars(
                select(ApplicationStatusEvent)
                .options(
                    joinedload(ApplicationStatusEvent.from_status),
                    joinedload(ApplicationStatusEvent.to_status),
                )
                .where(ApplicationStatusEvent.application_id == application_id)
                .order_by(ApplicationStatusEvent.effective_at.desc(), ApplicationStatusEvent.id.desc())
            )
        )
