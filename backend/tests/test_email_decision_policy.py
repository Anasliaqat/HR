import pytest

from app.agents.email_automation_agent import classify_score, evaluation_signals
from app.config import settings


def test_low_score_with_evidence_is_automatically_rejected():
    assert classify_score(
        50, matched_skills=["Python"], required_skills=["Python"], has_relevant_evidence=True
    ) == "automatic_rejection"


@pytest.mark.parametrize("score", [0, 20, 49, 50])
def test_irrelevant_cv_with_a_low_score_is_rejected(score):
    """No matching skills and no evidence is exactly what an irrelevant CV looks like."""
    assert classify_score(
        score, matched_skills=[], required_skills=["Python"], has_relevant_evidence=False
    ) == "automatic_rejection"


@pytest.mark.parametrize("score", [0, 20, 49, 50])
def test_unreadable_cv_always_goes_to_hr(score):
    assert classify_score(
        score, matched_skills=[], required_skills=["Python"],
        has_relevant_evidence=False, profile_unparsed=True,
    ) == "hr_review"


def test_missing_evidence_data_with_a_low_score_is_rejected():
    assert classify_score(
        35, matched_skills=None, required_skills=["Python"], has_relevant_evidence=None
    ) == "automatic_rejection"


@pytest.mark.parametrize("score", [51, 70, 89])
def test_scores_between_the_thresholds_go_to_hr_review(score):
    assert classify_score(
        score, matched_skills=["Python"], required_skills=["Python"], has_relevant_evidence=True
    ) == "hr_review"


def test_score_at_the_approval_threshold_is_automatically_approved():
    assert classify_score(
        90, matched_skills=["Python"], required_skills=["Python"], has_relevant_evidence=True
    ) == "automatic_approval"


def test_thresholds_are_configurable(monkeypatch):
    monkeypatch.setattr(settings, "email_automation_reject_below_score", 40)
    monkeypatch.setattr(settings, "email_automation_auto_approve_from_score", 80)
    assert classify_score(45) == "hr_review"
    assert classify_score(80) == "automatic_approval"
    assert classify_score(40) == "automatic_rejection"


def test_misordered_thresholds_are_reported(monkeypatch):
    monkeypatch.setattr(settings, "email_automation_reject_below_score", 90)
    monkeypatch.setattr(settings, "email_automation_auto_approve_from_score", 50)
    with pytest.raises(ValueError):
        classify_score(70)


@pytest.mark.parametrize("score", [-1, 101])
def test_invalid_scores_are_rejected_as_input(score):
    with pytest.raises(ValueError):
        classify_score(score)


def test_evaluation_signals_read_stored_details():
    signals = evaluation_signals(
        {"matched_skills": [], "evidence": [], "profile_unparsed": True}
    )
    assert signals == {
        "matched_skills": [], "has_relevant_evidence": False, "profile_unparsed": True,
    }
    assert evaluation_signals(None)["has_relevant_evidence"] is None
