import pytest

from app.agents.email_automation_agent import classify_score
from app.config import settings


def test_low_score_with_evidence_is_automatically_rejected(monkeypatch):
    monkeypatch.setattr(settings, "email_automation_reject_below_score", 50)
    assert classify_score(
        50,
        matched_skills=["Python"],
        required_skills=["Python"],
        has_relevant_evidence=True,
    ) == "automatic_rejection"


@pytest.mark.parametrize("score", [0, 20, 49, 50])
def test_low_score_without_reliable_evidence_goes_to_hr(score):
    assert classify_score(
        score,
        matched_skills=[],
        required_skills=["Python"],
        has_relevant_evidence=False,
    ) == "hr_review"


def test_missing_evidence_is_not_assumed_to_be_irrelevant():
    assert classify_score(
        35,
        matched_skills=None,
        required_skills=["Python"],
        has_relevant_evidence=None,
    ) == "automatic_rejection"


def test_score_above_rejection_threshold_goes_to_hr_review():
    assert classify_score(
        51,
        matched_skills=["Python"],
        required_skills=["Python"],
        has_relevant_evidence=True,
    ) == "hr_review"


@pytest.mark.parametrize("score", [-1, 101])
def test_invalid_scores_are_rejected_as_input(score):
    with pytest.raises(ValueError):
        classify_score(score)
