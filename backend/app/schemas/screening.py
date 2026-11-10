"""Candidate screening request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ScreeningStartRequest(BaseModel):
    application_id: UUID
    consent_confirmed: bool = Field(
        description=(
            "HR confirms the candidate consented to screening, any configured call "
            "recording, transcription, and AI-generated summary."
        )
    )


class ScreeningResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    application_id: UUID | None
    status: Literal[
        "not_started", "queued", "ringing", "in_progress", "completed", "failed"
    ]
    call_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: str | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    job_related_highlights: list[str] = Field(default_factory=list)
    interview_availability: str | None = None
    transcript: str | None = None
    recording_url: str | None = None
    ended_reason: str | None = None
    consent_confirmed_on_call: bool | None = None
    consent_obtained_at: datetime | None = None
    created_at: datetime


class ScreeningDashboardResponse(ScreeningResponse):
    candidate_name: str
    phone: str | None
    job_title: str | None


class VapiWebhookResponse(BaseModel):
    status: Literal["ok"] = "ok"
