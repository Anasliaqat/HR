"""Candidate application to a job."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.agent_run import AgentRun
    from app.models.email_log import EmailLog
    from app.models.job import Job
    from app.models.resume_evaluation import ResumeEvaluation
    from app.models.screening import Screening


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_application_candidate_job"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="pending_review")
    agent_review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")
    resume_evaluations: Mapped[list["ResumeEvaluation"]] = relationship(
        back_populates="application"
    )
    screenings: Mapped[list["Screening"]] = relationship(
        back_populates="application"
    )
    email_logs: Mapped[list["EmailLog"]] = relationship(back_populates="application")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="application")
