"""Uploaded resume and optional evaluation record."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.candidate import Candidate


class ResumeEvaluation(Base):
    __tablename__ = "resume_evaluations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    evaluation_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(40), default="pending_hr_review"
    )
    evaluation_status: Mapped[str] = mapped_column(
        String(40), default="pending"
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="resume_evaluations")
    application: Mapped["Application | None"] = relationship(
        back_populates="resume_evaluations"
    )

    @property
    def filename(self) -> str:
        return self.file_name
