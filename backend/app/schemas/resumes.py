"""Resume request and response schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResumeResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    filename: str
    content_type: str | None
    uploaded_at: datetime
    application_id: UUID | None = None
    evaluation_status: Literal["pending", "processing", "completed", "failed"] = "pending"
    score: int | None = None
    explanation: str | None = None
    review_status: str = "pending_hr_review"
    extracted_skills: list[str] = Field(default_factory=list)
    evaluation_details: dict[str, Any] | None = None
    job_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeEvaluationResponse(BaseModel):
    resume_id: UUID
    score: int
    explanation: str
    evaluation_status: Literal["completed"] = "completed"
    job_id: UUID | None = None
    job_title: str | None = None
    extracted_text: str | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    skill_match_reasons: dict[str, str] = Field(default_factory=dict)
    excluded_rubric_categories: list[str] = Field(default_factory=list)
    relevant_experience: list[str] = Field(default_factory=list)
    relevant_projects: list[str] = Field(default_factory=list)
    education_and_certifications: list[str] = Field(default_factory=list)
    candidate_strengths: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rubric_scores: dict[str, float] = Field(default_factory=dict)
    review_status: Literal["pending_hr_review"] = "pending_hr_review"


class ResumeEvaluationRequest(BaseModel):
    job_id: UUID | None = None
    force: bool = False
