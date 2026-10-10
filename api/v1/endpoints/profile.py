"""Candidate profile, resume and explicit memory endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.deps import db_session
from api.v1.schemas.profile import (
    ProfileConfirmRequest,
    ProfileFactCreate,
    ProfileFactPatch,
    ProfileFactResponse,
    ProfileResponse,
    ProfileUpdate,
    ResumeAttachmentConfirmRequest,
    ResumeAttachmentDeleteResponse,
    ResumeAttachmentResponse,
    ResumeCreate,
    ResumeDetailResponse,
    ResumeResponse,
)
from src.db.models import CandidateProfile, ProfileFact, ResumeVersion
from src.llm.adapter import LLMGenerationError, LLMNotConfiguredError
from src.services.profile_service import (
    ProfileFactNotFound,
    ProfileService,
    ResumeAttachmentNotFound,
    ResumeConsentRequired,
    ResumeNotFound,
)
from src.services.resume_document import MAX_RESUME_BYTES, ResumeDocumentError

router = APIRouter(prefix="/profile", tags=["profile"])
service = ProfileService()


def serialize_fact(fact: ProfileFact) -> dict:
    return {
        "id": fact.id,
        "fact_type": fact.fact_type,
        "fact_key": fact.fact_key,
        "fact_value": fact.fact_value,
        "status": fact.status,
        "source": fact.source,
        "confidence": fact.confidence,
        "confirmed_at": fact.confirmed_at,
        "valid_from": fact.valid_from,
        "valid_to": fact.valid_to,
        "created_at": fact.created_at,
        "updated_at": fact.updated_at,
    }


def serialize_resume(resume: ResumeVersion) -> dict:
    return {
        "id": resume.id,
        "title": resume.title,
        "is_current": resume.is_current,
        "created_at": resume.created_at,
        "updated_at": resume.updated_at,
        "text_preview": service.resume_preview(resume),
        "has_content": bool(resume.raw_text.strip()),
        "source_attachment_id": resume.source_attachment_id,
    }


def serialize_attachment(attachment, *, include_draft: bool = True) -> dict:
    linked_resume = max(attachment.resume_versions, key=lambda resume: resume.id, default=None)
    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "sha256": attachment.sha256,
        "parse_status": attachment.parse_status,
        "created_at": attachment.created_at,
        "linked_resume_version_id": linked_resume.id if linked_resume else None,
        "draft_content": (
            json.loads(attachment.draft_content)
            if include_draft and attachment.parse_status == "pending_review"
            else None
        ),
    }


def serialize_profile(profile: CandidateProfile) -> dict:
    facts = [fact for fact in profile.facts if fact.status == "active"]
    return {
        "id": profile.id,
        "school": profile.school,
        "major": profile.major,
        "education": profile.education,
        "graduation_year": profile.graduation_year,
        "target_directions": service.repository.decode_list(profile.target_directions),
        "target_cities": service.repository.decode_list(profile.target_cities),
        "available_period": profile.available_period,
        "days_per_week": profile.days_per_week,
        "internship_months": profile.internship_months,
        "desired_industries": service.repository.decode_list(profile.desired_industries),
        "resumes": [serialize_resume(resume) for resume in profile.resumes],
        "active_facts": [serialize_fact(fact) for fact in facts],
    }


def raise_profile_error(exc: Exception) -> None:
    if isinstance(exc, (ProfileFactNotFound, ResumeNotFound, ResumeAttachmentNotFound)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    raise exc


@router.get("", response_model=ProfileResponse, summary="查询个人画像")
def get_profile(session: Session = Depends(db_session)) -> dict:
    return serialize_profile(service.get_profile(session))


@router.put("", response_model=ProfileResponse, summary="更新个人画像")
def update_profile(request: ProfileUpdate, session: Session = Depends(db_session)) -> dict:
    profile = service.update_profile(session, request.model_dump())
    return serialize_profile(profile)


@router.get("/facts", response_model=list[ProfileFactResponse], summary="查询画像事实")
def list_facts(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|superseded|temporary|deleted)$"),
    session: Session = Depends(db_session),
) -> list[dict]:
    return [serialize_fact(fact) for fact in service.list_facts(session, status_filter)]


@router.post("/facts", response_model=ProfileFactResponse, summary="新增画像事实")
def create_fact(request: ProfileFactCreate, session: Session = Depends(db_session)) -> dict:
    return serialize_fact(service.create_fact(session, request.model_dump()))


@router.patch("/facts/{fact_id}", response_model=ProfileFactResponse, summary="修改画像事实")
def update_fact(fact_id: int, request: ProfileFactPatch, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_fact(service.update_fact(session, fact_id, request.model_dump(exclude_unset=True)))
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.delete("/facts/{fact_id}", response_model=ProfileFactResponse, summary="删除画像事实")
def delete_fact(fact_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_fact(service.delete_fact(session, fact_id))
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.post("/confirm", response_model=list[ProfileFactResponse], summary="确认画像事实")
def confirm_facts(request: ProfileConfirmRequest, session: Session = Depends(db_session)) -> list[dict]:
    try:
        facts = service.confirm_facts(session, request.fact_ids, request.replace_fact_ids)
        return [serialize_fact(fact) for fact in facts]
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.get("/resumes", response_model=list[ResumeResponse], summary="查询简历版本")
def list_resumes(session: Session = Depends(db_session)) -> list[dict]:
    return [serialize_resume(resume) for resume in service.list_resumes(session)]


@router.post("/resumes", response_model=ResumeResponse, summary="新增简历版本")
def create_resume(request: ResumeCreate, session: Session = Depends(db_session)) -> dict:
    try:
        resume = service.create_resume(
            session,
            title=request.title,
            raw_text=request.raw_text,
            structured_content=request.structured_content.model_dump() if request.structured_content else None,
            set_current=request.set_current,
            source_attachment_id=request.source_attachment_id,
        )
        return serialize_resume(resume)
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.post("/resumes/{resume_id}/select", response_model=ResumeResponse, summary="选择当前简历")
def select_resume(resume_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return serialize_resume(service.select_resume(session, resume_id))
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.post("/resume-attachments/parse", response_model=ResumeAttachmentResponse, summary="上传并解析附件简历")
def parse_resume_attachment(
    file: UploadFile = File(...),
    consent_to_model: bool = Form(...),
    session: Session = Depends(db_session),
) -> dict:
    content = file.file.read(MAX_RESUME_BYTES + 1)
    try:
        attachment = service.parse_resume_attachment(
            session,
            filename=file.filename or "resume",
            content=content,
            consent_to_model=consent_to_model,
        )
        return serialize_attachment(attachment)
    except ResumeConsentRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "consent_required", "message": str(exc)},
        ) from exc
    except ResumeDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_resume_file", "message": str(exc)},
        ) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_not_configured", "message": str(exc)},
        ) from exc
    except LLMGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "generation_failed", "message": "模型解析简历失败，请稍后重试。"},
        ) from exc
    finally:
        file.file.close()


@router.get("/resume-attachments", response_model=list[ResumeAttachmentResponse], summary="查询附件简历")
def list_resume_attachments(session: Session = Depends(db_session)) -> list[dict]:
    return [serialize_attachment(item) for item in service.list_resume_attachments(session)]


@router.post(
    "/resume-attachments/{attachment_id}/confirm",
    response_model=ResumeResponse,
    summary="确认解析结果并保存为在线简历",
)
def confirm_resume_attachment(
    attachment_id: int,
    request: ResumeAttachmentConfirmRequest,
    session: Session = Depends(db_session),
) -> dict:
    try:
        resume = service.confirm_resume_attachment(
            session,
            attachment_id=attachment_id,
            title=request.title,
            structured_content=request.structured_content.model_dump(),
            set_current=request.set_current,
        )
        return serialize_resume(resume)
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.get("/resume-attachments/{attachment_id}/file", summary="下载原始附件简历")
def download_resume_attachment(attachment_id: int, session: Session = Depends(db_session)) -> FileResponse:
    try:
        attachment = service.get_resume_attachment(session, attachment_id)
        file_path = service.attachment_file_path(attachment)
    except ResumeAttachmentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    return FileResponse(
        file_path,
        media_type=attachment.content_type,
        filename=Path(attachment.original_filename).name,
    )


@router.delete(
    "/resume-attachments/{attachment_id}",
    response_model=ResumeAttachmentDeleteResponse,
    summary="删除附件简历",
)
def delete_resume_attachment(attachment_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        service.delete_resume_attachment(session, attachment_id)
        return {"id": attachment_id, "deleted": True}
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")


@router.get("/resumes/{resume_id}", response_model=ResumeDetailResponse, summary="查询在线简历详情")
def get_resume_detail(resume_id: int, session: Session = Depends(db_session)) -> dict:
    try:
        return service.resume_detail(session, resume_id)
    except Exception as exc:
        raise_profile_error(exc)
        raise AssertionError("unreachable")
