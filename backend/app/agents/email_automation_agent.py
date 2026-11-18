"""Apply CV-score outcomes and trigger the corresponding recruiting email."""

import logging
from typing import Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume_evaluation import ResumeEvaluation
from app.services.email_automation_service import (
    EmailAutomationError,
    send_application_email,
)

logger = logging.getLogger(__name__)
ScoreAction = Literal[
    "auto_reject",
    "hr_review",
    "hr_decision",
    "interview_eligible",
]


def classify_score(
    score: int,
    *,
    matched_skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    has_relevant_evidence: bool | None = None,
) -> ScoreAction:
    """Automatically reject clear failures; keep borderline cases with HR."""
    reject_below = settings.email_automation_reject_below_score
    review_through = settings.email_automation_review_through_score
    interview_from = settings.email_automation_interview_from_score
    interview_through = settings.email_automation_interview_through_score
    if not (
        0 <= reject_below <= review_through < interview_from <= interview_through <= 100
    ):
        raise ValueError("Email automation score thresholds are not ordered correctly.")

    # Explicitly empty relevance evidence or no required-skill matches is a
    # clear mismatch. Missing evidence is not treated as proof of irrelevance.
    if has_relevant_evidence is False:
        return "auto_reject"
    if required_skills and matched_skills is not None and not matched_skills:
        return "auto_reject"
    if score < reject_below:
        return "auto_reject"
    if score <= review_through:
        return "hr_review"
    if score < interview_from:
        return "hr_decision"
    if score <= interview_through:
        return "interview_eligible"
    if settings.email_automation_above_range_action == "interview_eligible":
        return "interview_eligible"
    return "hr_review"


def apply_resume_score_outcome(db: Session, resume: ResumeEvaluation) -> None:
    """Apply a score once, then send the matching email where consent permits."""
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
    has_evidence_data = any(key in details for key in evidence_keys)
    has_relevant_evidence = (
        any(isinstance(details.get(key), list) and details[key] for key in evidence_keys)
        if has_evidence_data
        else None
    )

    try:
        action = classify_score(
            resume.score,
            matched_skills=matched_skills,
            required_skills=job.required_skills,
            has_relevant_evidence=has_relevant_evidence,
        )
    except ValueError:
        logger.exception("Email automation score thresholds are invalid.")
        return

    if action == "auto_reject":
        reasons: list[str] = []
        if resume.score < settings.email_automation_reject_below_score:
            reasons.append(
                f"CV score {resume.score}% is below "
                f"{settings.email_automation_reject_below_score}%."
            )
        if job.required_skills and matched_skills is not None and not matched_skills:
            reasons.append("No required job skills were matched in the CV.")
        if has_evidence_data and has_relevant_evidence is False:
            reasons.append("The evaluation found no relevant CV evidence for this job.")

        application.status = "rejected_by_agent"
        application.agent_review_reason = " ".join(reasons) or (
            "The CV did not meet the configured screening criteria."
        )
        db.commit()
        candidate = db.get(Candidate, application.candidate_id)
        if candidate is not None:
            try:
                send_application_email(db, application, "rejection")
            except EmailAutomationError:
                logger.exception(
                    "Could not send the automated rejection email for application %s.",
                    application.id,
                )
    elif action == "interview_eligible":
        application.status = "interview_eligible"
        db.commit()
        candidate = db.get(Candidate, application.candidate_id)
        if candidate and candidate.email_consent and candidate.phone:
            try:
                send_application_email(db, application, "screening_invitation")
            except EmailAutomationError:
                logger.exception(
                    "Could not prepare an eligible candidate's screening invitation."
                )
