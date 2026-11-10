"""Job application request and response schemas."""

from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApplicationCreate(BaseModel):
    candidate_id: UUID
    job_id: UUID


class ApplicationResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID
    status: str = Field(default="pending_review")
    applied_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationUpdate(BaseModel):
    status: Literal[
        "pending_review",
        "screening",
        "interview",
        "hired",
        "withdrawn",
        "rejected_by_hr",
        "rejected",
        "interview_eligible",
        "approved_by_hr",
        "over_agent_review",
    ]
