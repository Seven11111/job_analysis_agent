"""Initial ORM model set for the job research domain."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class JobSource(TimestampMixin, Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    terms_url: Mapped[str | None] = mapped_column(String(1000))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    jobs: Mapped[list["Job"]] = relationship(back_populates="source")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_jobs_source_job"),
        Index("ix_jobs_city_published", "city", "published_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("job_sources.id"), nullable=False, index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    district: Mapped[str | None] = mapped_column(String(64))
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_unit: Mapped[str | None] = mapped_column(String(32))
    salary_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    education: Mapped[str | None] = mapped_column(String(128))
    internship_months: Mapped[float | None] = mapped_column(Float)
    days_per_week: Mapped[int | None] = mapped_column(Integer)
    conversion_chance: Mapped[str | None] = mapped_column(String(32))
    detail_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_date: Mapped[date | None] = mapped_column(Date, index=True)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    source: Mapped[JobSource] = relationship(back_populates="jobs")
    snapshots: Mapped[list["JobSnapshot"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    skills: Mapped[list["JobSkill"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="job")
    matches: Mapped[list["JobMatch"]] = relationship(back_populates="job")


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"
    __table_args__ = (UniqueConstraint("job_id", "content_hash", name="uq_job_snapshots_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    salary_text: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False, default="provider_api")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="snapshots")


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_name", "skill_type", name="uq_job_skills_name_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False)
    skill_type: Mapped[str | None] = mapped_column(String(32))
    required_level: Mapped[str | None] = mapped_column(String(32))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    job: Mapped[Job] = relationship(back_populates="skills")


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school: Mapped[str | None] = mapped_column(String(200))
    major: Mapped[str | None] = mapped_column(String(200))
    education: Mapped[str | None] = mapped_column(String(64))
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    target_directions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    target_cities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    available_period: Mapped[str | None] = mapped_column(String(128))
    days_per_week: Mapped[int | None] = mapped_column(Integer)
    internship_months: Mapped[float | None] = mapped_column(Float)
    desired_industries: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    resumes: Mapped[list["ResumeVersion"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    resume_attachments: Mapped[list["ResumeAttachment"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    facts: Mapped[list["ProfileFact"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="profile")
    status_definitions: Mapped[list["ApplicationStatusDefinition"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    todos: Mapped[list["JobTodo"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    interviews: Mapped[list["InterviewEvent"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    matches: Mapped[list["JobMatch"]] = relationship(back_populates="profile")
    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    job_subscriptions: Mapped[list["JobSubscription"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ResumeVersion(TimestampMixin, Base):
    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[str | None] = mapped_column(Text)
    source_attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_attachments.id", ondelete="SET NULL", name="fk_resume_versions_source_attachment_id"),
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    profile: Mapped[CandidateProfile] = relationship(back_populates="resumes")
    source_attachment: Mapped["ResumeAttachment | None"] = relationship(back_populates="resume_versions")
    matches: Mapped[list["JobMatch"]] = relationship(back_populates="resume_version")


class ResumeAttachment(TimestampMixin, Base):
    __tablename__ = "resume_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_filename: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    draft_content: Mapped[str] = mapped_column(Text, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")

    profile: Mapped[CandidateProfile] = relationship(back_populates="resume_attachments")
    resume_versions: Mapped[list[ResumeVersion]] = relationship(back_populates="source_attachment")


class ProfileFact(TimestampMixin, Base):
    __tablename__ = "profile_facts"
    __table_args__ = (Index("ix_profile_facts_active_key", "profile_id", "status", "fact_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="temporary")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    confidence: Mapped[float | None] = mapped_column(Float)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    profile: Mapped[CandidateProfile] = relationship(back_populates="facts")


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_applications_profile_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    current_status_id: Mapped[int] = mapped_column(ForeignKey("application_status_definitions.id"), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_status_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)

    job: Mapped[Job] = relationship(back_populates="applications")
    profile: Mapped[CandidateProfile] = relationship(back_populates="applications")
    current_status: Mapped["ApplicationStatusDefinition"] = relationship(back_populates="applications")
    status_events: Mapped[list["ApplicationStatusEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    todos: Mapped[list["JobTodo"]] = relationship(back_populates="application")
    interviews: Mapped[list["InterviewEvent"]] = relationship(back_populates="application")


class ApplicationStatusDefinition(TimestampMixin, Base):
    __tablename__ = "application_status_definitions"
    __table_args__ = (UniqueConstraint("profile_id", "name", name="uq_status_definitions_profile_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    profile: Mapped[CandidateProfile] = relationship(back_populates="status_definitions")
    applications: Mapped[list[Application]] = relationship(back_populates="current_status")


class ApplicationStatusEvent(Base):
    __tablename__ = "application_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)
    from_status_id: Mapped[int | None] = mapped_column(ForeignKey("application_status_definitions.id"))
    to_status_id: Mapped[int] = mapped_column(ForeignKey("application_status_definitions.id"), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    application: Mapped[Application] = relationship(back_populates="status_events")
    from_status: Mapped[ApplicationStatusDefinition | None] = relationship(
        foreign_keys=[from_status_id]
    )
    to_status: Mapped[ApplicationStatusDefinition] = relationship(
        foreign_keys=[to_status_id]
    )


class JobTodo(TimestampMixin, Base):
    __tablename__ = "job_todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)

    profile: Mapped[CandidateProfile] = relationship(back_populates="todos")
    application: Mapped[Application | None] = relationship(back_populates="todos")


class InterviewEvent(TimestampMixin, Base):
    __tablename__ = "interview_events"
    __table_args__ = (Index("ix_interview_events_profile_starts_at", "profile_id", "starts_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    position_title: Mapped[str | None] = mapped_column(String(300))
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    interview_format: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    location: Mapped[str | None] = mapped_column(String(500))
    meeting_url: Mapped[str | None] = mapped_column(String(1000))
    note: Mapped[str | None] = mapped_column(Text)

    profile: Mapped[CandidateProfile] = relationship(back_populates="interviews")
    application: Mapped[Application | None] = relationship(back_populates="interviews")


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (Index("ix_job_matches_job_profile_created", "job_id", "profile_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    resume_version_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id"))
    match_score: Mapped[int | None] = mapped_column(Integer)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_points: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_points: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    risk_points: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    next_actions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_evidence: Mapped[str | None] = mapped_column(Text)
    raw_result: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="matches")
    profile: Mapped[CandidateProfile] = relationship(back_populates="matches")
    resume_version: Mapped[ResumeVersion | None] = relationship(back_populates="matches")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    profile: Mapped[CandidateProfile] = relationship(back_populates="sessions")
    messages: Mapped[list["AgentMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    run_events: Mapped[list["AgentRunEvent"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("agent_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    structured_content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    session: Mapped[AgentSession] = relationship(back_populates="messages")


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("agent_sessions.id"), nullable=False, index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("agent_messages.id"))
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)

    session: Mapped[AgentSession] = relationship(back_populates="run_events")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class JobSubscription(TimestampMixin, Base):
    __tablename__ = "job_subscriptions"
    __table_args__ = (Index("ix_job_subscriptions_enabled_next_run", "enabled", "next_run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    schedule_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    weekday: Mapped[int | None] = mapped_column(Integer)
    interval_days: Mapped[int | None] = mapped_column(Integer)
    month_day: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    profile: Mapped[CandidateProfile] = relationship(back_populates="job_subscriptions")
    runs: Mapped[list["JobSubscriptionRun"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    seen_jobs: Mapped[list["JobSubscriptionSeenJob"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )


class JobSubscriptionRun(Base):
    __tablename__ = "job_subscription_runs"
    __table_args__ = (Index("ix_job_subscription_runs_subscription_started", "subscription_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("job_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_results_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    subscription: Mapped[JobSubscription] = relationship(back_populates="runs")
    items: Mapped[list["JobSubscriptionRunItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class JobSubscriptionSeenJob(Base):
    """Minimal stable keys retained so previously surfaced jobs are not announced again."""

    __tablename__ = "job_subscription_seen_jobs"
    __table_args__ = (
        UniqueConstraint("subscription_id", "provider", "identity_hash", name="uq_subscription_seen_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("job_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    subscription: Mapped[JobSubscription] = relationship(back_populates="seen_jobs")


class JobSubscriptionRunItem(Base):
    """Short-lived display payload for one provider result in one subscription run."""

    __tablename__ = "job_subscription_run_items"
    __table_args__ = (
        UniqueConstraint("run_id", "provider", "identity_hash", name="uq_subscription_run_item_identity"),
        Index("ix_subscription_run_items_run_new", "run_id", "is_new"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("job_subscription_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    job_json: Mapped[str] = mapped_column(Text, nullable=False)
    saved_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    run: Mapped[JobSubscriptionRun] = relationship(back_populates="items")
