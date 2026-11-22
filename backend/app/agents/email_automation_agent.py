"""Route scored CV applications safely into rejection or HR review.

The scoring model provides evidence; this agent applies the configured email
policy. Missing parser evidence must never be treated as proof that a candidate
is unsuitable.
"""

import logging
from typing import Literal

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
ScoreAction = Literal["automatic_rejection", "hr_review"]


def classify_score(
    score: int,
    *,
    matched_skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    has_relevant_evidence: bool | None = None,
) -> ScoreAction:
    """Reject only low scores supported by usable CV evidence."""
    if not 0 <= score <= 100:
        raise ValueError("CV score must be between 0 and 100.")
    threshold = settings.email_automation_reject_below_score
    if not 0 <= threshold <= 100:
        raise ValueError(
            "EMAIL_AUTOMATION_REJECT_BELOW_SCORE must be between 0 and 100."
        )

    # A parser gap or an explicit lack of extracted evidence is not a fair
    # reason to reject. Send these cases to a human instead.
    if has_relevant_evidence is False:
        return "hr_review"
    if required_skills and matched_skills is not None and not matched_skills:
        return "hr_review"
    # Unknown/empty evaluation evidence must never trigger automatic rejection.
    # A non-empty matched-skill list is the minimum positive evidence when the
    # evaluator does not provide the richer evidence fields.
    if has_relevant_evidence is None and not matched_skills:
        return "hr_review"
    if matched_skills is None and has_relevant_evidence is not True:
        return "hr_review"

    return "automatic_rejection" if score <= threshold else "hr_review"


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

    details = resume.evaluation_details or {}
    matched_skills = details.get("matched_skills")
    if not isinstance(matched_skills, list):
        matched_skills = None

    evidence_keys = (
        "evidence",
        "candidate_strengths",
        "relevant_experience",
        "relevant_projects",
    )
    evidence_was_evaluated = any(key in details for key in evidence_keys)
    has_relevant_evidence = (
        any(
            isinstance(details.get(key), list) and bool(details[key])
            for key in evidence_keys
        )
        if evidence_was_evaluated
        else None
    )

    try:
        action = classify_score(
            resume.score,
            matched_skills=matched_skills,
            required_skills=job.required_skills or [],
            has_relevant_evidence=has_relevant_evidence,
        )
    except ValueError:
        logger.exception(
            "Invalid email automation policy; application %s remains pending HR review.",
            application.id,
        )
        return

    if action == "hr_review":
        # No selection email is sent automatically. HR reviews every score
        # above the rejection threshold and all uncertain/parser-gap cases.
        if resume.score <= settings.email_automation_reject_below_score:
            reasons = []
            if has_relevant_evidence is False:
                reasons.append("The CV parser found no relevant evidence.")
            if job.required_skills and matched_skills == []:
                reasons.append("No required job skills were matched in the CV.")
            if reasons:
                application.agent_review_reason = " ".join(reasons)
                db.commit()
        return

    application.status = "rejected"
    application.agent_review_reason = (
        f"CV score {resume.score}% is at or below the configured "
        f"{settings.email_automation_reject_below_score}% rejection threshold; "
        "the evaluation contained usable CV evidence."
    )
    db.commit()

    try:
        # Delivery is consent-gated, logged, and retryable. A missing SMTP
        # configuration never crashes resume evaluation.
        email = send_application_email(db, application, "rejection")
        if email.status != "sent":
            logger.warning(
                "Automatic rejection email for application %s has status %s: %s",
                application.id,
                email.status,
                email.error_message,
            )
    except EmailAutomationError:
        logger.exception(
            "Could not start automatic rejection email for application %s.",
            application.id,
        )
