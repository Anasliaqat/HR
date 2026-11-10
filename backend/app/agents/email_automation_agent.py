"""Apply configurable CV-score workflow rules and request the matching email."""

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
    "agent_review",
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
    """Route weak, irrelevant, or unmatched resumes to the separate HR queue."""
    reject_below = settings.email_automation_reject_below_score
    review_through = settings.email_automation_review_through_score
    interview_from = settings.email_automation_interview_from_score
    interview_through = settings.email_automation_interview_through_score
    if not (
        0 <= reject_below <= review_through < interview_from <= interview_through <= 100
    ):
        raise ValueError("Email automation score thresholds are not ordered correctly.")
    if has_relevant_evidence is False:
        return "agent_review"
    if required_skills and matched_skills is not None and not matched_skills:
        return "agent_review"
    if score < reject_below:
        return "agent_review"
    if score <= review_through:
        return "hr_review"
    if score < interview_from:
        return "hr_decision"
    if score <= interview_through:
        return "interview_eligible"
    if settings.email_automation_above_range_action == "interview_eligible":
        return "interview_eligible"
    return "hr_review"


def apply_resume_score_outcome(
    db: Session,
    resume: ResumeEvaluation,
) -> None:
    """Update an unreviewed application after its score is saved."""
    if resume.score is None or resume.application_id is None:
        return
    application = db.get(Application, resume.application_id)
    if application is None or application.status != "pending_review":
        return
    try:
        job = db.get(Job, resume.job_id or application.job_id)
        if job is None:
            logger.warning(
                "Could not apply email automation to %s: related job is missing.",
                application.id,
            )
            return
        evaluation_details = resume.evaluation_details or {}
        matched_skills = evaluation_details.get("matched_skills")
        if not isinstance(matched_skills, list):
            matched_skills = None
        evidence_keys = (
            "evidence",
            "candidate_strengths",
            "relevant_experience",
            "relevant_projects",
        )
        has_evidence_data = any(key in evaluation_details for key in evidence_keys)
        has_relevant_evidence = (
            any(
                isinstance(evaluation_details.get(key), list)
                and evaluation_details[key]
                for key in evidence_keys
            )
            if has_evidence_data
            else None
        )
        action = classify_score(
            resume.score,
            matched_skills=matched_skills,
            required_skills=job.required_skills,
            has_relevant_evidence=has_relevant_evidence,
        )
    except ValueError:
        logger.exception("Email automation score thresholds are invalid.")
        return

    if action == "agent_review":
        evaluation_details = resume.evaluation_details or {}
        matched_skills = evaluation_details.get("matched_skills", [])
        evidence = evaluation_details.get("evidence", [])
        candidate_strengths = evaluation_details.get("candidate_strengths", [])
        relevant_experience = evaluation_details.get("relevant_experience", [])
        relevant_projects = evaluation_details.get("relevant_projects", [])
        reasons: list[str] = []
        if resume.score < settings.email_automation_reject_below_score:
            reasons.append(
                f"CV score {resume.score}% is below "
                f"{settings.email_automation_reject_below_score}%."
            )
        if (
            job.required_skills
            and isinstance(matched_skills, list)
            and not matched_skills
        ):
            reasons.append("No required job skills were matched in the CV.")
        has_evidence_data = any(
            key in evaluation_details
            for key in (
                "evidence",
                "candidate_strengths",
                "relevant_experience",
                "relevant_projects",
            )
        )
        if has_evidence_data and not any(
            isinstance(items, list) and items
            for items in (
                evidence,
                candidate_strengths,
                relevant_experience,
                relevant_projects,
            )
        ):
            reasons.append("The evaluation found no relevant CV evidence for this job.")
        application.status = "over_agent_review"
        application.agent_review_reason = " ".join(reasons)
        db.commit()
    elif action == "interview_eligible":
        application.status = "interview_eligible"
        db.commit()
        candidate = db.get(Candidate, application.candidate_id)
        if candidate and candidate.email_consent and candidate.phone:
            try:
                send_application_email(db, application, "screening_invitation")
            except EmailAutomationError:
                logger.exception("Could not prepare an eligible candidate's screening invitation.")
