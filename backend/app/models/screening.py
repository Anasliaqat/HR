"""Vapi screening call results."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.candidate import Candidate


class Screening(Base):
    __tablename__ = "screenings"
    __table_args__ = (
        Index(
            "uq_screenings_call_id",
            "call_id",
            unique=True,
            sqlite_where=text("call_id IS NOT NULL"),
            postgresql_where=text("call_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    call_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    call_status: Mapped[str] = mapped_column(String(40), default="queued")
    end_report_received: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    job_related_highlights: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_confirmed_on_call: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    consent_obtained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="screenings")
    application: Mapped["Application | None"] = relationship(back_populates="screenings")
