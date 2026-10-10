"""Persistence operations for the single local candidate profile."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.models import CandidateProfile, ProfileFact, ResumeAttachment, ResumeVersion


class ProfileRepository:
    def ensure_profile(self, session: Session) -> CandidateProfile:
        profile = session.scalar(
            select(CandidateProfile)
            .options(selectinload(CandidateProfile.resumes), selectinload(CandidateProfile.facts))
            .where(CandidateProfile.active.is_(True))
            .order_by(CandidateProfile.id)
        )
        if profile is None:
            profile = CandidateProfile(
                target_directions="[]",
                target_cities="[]",
                desired_industries="[]",
                active=True,
            )
            session.add(profile)
            session.flush()
        return profile

    @staticmethod
    def encode_list(values: list[str]) -> str:
        return json.dumps(values, ensure_ascii=False)

    @staticmethod
    def decode_list(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []

    def list_facts(self, session: Session, profile_id: int, status_filter: str | None) -> list[ProfileFact]:
        statement = select(ProfileFact).where(ProfileFact.profile_id == profile_id)
        if status_filter:
            statement = statement.where(ProfileFact.status == status_filter)
        else:
            statement = statement.where(ProfileFact.status == "active")
        return list(session.scalars(statement.order_by(ProfileFact.updated_at.desc(), ProfileFact.id.desc())))

    def get_fact(self, session: Session, profile_id: int, fact_id: int) -> ProfileFact | None:
        return session.scalar(
            select(ProfileFact).where(ProfileFact.profile_id == profile_id, ProfileFact.id == fact_id)
        )

    def get_resume(self, session: Session, profile_id: int, resume_id: int) -> ResumeVersion | None:
        return session.scalar(
            select(ResumeVersion).where(ResumeVersion.profile_id == profile_id, ResumeVersion.id == resume_id)
        )

    def list_resumes(self, session: Session, profile_id: int) -> list[ResumeVersion]:
        return list(
            session.scalars(
                select(ResumeVersion)
                .where(ResumeVersion.profile_id == profile_id)
                .order_by(ResumeVersion.is_current.desc(), ResumeVersion.updated_at.desc())
            )
        )

    def get_attachment(self, session: Session, profile_id: int, attachment_id: int) -> ResumeAttachment | None:
        return session.scalar(
            select(ResumeAttachment)
            .options(selectinload(ResumeAttachment.resume_versions))
            .where(ResumeAttachment.profile_id == profile_id, ResumeAttachment.id == attachment_id)
        )

    def list_attachments(self, session: Session, profile_id: int) -> list[ResumeAttachment]:
        return list(
            session.scalars(
                select(ResumeAttachment)
                .options(selectinload(ResumeAttachment.resume_versions))
                .where(ResumeAttachment.profile_id == profile_id)
                .order_by(ResumeAttachment.created_at.desc(), ResumeAttachment.id.desc())
            )
        )

    def set_current_resume(self, session: Session, profile_id: int, resume: ResumeVersion) -> ResumeVersion:
        session.query(ResumeVersion).filter(
            ResumeVersion.profile_id == profile_id, ResumeVersion.id != resume.id
        ).update({ResumeVersion.is_current: False}, synchronize_session=False)
        resume.is_current = True
        session.flush()
        return resume

    def now(self) -> datetime:
        return datetime.utcnow()
