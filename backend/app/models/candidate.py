"""Candidate profile model."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.interview import Interview
    from app.models.resume_evaluation import ResumeEvaluation
    from app.models.screening import Screening


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    hr_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    hr_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    resume_evaluations: Mapped[list["ResumeEvaluation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    screenings: Mapped[list["Screening"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
