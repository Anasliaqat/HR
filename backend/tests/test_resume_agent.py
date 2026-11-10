from app.agents import resume_agent
from app.services.resume_parser import ResumeProfile


def test_skill_synonyms_match_equivalent_resume_wording(monkeypatch) -> None:
    assert resume_agent._skill_evidence_matches("Python", ["Python 3"])
    assert resume_agent._skill_evidence_matches("TensorFlow", ["TensorFlow 2.x"])
    assert resume_agent._skill_evidence_matches("Generative AI", ["GenAI"])
    assert resume_agent._skill_evidence_matches(
        "RAG (Retrieval-Augmented Generation)",
        ["Built a retrieval augmented generation assistant."],
    )
    assert resume_agent._skill_evidence_matches("AI agents", ["Agentic AI workflows"])
    assert not resume_agent._skill_evidence_matches("Python", ["PyPI package publishing"])
    assert resume_agent._skill_match_reason(
        "RAG (Retrieval-Augmented Generation)",
        ResumeProfile(skills=["Retrieval augmented generation"]),
    )
    assert resume_agent._skill_evidence_matches(
        "Generative AI",
        [" GENERATIVE!!!   AI "],
    )
    monkeypatch.setattr(resume_agent, "semantic_similarity", lambda _skill, _item: 0.84)
    reason = resume_agent._skill_match_reason(
        "Retrieval-Augmented Generation",
        ResumeProfile(projects=["Implemented a context-aware document search assistant."]),
    )
    assert reason is not None
    assert reason.startswith("Semantic match (0.84) to projects:")


def test_education_abbreviations_match_full_degree_name() -> None:
    assert resume_agent._education_requirement_matches(
        ["Bachelor of Science in Information Technology"],
        "Bs It",
    )
    assert resume_agent._education_requirement_matches(
        ["B.S. in Information Technology"],
        "Bs It",
    )
    assert not resume_agent._education_requirement_matches(
        ["Bachelor of Arts in Accounting"],
        "Bs It",
    )


def test_zero_year_experience_requirement_does_not_award_experience_points(
    monkeypatch,
) -> None:
    monkeypatch.setattr(resume_agent, "semantic_similarity", lambda _left, _right: 0.0)
    result = resume_agent.score_resume(
        ResumeProfile(skills=["Python", "GenAI"]),
        job_title="Junior AI/ML Developer",
        job_description="Entry-level developer working with generative AI.",
        required_skills=["Python", "Generative AI"],
        required_experience_years=0,
    )

    assert result.matched_skills == ["Python", "Generative AI"]
    assert result.rubric_scores["required_skills"] == 40
    assert result.rubric_scores["relevant_experience"] == 0
    assert result.excluded_rubric_categories == ["relevant_experience"]
    assert result.score == 53
    assert "required skills 40/40 (2 of 2 matched)" in result.explanation
    assert "relevant experience not weighted (0 years required)" in result.explanation
    assert "normalized across 75 applicable rubric points" in result.explanation
    assert not any("At least 0 years" in item for item in result.missing_requirements)


def test_equivalent_required_skill_labels_are_not_counted_twice() -> None:
    skills = resume_agent._job_skills(
        ["RAG", "Retrieval-Augmented Generation", "Generative AI"],
        "Build retrieval augmented generation systems.",
    )

    assert skills == ["RAG", "Generative AI"]
