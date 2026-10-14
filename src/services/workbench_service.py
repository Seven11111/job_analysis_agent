"""Business rules for the user-owned workbench."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.db.models import CandidateProfile, InterviewEvent, JobTodo
from src.repositories.workbench_repository import WorkbenchRepository


class WorkbenchItemNotFound(Exception):
    pass


class WorkbenchApplicationNotFound(Exception):
    pass


class InvalidWorkbenchRequest(Exception):
    pass


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidWorkbenchRequest("时间必须包含时区，例如 +08:00")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class WorkbenchService:
    def __init__(self, repository: WorkbenchRepository | None = None):
        self.repository = repository or WorkbenchRepository()

    def _profile(self, session: Session) -> CandidateProfile:
        return self.repository.ensure_profile(session)

    def overview(self, session: Session) -> dict:
        now = utc_now_naive()
        profile = self._profile(session)
        result = self.repository.overview(session, profile, now)
        session.commit()
        return {"generated_at": now.replace(tzinfo=timezone.utc), **result}

    def list_applications(self, session: Session):
        profile = self._profile(session)
        items = self.repository.list_applications(session, profile.id)
        session.commit()
        return items

    def list_todos(self, session: Session, *, status_filter: str, page: int, limit: int):
        profile = self._profile(session)
        items, total = self.repository.list_todos(
            session, profile.id, status_filter=status_filter, page=page, limit=limit
        )
        session.commit()
        return items, total

    def create_todo(self, session: Session, values: dict) -> JobTodo:
        profile = self._profile(session)
        values = dict(values)
        values["due_at"] = to_utc_naive(values.get("due_at"))
        if values.get("application_id") is not None and self.repository.get_application(
            session, profile.id, values["application_id"]
        ) is None:
            raise WorkbenchApplicationNotFound("关联岗位不存在")
        todo = self.repository.create_todo(session, profile.id, values)
        session.commit()
        return todo

    def update_todo(self, session: Session, todo_id: int, values: dict) -> JobTodo:
        profile = self._profile(session)
        todo = self.repository.get_todo(session, profile.id, todo_id)
        if todo is None:
            raise WorkbenchItemNotFound("待办不存在")
        values = dict(values)
        if "due_at" in values:
            values["due_at"] = to_utc_naive(values["due_at"])
        if "application_id" in values and values["application_id"] is not None:
            if self.repository.get_application(session, profile.id, values["application_id"]) is None:
                raise WorkbenchApplicationNotFound("关联岗位不存在")
        if values.get("title") is None:
            values.pop("title", None)
        if values.get("priority") is None:
            values.pop("priority", None)
        if values.get("completed") is None:
            values.pop("completed", None)
        todo = self.repository.update_todo(session, todo, values, utc_now_naive())
        session.commit()
        return todo

    def delete_todo(self, session: Session, todo_id: int) -> None:
        profile = self._profile(session)
        todo = self.repository.get_todo(session, profile.id, todo_id)
        if todo is None:
            raise WorkbenchItemNotFound("待办不存在")
        self.repository.delete_todo(session, todo)
        session.commit()

    def list_interviews(
        self,
        session: Session,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[list[InterviewEvent], int]:
        start = to_utc_naive(start_at)
        end = to_utc_naive(end_at)
        if start is not None and end is not None and end <= start:
            raise InvalidWorkbenchRequest("结束时间必须晚于开始时间")
        profile = self._profile(session)
        result = self.repository.list_interviews(session, profile.id, start_at=start, end_at=end)
        session.commit()
        return result

    def create_interview(self, session: Session, values: dict) -> InterviewEvent:
        profile = self._profile(session)
        values = dict(values)
        values["starts_at"] = to_utc_naive(values["starts_at"])
        values["ends_at"] = to_utc_naive(values.get("ends_at"))
        self._validate_interview_range(values["starts_at"], values["ends_at"])
        if values.get("application_id") is not None and self.repository.get_application(
            session, profile.id, values["application_id"]
        ) is None:
            raise WorkbenchApplicationNotFound("关联岗位不存在")
        interview = self.repository.create_interview(session, profile.id, values)
        session.commit()
        return interview

    def update_interview(self, session: Session, interview_id: int, values: dict) -> InterviewEvent:
        profile = self._profile(session)
        interview = self.repository.get_interview(session, profile.id, interview_id)
        if interview is None:
            raise WorkbenchItemNotFound("面试安排不存在")
        values = dict(values)
        for key in ("starts_at", "ends_at"):
            if key in values:
                values[key] = to_utc_naive(values[key])
        starts_at = values.get("starts_at", interview.starts_at)
        if starts_at is None:
            raise InvalidWorkbenchRequest("面试开始时间不能为空")
        ends_at = values.get("ends_at", interview.ends_at)
        self._validate_interview_range(starts_at, ends_at)
        if "application_id" in values and values["application_id"] is not None:
            if self.repository.get_application(session, profile.id, values["application_id"]) is None:
                raise WorkbenchApplicationNotFound("关联岗位不存在")
        for key in ("title", "timezone", "interview_format"):
            if values.get(key) is None:
                values.pop(key, None)
        interview = self.repository.update_interview(session, interview, values)
        session.commit()
        return interview

    def delete_interview(self, session: Session, interview_id: int) -> None:
        profile = self._profile(session)
        interview = self.repository.get_interview(session, profile.id, interview_id)
        if interview is None:
            raise WorkbenchItemNotFound("面试安排不存在")
        self.repository.delete_interview(session, interview)
        session.commit()

    @staticmethod
    def _validate_interview_range(starts_at: datetime, ends_at: datetime | None) -> None:
        if ends_at is not None and ends_at <= starts_at:
            raise InvalidWorkbenchRequest("结束时间必须晚于开始时间")
