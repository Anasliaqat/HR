"""Route scored CV applications into rejection, HR review, or approval.

Policy (thresholds come from settings):
* score at or below ``EMAIL_AUTOMATION_REJECT_BELOW_SCORE`` (default 50):
  automatic rejection email. This includes CVs that are irrelevant to the job.
* score at or above ``EMAIL_AUTOMATION_AUTO_APPROVE_FROM_SCORE`` (default 90):
  automatic approval email.
* everything in between: stays ``pending_review`` and appears in the HR portal
  for an Accept or Reject decision, which sends the matching email.

Safety rule: when the parser could not read ANY section of the CV the score says
nothing about the candidate, so the application always goes to HR instead.
"""

import logging
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.job import Job
from app.models.resume_evaluation import ResumeEvaluation
from app.services.email_automation_service import (
    EmailAutomationError,
    send_application_email,
)

logger = logging.getLogger(__name__)
ScoreAction = Literal["automatic_rejection", "automatic_approval", "hr_review"]
EVIDENCE_KEYS = (
    "evidence",
    "candidate_strengths",
    "relevant_experience",
    "relevant_projects",
)


def evaluation_signals(details: dict[str, Any] | None) -> dict[str, Any]:
    """Read the facts the policy needs from a stored resume evaluation."""
    details = details or {}
    matched = details.get("matched_skills")
    evidence_was_evaluated = any(key in details for key in EVIDENCE_KEYS)
    return {
        "matched_skills": matched if isinstance(matched, list) else None,
        "has_relevant_evidence": (
            any(
                isinstance(details.get(key), list) and bool(details[key])
                for key in EVIDENCE_KEYS
            )
            if evidence_was_evaluated
            else None
        ),
        "profile_unparsed": details.get("profile_unparsed") is True,
    }


def classify_score(
    score: int,
    *,
    matched_skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    has_relevant_evidence: bool | None = None,
    profile_unparsed: bool = False,
) -> ScoreAction:
    if not 0 <= score <= 100:
        raise ValueError("CV score must be between 0 and 100.")
    reject_at = settings.email_automation_reject_below_score
    approve_from = settings.email_automation_auto_approve_from_score
    if not 0 <= reject_at < approve_from <= 100:
        raise ValueError(
            "EMAIL_AUTOMATION_REJECT_BELOW_SCORE must be lower than "
            "EMAIL_AUTOMATION_AUTO_APPROVE_FROM_SCORE, both within 0-100."
        )

    # Nothing could be read from the CV: a human must look at it.
    if profile_unparsed:
        return "hr_review"
    if score <= reject_at:
        return "automatic_rejection"
    if score >= approve_from:
        # Never approve automatically on a high score that lacks supporting evidence.
        if has_relevant_evidence is False:
            return "hr_review"
        if required_skills and matched_skills is not None and not matched_skills:
            return "hr_review"
        return "automatic_approval"
    return "hr_review"


def _send(db: Session, application: Application, email_type: str) -> None:
    """Delivery is consent-gated, logged and retryable; it never breaks scoring."""
    try:
        email = send_application_email(db, application, email_type)
        if email.status != "sent":
            logger.warning(
                "Automatic %s email for application %s is %s: %s",
                email_type,
                application.id,
                email.status,
                email.error_message,
            )
    except EmailAutomationError:
        logger.exception(
            "Could not start the automatic %s email for application %s.",
            email_type,
            application.id,
        )


def apply_resume_score_outcome(db: Session, resume: ResumeEvaluation) -> None:
    """Apply the email policy once a completed resume score is saved."""
    if resume.score is None or resume.application_id is None:
        return
    application = db.get(Application, resume.application_id)
    if application is None or application.status != "pending_review":
        return

    job = db.get(Job, resume.job_id or application.job_id)
    if job is None:
        logger.warning(
            "Could not apply email automation to %s: related job is missing.",
            application.id,
        )
        return

    signals = evaluation_signals(resume.evaluation_details)
    try:
        action = classify_score(
            resume.score, required_skills=job.required_skills or [], **signals
        )
    except ValueError:
        logger.exception(
            "Invalid email automation policy; application %s remains pending HR review.",
            application.id,
        )
        return

    if action == "hr_review":
        # No email is sent. HR sees it in the portal and decides.
        if signals["profile_unparsed"]:
            application.agent_review_reason = (
                "No CV sections could be recognized, so the score is unreliable. "
                "HR should read the CV and decide."
            )
            db.commit()
        return

    if action == "automatic_rejection":
        reasons = [
            f"CV score {resume.score}% is at or below the "
            f"{settings.email_automation_reject_below_score}% rejection threshold."
        ]
        if job.required_skills and signals["matched_skills"] == []:
            reasons.append("No required job skills were matched in the CV.")
        if signals["has_relevant_evidence"] is False:
            reasons.append("The CV showed no relevant evidence for this job.")
        application.status = "rejected"
        application.agent_review_reason = " ".join(reasons)
        db.commit()
        _send(db, application, "rejection")
        return

    # automatic_approval: score-based, so it is NOT recorded as an HR approval.
    application.status = "interview_eligible"
    application.agent_review_reason = (
        f"CV score {resume.score}% is at or above the "
        f"{settings.email_automation_auto_approve_from_score}% automatic-approval "
        "threshold."
    )
    db.commit()
    _send(db, application, "selection")
