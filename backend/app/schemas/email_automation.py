"""Email automation API schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

EmailType = Literal[
    "rejection",
    "selection",
    "screening_invitation",
    "interview_invitation",
]
EmailDecision = Literal["approve", "reject"]


class EmailLogResponse(BaseModel):
    id: UUID
    recipient_email: str
    subject: str
    email_type: str
    body: str | None
    status: str
    provider_message_id: str | None
    error_message: str | None
    sent_at: datetime | None
    deleted_at: datetime | None = None
    created_at: datetime
    application_id: UUID | None
    interview_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class EmailApplicationResponse(BaseModel):
    application_id: UUID
    candidate_id: UUID
    candidate_name: str
    recipient_email: str
    email_consent: bool
    email_consent_at: datetime | None
    job_id: UUID
    job_title: str
    cv_score: int | None
    score_action: str | None
    application_status: str
    matched_skills: list[str]
    missing_skills: list[str]
    review_reason: str | None
    emails: list[EmailLogResponse]


class AgentReviewQueueItem(BaseModel):
    application_id: UUID
    candidate_id: UUID
    candidate_name: str
    recipient_email: str
    job_id: UUID
    job_title: str
    cv_score: int | None
    matched_skills: list[str]
    missing_skills: list[str]
    reason: str
    status: str


class AgentReviewDecisionResponse(BaseModel):
    application_id: UUID
    status: str
    review_reason: str
    email: EmailLogResponse | None = None


class EmailPreviewResponse(BaseModel):
    email_type: EmailType
    recipient_email: str
    subject: str
    body: str
    can_send: bool
    reason: str | None = None


class EmailDecisionRequest(BaseModel):
    decision: EmailDecision


class EmailSendRequest(BaseModel):
    email_type: EmailType
    interview_id: UUID | None = None
