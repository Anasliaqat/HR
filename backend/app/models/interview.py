"""Interview appointment model."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.job import Job
    from app.models.user import User


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    interviewer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    interviewer_email: Mapped[str] = mapped_column(String(320))
    interview_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    meeting_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default="scheduled")
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notifications_status: Mapped[str] = mapped_column(
        String(40), default="not_sent"
    )
    notification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="interviews")
    job: Mapped["Job"] = relationship()
    interviewer: Mapped["User | None"] = relationship(back_populates="interviews")
