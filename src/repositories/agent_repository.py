"""Persistence for local Agent sessions, messages and observable run events."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.db.models import AgentMessage, AgentRunEvent, AgentSession


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentRepository:
    def create_session(self, db: Session, *, profile_id: int, title: str | None) -> AgentSession:
        record = AgentSession(profile_id=profile_id, title=title or "新对话")
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_sessions(self, db: Session, *, profile_id: int) -> list[AgentSession]:
        records = list(
            db.scalars(
                select(AgentSession)
                .where(AgentSession.profile_id == profile_id, AgentSession.status == "active")
                .order_by(AgentSession.updated_at.desc(), AgentSession.id.desc())
            )
        )
        counts = dict(
            db.execute(
                select(AgentMessage.session_id, func.count(AgentMessage.id))
                .where(AgentMessage.session_id.in_([item.id for item in records]))
                .group_by(AgentMessage.session_id)
            ).all()
        ) if records else {}
        for record in records:
            record._message_count = int(counts.get(record.id, 0))
        return records

    def get_session(self, db: Session, *, profile_id: int, session_id: int) -> AgentSession | None:
        return db.scalar(
            select(AgentSession)
            .options(selectinload(AgentSession.messages))
            .where(AgentSession.id == session_id, AgentSession.profile_id == profile_id)
        )

    def rename_session(self, db: Session, record: AgentSession, title: str) -> AgentSession:
        record.title = title.strip()
        record.updated_at = _now_utc_naive()
        db.commit()
        db.refresh(record)
        return record

    def add_message(
        self,
        db: Session,
        *,
        session_record: AgentSession,
        role: str,
        content: str | None,
        structured_content: dict | None = None,
    ) -> AgentMessage:
        record = AgentMessage(
            session_id=session_record.id,
            role=role,
            content_text=content,
            structured_content=(
                json.dumps(structured_content, ensure_ascii=False, separators=(",", ":"))
                if structured_content is not None
                else None
            ),
        )
        session_record.updated_at = _now_utc_naive()
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_messages(self, db: Session, *, session_id: int, limit: int = 16) -> list[AgentMessage]:
        records = list(
            db.scalars(
                select(AgentMessage)
                .where(AgentMessage.session_id == session_id)
                .order_by(AgentMessage.id.desc())
                .limit(limit)
            )
        )
        return list(reversed(records))

    def add_event(
        self,
        db: Session,
        *,
        session_id: int,
        run_id: str,
        event_type: str,
        name: str | None,
        status: str,
        payload: dict | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> AgentRunEvent:
        sequence = int(
            db.scalar(select(func.max(AgentRunEvent.sequence)).where(AgentRunEvent.run_id == run_id)) or 0
        ) + 1
        record = AgentRunEvent(
            session_id=session_id,
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            name=name,
            status=status,
            payload=(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload is not None else None),
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_events(
        self,
        db: Session,
        *,
        session_id: int,
        run_id: str | None = None,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[AgentRunEvent]:
        statement = select(AgentRunEvent).where(
            AgentRunEvent.session_id == session_id,
        )
        if run_id:
            statement = statement.where(
                AgentRunEvent.run_id == run_id,
                AgentRunEvent.sequence > after_sequence,
            )
        return list(db.scalars(statement.order_by(AgentRunEvent.id).limit(limit)))

    def list_recent_events_with_pending_actions(
        self,
        db: Session,
        *,
        session_id: int,
        limit: int = 200,
    ) -> list[AgentRunEvent]:
        recent = list(
            db.scalars(
                select(AgentRunEvent)
                .where(AgentRunEvent.session_id == session_id)
                .order_by(AgentRunEvent.id.desc())
                .limit(limit)
            )
        )
        pending = self.list_pending_actions(db, session_id=session_id)
        by_id = {event.id: event for event in (*recent, *pending)}
        return sorted(by_id.values(), key=lambda event: event.id)

    def list_pending_actions(self, db: Session, *, session_id: int) -> list[AgentRunEvent]:
        return list(
            db.scalars(
                select(AgentRunEvent)
                .where(
                    AgentRunEvent.session_id == session_id,
                    AgentRunEvent.event_type == "action_proposed",
                    AgentRunEvent.status == "pending",
                )
                .order_by(AgentRunEvent.id)
            )
        )

    def get_event(self, db: Session, *, event_id: int) -> AgentRunEvent | None:
        return db.scalar(
            select(AgentRunEvent)
            .options(selectinload(AgentRunEvent.session))
            .where(AgentRunEvent.id == event_id)
        )
