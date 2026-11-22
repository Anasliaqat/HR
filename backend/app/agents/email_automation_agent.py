"""Classify CV scores for HR review; never make or email a hiring decision automatically."""

from typing import Literal

from app.config import settings

ScoreAction = Literal[
    "low_score_review",
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
    """Return an HR review priority, not an automatic hiring decision."""
    reject_below = settings.email_automation_reject_below_score
    review_through = settings.email_automation_review_through_score
    interview_from = settings.email_automation_interview_from_score
    interview_through = settings.email_automation_interview_through_score
    if not (
        0 <= reject_below <= review_through < interview_from <= interview_through <= 100
    ):
        raise ValueError("Email automation score thresholds are not ordered correctly.")

    # A low score or a skills mismatch only prioritizes HR review.
    # Missing evidence is not proof that a candidate is irrelevant.
    if score < reject_below:
        return "low_score_review"
    if has_relevant_evidence is False:
        return "low_score_review"
    if required_skills and matched_skills is not None and not matched_skills:
        return "low_score_review"
    if score <= review_through:
        return "hr_review"
    if score < interview_from:
        return "hr_decision"
    if score <= interview_through:
        return "interview_eligible"
    if settings.email_automation_above_range_action == "interview_eligible":
        return "interview_eligible"
    return "hr_review"
