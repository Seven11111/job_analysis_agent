"""Database access for workbench summaries, todos, and interview events."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from src.db.models import (
    Application,
    ApplicationStatusDefinition,
    ApplicationStatusEvent,
    CandidateProfile,
    InterviewEvent,
    Job,
    JobTodo,
)
from src.repositories.application_repository import ApplicationRepository


class WorkbenchRepository:
    def __init__(self, applications: ApplicationRepository | None = None):
        self.applications = applications or ApplicationRepository()

    def ensure_profile(self, session: Session) -> CandidateProfile:
        return self.applications.ensure_profile(session)

    @staticmethod
    def _application_options():
        return joinedload(JobTodo.application).joinedload(Application.job)

    def get_application(self, session: Session, profile_id: int, application_id: int) -> Application | None:
        return session.scalar(
            select(Application)
            .options(joinedload(Application.job), joinedload(Application.current_status))
            .where(Application.profile_id == profile_id, Application.id == application_id)
        )

    def list_applications(self, session: Session, profile_id: int) -> list[Application]:
        return list(
            session.scalars(
                select(Application)
                .options(joinedload(Application.job), joinedload(Application.current_status))
                .where(Application.profile_id == profile_id)
                .order_by(Application.saved_at.desc(), Application.id.desc())
            ).unique()
        )

    def list_todos(
        self,
        session: Session,
        profile_id: int,
        *,
        status_filter: str,
        page: int,
        limit: int,
    ) -> tuple[list[JobTodo], int]:
        statement = select(JobTodo).where(JobTodo.profile_id == profile_id)
        if status_filter == "open":
            statement = statement.where(JobTodo.completed.is_(False))
        elif status_filter == "completed":
            statement = statement.where(JobTodo.completed.is_(True))

        total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        if status_filter == "completed":
            statement = statement.order_by(JobTodo.completed_at.desc(), JobTodo.id.desc())
        else:
            priority_order = case(
                (JobTodo.priority == "high", 0),
                (JobTodo.priority == "normal", 1),
                else_=2,
            )
            statement = statement.order_by(
                JobTodo.completed.asc(),
                case((JobTodo.due_at.is_(None), 1), else_=0),
                JobTodo.due_at.asc(),
                priority_order,
                JobTodo.id.desc(),
            )
        statement = statement.options(self._application_options())
        items = list(session.scalars(statement.offset((page - 1) * limit).limit(limit)).unique())
        return items, total

    def get_todo(self, session: Session, profile_id: int, todo_id: int) -> JobTodo | None:
        return session.scalar(
            select(JobTodo)
            .options(self._application_options())
            .where(JobTodo.profile_id == profile_id, JobTodo.id == todo_id)
        )

    def create_todo(self, session: Session, profile_id: int, values: dict) -> JobTodo:
        todo = JobTodo(profile_id=profile_id, **values)
        session.add(todo)
        session.flush()
        return self.get_todo(session, profile_id, todo.id)

    def update_todo(self, session: Session, todo: JobTodo, values: dict, now: datetime) -> JobTodo:
        for key, value in values.items():
            if key == "completed":
                todo.completed = value
                todo.completed_at = now if value else None
            else:
                setattr(todo, key, value)
        session.flush()
        return self.get_todo(session, todo.profile_id, todo.id)

    @staticmethod
    def delete_todo(session: Session, todo: JobTodo) -> None:
        session.delete(todo)

    def list_interviews(
        self,
        session: Session,
        profile_id: int,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[list[InterviewEvent], int]:
        statement = select(InterviewEvent).where(InterviewEvent.profile_id == profile_id)
        if start_at is not None:
            statement = statement.where(InterviewEvent.starts_at >= start_at)
        if end_at is not None:
            statement = statement.where(InterviewEvent.starts_at < end_at)
        total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        statement = statement.options(joinedload(InterviewEvent.application).joinedload(Application.job))
        statement = statement.order_by(InterviewEvent.starts_at, InterviewEvent.id)
        return list(session.scalars(statement).unique()), total

    def get_interview(self, session: Session, profile_id: int, interview_id: int) -> InterviewEvent | None:
        return session.scalar(
            select(InterviewEvent)
            .options(joinedload(InterviewEvent.application).joinedload(Application.job))
            .where(InterviewEvent.profile_id == profile_id, InterviewEvent.id == interview_id)
        )

    def create_interview(self, session: Session, profile_id: int, values: dict) -> InterviewEvent:
        interview = InterviewEvent(profile_id=profile_id, **values)
        session.add(interview)
        session.flush()
        return self.get_interview(session, profile_id, interview.id)

    def update_interview(self, session: Session, interview: InterviewEvent, values: dict) -> InterviewEvent:
        for key, value in values.items():
            setattr(interview, key, value)
        session.flush()
        return self.get_interview(session, interview.profile_id, interview.id)

    @staticmethod
    def delete_interview(session: Session, interview: InterviewEvent) -> None:
        session.delete(interview)

    def overview(self, session: Session, profile: CandidateProfile, now: datetime) -> dict:
        application_count = int(
            session.scalar(select(func.count()).select_from(Application).where(Application.profile_id == profile.id))
            or 0
        )
        todos = list(session.scalars(select(JobTodo).where(JobTodo.profile_id == profile.id)))
        open_todos = [todo for todo in todos if not todo.completed]
        todo_overdue_count = sum(1 for todo in open_todos if todo.due_at is not None and todo.due_at < now)
        interviews = list(
            session.scalars(select(InterviewEvent).where(InterviewEvent.profile_id == profile.id))
        )
        interview_upcoming_count = sum(1 for item in interviews if item.starts_at >= now)
        interview_next_7_days_count = sum(
            1 for item in interviews if now <= item.starts_at < now + timedelta(days=7)
        )

        status_definitions = list(
            session.scalars(
                select(ApplicationStatusDefinition)
                .where(ApplicationStatusDefinition.profile_id == profile.id)
                .order_by(ApplicationStatusDefinition.sort_order, ApplicationStatusDefinition.id)
            )
        )
        status_rows = session.execute(
            select(Application.current_status_id, func.count(Application.id))
            .where(Application.profile_id == profile.id)
            .group_by(Application.current_status_id)
        ).all()
        status_counts = {status_id: count for status_id, count in status_rows}

        # Status events are stored as naive UTC. The workbench presents calendar
        # weeks in the product's default timezone (Beijing), so bucket after
        # converting to UTC+08:00 instead of cutting weeks at UTC midnight.
        beijing_offset = timedelta(hours=8)
        local_now = now + beijing_offset
        current_week = local_now.date().toordinal() - local_now.date().weekday()
        first_week = current_week - 5 * 7
        first_day = datetime.fromordinal(first_week) - beijing_offset
        events = list(
            session.scalars(
                select(ApplicationStatusEvent).where(
                    ApplicationStatusEvent.effective_at >= first_day,
                    ApplicationStatusEvent.effective_at <= now,
                    ApplicationStatusEvent.application_id.in_(
                        select(Application.id).where(Application.profile_id == profile.id)
                    ),
                )
            )
        )
        weekly_counts: dict[str, int] = {}
        for event in events:
            local_effective_at = event.effective_at + beijing_offset
            monday = local_effective_at.date() - timedelta(days=local_effective_at.weekday())
            key = monday.isoformat()
            weekly_counts[key] = weekly_counts.get(key, 0) + 1
        weekly_status_events = []
        for offset in range(6):
            week_start = datetime.fromordinal(first_week + offset * 7).date().isoformat()
            weekly_status_events.append({"week_start": week_start, "count": weekly_counts.get(week_start, 0)})

        return {
            "application_count": application_count,
            "todo_open_count": len(open_todos),
            "todo_overdue_count": todo_overdue_count,
            "todo_completed_count": sum(1 for todo in todos if todo.completed),
            "interview_upcoming_count": interview_upcoming_count,
            "interview_next_7_days_count": interview_next_7_days_count,
            "status_counts": [
                {
                    "id": status.id,
                    "name": status.name,
                    "color": status.color,
                    "sort_order": status.sort_order,
                    "enabled": status.enabled,
                    "count": status_counts.get(status.id, 0),
                }
                for status in status_definitions
            ],
            "weekly_status_events": weekly_status_events,
        }
