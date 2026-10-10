from datetime import datetime

from pydantic import BaseModel, Field


class MatchCreateRequest(BaseModel):
    resume_version_id: int | None = Field(default=None, gt=0)


class MatchResponse(BaseModel):
    id: int
    summary: str
    match_score: int
    recommendation: str
    matched_points: list[str]
    missing_points: list[str]
    risk_points: list[str]
    next_actions: list[str]
    analysis_mode: str
    evidence: dict | list
    created_at: datetime
