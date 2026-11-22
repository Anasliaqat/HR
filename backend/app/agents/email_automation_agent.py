"""Route scored CV applications into automatic low-score rejection or HR review."""

import logging
from typing import Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.resume_evaluation import ResumeEvaluation
from app.services.email_automation_service import (
    EmailAutomationError,
    send_application_email,
)

logger = logging.getLogger(__name__)
ScoreAction = Literal["automatic_rejection", "hr_review"]


def classify_score(
    score: int,
    *,
    matched_skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    has_relevant_evidence: bool | None = None,
) -> ScoreAction:
    """Use the agreed score threshold: 50 and below reject; above 50 goes to HR."""
    if not 0 <= score <= 100:
        raise ValueError("CV score must be between 0 and 100.")
    threshold = settings.email_automation_reject_below_score
    if not 0 <= threshold <= 100:
        raise ValueError("EMAIL_AUTOMATION_REJECT_BELOW_SCORE must be between 0 and 100.")
    return "automatic_rejection" if score <= threshold else "hr_review"


def apply_resume_score_outcome(db: Session, resume: ResumeEvaluation) -> None:
    """After scoring, automatically reject <=50 or queue >50 for HR decision."""
    if resume.score is None or resume.application_id is None:
        return
    application = db.get(Application, resume.application_id)
    if application is None or application.status != "pending_review":
        return

    try:
        action = classify_score(resume.score)
    except ValueError:
        logger.exception("Invalid score threshold; application left pending HR review.")
        return

    if action == "hr_review":
        # HR decision page reads pending_review applications with a score > 50.
        return

    application.status = "rejected"
    application.agent_review_reason = (
        f"CV score {resume.score}% is at or below the configured "
        f"{settings.email_automation_reject_below_score}% rejection threshold."
    )
    db.commit()
    try:
        # send_application_email records a pending consent-gated email or a
        # failed SMTP attempt; both states are visible and retryable in history.
        email = send_application_email(db, application, "rejection")
        if email.status != "sent":
            logger.warning(
                "Automatic rejection email for application %s has status %s: %s",
                application.id,
                email.status,
                email.error_message,
            )
    except EmailAutomationError:
        logger.exception("Could not start automatic rejection email for %s", application.id)
