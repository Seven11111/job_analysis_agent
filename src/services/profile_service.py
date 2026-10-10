"""Profile, resume and explicit long-term memory business rules."""

from __future__ import annotations

import json
import hashlib
import logging
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from src.config import PROJECT_ROOT
from src.db.models import CandidateProfile, ProfileFact, ResumeAttachment, ResumeVersion
from src.schemas.resume import ResumeStructuredContent
from src.repositories.profile_repository import ProfileRepository
from src.services.resume_document import extract_resume_text
from src.services.resume_parser import ResumeParserService
from src.services.privacy import mask_sensitive_text


logger = logging.getLogger(__name__)
ATTACHMENT_DIRECTORY = PROJECT_ROOT / "data" / "resume_attachments"
_SAFE_STORAGE_FILENAME = re.compile(r"^[a-f0-9]{32}\.(?:pdf|docx)$")


class ProfileFactNotFound(Exception):
    pass


class ResumeNotFound(Exception):
    pass


class ResumeAttachmentNotFound(Exception):
    pass


class ResumeConsentRequired(Exception):
    pass


class ProfileService:
    def __init__(
        self,
        repository: ProfileRepository | None = None,
        resume_parser: ResumeParserService | None = None,
    ):
        self.repository = repository or ProfileRepository()
        self.resume_parser = resume_parser or ResumeParserService()

    def get_profile(self, session: Session) -> CandidateProfile:
        return self.repository.ensure_profile(session)

    def update_profile(self, session: Session, payload: dict) -> CandidateProfile:
        profile = self.repository.ensure_profile(session)
        for key, value in payload.items():
            if key in {"target_directions", "target_cities", "desired_industries"}:
                value = self.repository.encode_list(value)
            setattr(profile, key, value)
        session.commit()
        return self.repository.ensure_profile(session)

    def list_facts(self, session: Session, status_filter: str | None) -> list[ProfileFact]:
        profile = self.repository.ensure_profile(session)
        return self.repository.list_facts(session, profile.id, status_filter)

    def create_fact(self, session: Session, payload: dict) -> ProfileFact:
        profile = self.repository.ensure_profile(session)
        confirmed = payload.pop("confirmed", False)
        fact = ProfileFact(
            profile_id=profile.id,
            status="active" if confirmed else "temporary",
            confirmed_at=self.repository.now() if confirmed else None,
            **payload,
        )
        session.add(fact)
        session.commit()
        session.refresh(fact)
        return fact

    def update_fact(self, session: Session, fact_id: int, payload: dict) -> ProfileFact:
        profile = self.repository.ensure_profile(session)
        fact = self.repository.get_fact(session, profile.id, fact_id)
        if fact is None:
            raise ProfileFactNotFound("画像事实不存在")
        if payload.get("status") == "active" and fact.status != "active":
            fact.confirmed_at = self.repository.now()
        for key, value in payload.items():
            if value is not None:
                setattr(fact, key, value)
        session.commit()
        session.refresh(fact)
        return fact

    def delete_fact(self, session: Session, fact_id: int) -> ProfileFact:
        return self.update_fact(session, fact_id, {"status": "deleted"})

    def confirm_facts(self, session: Session, fact_ids: list[int], replace_fact_ids: list[int]) -> list[ProfileFact]:
        profile = self.repository.ensure_profile(session)
        facts = [self.repository.get_fact(session, profile.id, fact_id) for fact_id in fact_ids]
        if any(fact is None for fact in facts):
            raise ProfileFactNotFound("待确认的画像事实不存在")
        for fact in facts:
            fact.status = "active"
            fact.confirmed_at = self.repository.now()
        for fact_id in replace_fact_ids:
            old_fact = self.repository.get_fact(session, profile.id, fact_id)
            if old_fact is None:
                raise ProfileFactNotFound("待替代的画像事实不存在")
            old_fact.status = "superseded"
        session.commit()
        return [fact for fact in facts if fact is not None]

    def list_resumes(self, session: Session) -> list[ResumeVersion]:
        profile = self.repository.ensure_profile(session)
        return self.repository.list_resumes(session, profile.id)

    def create_resume(
        self,
        session: Session,
        *,
        title: str,
        raw_text: str,
        structured_content: dict | None,
        set_current: bool,
        source_attachment_id: int | None = None,
    ) -> ResumeVersion:
        profile = self.repository.ensure_profile(session)
        existing_resumes = self.repository.list_resumes(session, profile.id)
        attachment = None
        if source_attachment_id is not None:
            attachment = self.repository.get_attachment(session, profile.id, source_attachment_id)
            if attachment is None:
                raise ResumeAttachmentNotFound("附件简历不存在")
        resume = ResumeVersion(
            profile_id=profile.id,
            title=title,
            raw_text=raw_text,
            structured_content=json.dumps(structured_content, ensure_ascii=False) if structured_content else None,
            source_attachment_id=source_attachment_id,
            is_current=False,
        )
        session.add(resume)
        session.flush()
        if set_current or not existing_resumes:
            self.repository.set_current_resume(session, profile.id, resume)
        session.commit()
        session.refresh(resume)
        return resume

    def parse_resume_attachment(
        self,
        session: Session,
        *,
        filename: str,
        content: bytes,
        consent_to_model: bool,
    ) -> ResumeAttachment:
        if not consent_to_model:
            raise ResumeConsentRequired("请先确认同意将脱敏后的简历文本发送给当前配置的模型进行解析。")
        extracted_text, extension, content_type = extract_resume_text(filename, content)
        parsed = self.resume_parser.parse(extracted_text)
        safe_original_filename = _safe_original_filename(filename, extension)
        storage_filename = f"{uuid4().hex}{extension}"
        storage_path = _attachment_path(storage_filename)
        profile = self.repository.ensure_profile(session)
        attachment = ResumeAttachment(
            profile_id=profile.id,
            original_filename=safe_original_filename,
            storage_filename=storage_filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            extracted_text=extracted_text,
            draft_content=json.dumps(parsed.model_dump(), ensure_ascii=False),
            parse_status="pending_review",
        )
        try:
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage_path.write_bytes(content)
            session.add(attachment)
            session.commit()
            session.refresh(attachment)
            return attachment
        except Exception:
            session.rollback()
            storage_path.unlink(missing_ok=True)
            raise

    def list_resume_attachments(self, session: Session) -> list[ResumeAttachment]:
        profile = self.repository.ensure_profile(session)
        return self.repository.list_attachments(session, profile.id)

    def get_resume_attachment(self, session: Session, attachment_id: int) -> ResumeAttachment:
        profile = self.repository.ensure_profile(session)
        attachment = self.repository.get_attachment(session, profile.id, attachment_id)
        if attachment is None:
            raise ResumeAttachmentNotFound("附件简历不存在")
        return attachment

    def confirm_resume_attachment(
        self,
        session: Session,
        *,
        attachment_id: int,
        title: str,
        structured_content: dict,
        set_current: bool,
    ) -> ResumeVersion:
        attachment = self.get_resume_attachment(session, attachment_id)
        if attachment.parse_status != "pending_review":
            raise ResumeNotFound("该附件已确认或不可再次确认，请从在线简历创建新版本。")
        structured = ResumeStructuredContent.model_validate(structured_content)
        profile = self.repository.ensure_profile(session)
        existing_resumes = self.repository.list_resumes(session, profile.id)
        resume = ResumeVersion(
            profile_id=profile.id,
            title=title.strip(),
            raw_text=attachment.extracted_text,
            structured_content=json.dumps(structured.model_dump(), ensure_ascii=False),
            source_attachment_id=attachment.id,
            is_current=False,
        )
        session.add(resume)
        attachment.parse_status = "confirmed"
        session.flush()
        if set_current or not existing_resumes:
            self.repository.set_current_resume(session, profile.id, resume)
        session.commit()
        session.refresh(resume)
        return resume

    def delete_resume_attachment(self, session: Session, attachment_id: int) -> ResumeAttachment:
        attachment = self.get_resume_attachment(session, attachment_id)
        storage_filename = attachment.storage_filename
        if not _SAFE_STORAGE_FILENAME.fullmatch(storage_filename):
            raise ValueError("附件存储信息无效，已拒绝删除。")
        for resume in attachment.resume_versions:
            resume.source_attachment_id = None
        session.delete(attachment)
        session.commit()
        try:
            _attachment_path(storage_filename).unlink(missing_ok=True)
        except OSError:
            logger.warning("Unable to remove local resume attachment file after DB deletion")
        return attachment

    def resume_detail(self, session: Session, resume_id: int) -> dict:
        profile = self.repository.ensure_profile(session)
        resume = self.repository.get_resume(session, profile.id, resume_id)
        if resume is None:
            raise ResumeNotFound("简历版本不存在")
        return {
            "id": resume.id,
            "title": resume.title,
            "is_current": resume.is_current,
            "raw_text": resume.raw_text,
            "structured_content": (
                ResumeStructuredContent.model_validate(json.loads(resume.structured_content)).model_dump()
                if resume.structured_content
                else None
            ),
            "source_attachment_id": resume.source_attachment_id,
            "text_preview": self.resume_preview(resume),
            "has_content": bool(resume.raw_text.strip()),
            "created_at": resume.created_at,
            "updated_at": resume.updated_at,
        }

    @staticmethod
    def attachment_file_path(attachment: ResumeAttachment) -> Path:
        if not _SAFE_STORAGE_FILENAME.fullmatch(attachment.storage_filename):
            raise ValueError("附件存储信息无效，已拒绝访问。")
        path = _attachment_path(attachment.storage_filename)
        if not path.is_file():
            raise ResumeAttachmentNotFound("附件文件不存在，请删除记录后重新上传。")
        return path

    def select_resume(self, session: Session, resume_id: int) -> ResumeVersion:
        profile = self.repository.ensure_profile(session)
        resume = self.repository.get_resume(session, profile.id, resume_id)
        if resume is None:
            raise ResumeNotFound("简历版本不存在")
        self.repository.set_current_resume(session, profile.id, resume)
        session.commit()
        session.refresh(resume)
        return resume

    @staticmethod
    def resume_preview(resume: ResumeVersion, max_length: int = 180) -> str:
        preview = mask_sensitive_text(" ".join(resume.raw_text.split()))
        return preview if len(preview) <= max_length else f"{preview[:max_length]}…"


def _safe_original_filename(filename: str, extension: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    basename = "".join(character for character in basename if character.isprintable() and character not in "/\\")
    basename = basename.strip()[:255]
    return basename if basename.lower().endswith(extension) else f"{Path(basename).stem or 'resume'}{extension}"


def _attachment_path(storage_filename: str) -> Path:
    if not _SAFE_STORAGE_FILENAME.fullmatch(storage_filename):
        raise ValueError("附件存储信息无效。")
    root = ATTACHMENT_DIRECTORY.resolve()
    path = (root / storage_filename).resolve()
    if path.parent != root:
        raise ValueError("附件路径无效。")
    return path
