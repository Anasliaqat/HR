"""Interview scheduling request and response schemas."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class InterviewSlot(BaseModel):
    start_at: datetime
    end_at: datetime


class AvailableSlotsResponse(BaseModel):
    available_slots: list[InterviewSlot]
    message: str
    test_mode: bool = True


class InterviewScheduleRequest(BaseModel):
    candidate_id: UUID
    job_id: UUID
    interviewer_email: EmailStr
    start_at: datetime
    duration_minutes: int = Field(default=30, ge=15, le=240)
    interview_mode: str | None = None
    meeting_details: str | None = Field(default=None, max_length=1000)
    hr_approved: bool = Field(
        description="HR approval to create the calendar event and schedule this interview."
    )

    @field_validator("start_at")
    @classmethod
    def require_timezone_and_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_at must include a timezone")
        if value <= datetime.now(timezone.utc):
            raise ValueError("start_at must be in the future")
        return value

    @field_validator("interview_mode")
    @classmethod
    def validate_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in {"online", "on_site"}:
            raise ValueError("interview_mode must be online or on_site")
        return value


class InterviewRescheduleRequest(BaseModel):
    start_at: datetime
    duration_minutes: int = Field(default=30, ge=15, le=240)
    hr_approved: bool = Field(
        description="HR approval to update the calendar event and interview time."
    )

    @field_validator("start_at")
    @classmethod
    def require_timezone_and_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_at must include a timezone")
        if value <= datetime.now(timezone.utc):
            raise ValueError("start_at must be in the future")
        return value


class InterviewResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID
    interviewer_email: EmailStr
    interview_mode: str | None = None
    meeting_details: str | None = None
    start_at: datetime
    end_at: datetime
    status: str = "scheduled"
    calendar_event_id: str | None = None
    notifications_status: str = "not_sent"
    notification_error: str | None = None
    test_mode: bool = True

    model_config = ConfigDict(from_attributes=True)

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_database_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class InterviewUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"completed", "cancelled"}:
            raise ValueError("status must be completed or cancelled")
        return value


class InterviewDetailsUpdate(BaseModel):
    interview_mode: str
    meeting_details: str = Field(min_length=1, max_length=1000)

    @field_validator("interview_mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"online", "on_site"}:
            raise ValueError("interview_mode must be online or on_site")
        return value


def interview_end_time(start_at: datetime, duration_minutes: int) -> datetime:
    return start_at + timedelta(minutes=duration_minutes)
