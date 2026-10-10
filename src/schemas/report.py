"""Structured job match report contract."""

from typing import Literal

from pydantic import BaseModel, Field


class MatchReport(BaseModel):
    summary: str
    match_score: int = Field(ge=0, le=100)
    recommendation: Literal["strong_match", "match", "observe", "not_recommended"]
    matched_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
