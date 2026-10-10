"""Structured online-resume data produced from a user-provided resume."""

from pydantic import BaseModel, Field


class ResumeBasics(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    city: str | None = Field(default=None, max_length=64)
    school: str | None = Field(default=None, max_length=200)
    major: str | None = Field(default=None, max_length=200)
    education: str | None = Field(default=None, max_length=64)
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)


class ResumeJobIntent(BaseModel):
    target_positions: list[str] = Field(default_factory=list)
    target_cities: list[str] = Field(default_factory=list)
    internship_type: str | None = None
    availability: str | None = None
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    expected_salary: str | None = None


class ResumeEducationEntry(BaseModel):
    school: str | None = None
    degree: str | None = None
    major: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ResumeExperienceEntry(BaseModel):
    organization: str | None = None
    role: str | None = None
    experience_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    achievements: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class ResumeCampusExperience(ResumeExperienceEntry):
    """Student organization, campus role, competition, or volunteer experience."""


class ResumeProjectEntry(BaseModel):
    name: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ResumeStructuredContent(BaseModel):
    basics: ResumeBasics = Field(default_factory=ResumeBasics)
    job_intent: ResumeJobIntent = Field(default_factory=ResumeJobIntent)
    education: list[ResumeEducationEntry] = Field(default_factory=list)
    campus_experiences: list[ResumeCampusExperience] = Field(default_factory=list)
    experience: list[ResumeExperienceEntry] = Field(default_factory=list)
    projects: list[ResumeProjectEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    summary: str | None = None
