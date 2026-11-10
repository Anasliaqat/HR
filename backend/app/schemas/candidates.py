"""Candidate request and response schemas."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CandidateCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    details: dict[str, object] = Field(default_factory=dict)
    email_consent: bool = False


class CandidateResponse(CandidateCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hr_approved: bool = False
    hr_approved_at: datetime | None = None
    email_consent_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CandidateEmailConsentUpdate(BaseModel):
    email_consent: bool
