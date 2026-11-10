"""Advisory, evidence-based resume scoring for HR review."""

import re
from functools import lru_cache

from pydantic import BaseModel, Field

from app.services.resume_parser import ResumeProfile

SCORING_WEIGHTS = {
    "required_skills": 40,
    "relevant_experience": 25,
    "projects": 20,
    "education_and_certifications": 10,
    "other_relevant_evidence": 5,
}
_SKILL_LEXICON = (
    "Python", "Java", "JavaScript", "TypeScript", "SQL", "PostgreSQL", "MySQL",
    "C#", ".NET", "C++", "Go", "Rust", "React", "Angular", "Vue", "Node.js",
    "FastAPI", "Django", "Flask", "Spring", "AWS", "Azure", "GCP", "Docker",
    "Kubernetes", "Terraform", "Linux", "Git", "REST", "GraphQL", "API",
    "machine learning", "deep learning", "data analysis", "data engineering",
    "TensorFlow", "PyTorch", "pandas", "Spark", "Power BI", "Tableau",
    "Agile", "project management", "communication",
)
_SKILL_SYNONYMS = {
    "python": ("python 3", "python3", "py3"),
    "tensorflow": ("tensorflow 2", "tensorflow 2.x", "tf"),
    "numpy": ("numerical python",),
    "pandas": ("python pandas",),
    "generative ai": (
        "gen ai",
        "genai",
        "generative artificial intelligence",
        "large language model",
        "large language models",
        "llm",
        "llms",
    ),
    "rag retrieval augmented generation": (
        "rag",
        "retrieval augmented generation",
        "retrieval-augmented generation",
    ),
    "ai agents": (
        "ai agent",
        "agentic ai",
        "agentic system",
        "agentic systems",
        "autonomous ai agent",
        "autonomous ai agents",
        "autonomous agent",
        "autonomous agents",
    ),
    "git github": ("git", "github", "version control", "source control"),
    "github copilot": (
        "copilot for github",
        "github ai coding assistant",
        "github copilot",
    ),
}


class ResumeEvaluationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    review_status: str = "pending_hr_review"
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    skill_match_reasons: dict[str, str] = Field(default_factory=dict)
    excluded_rubric_categories: list[str] = Field(default_factory=list)
    relevant_experience: list[str] = Field(default_factory=list)
    relevant_projects: list[str] = Field(default_factory=list)
    education_and_certifications: list[str] = Field(default_factory=list)
    candidate_strengths: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rubric_scores: dict[str, float] = Field(default_factory=dict)
    explanation: str


@lru_cache(maxsize=1)
def _embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Sentence Transformers is required for resume scoring; install backend requirements."
        ) from exc
    try:
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as exc:
        raise RuntimeError(
            "Unable to load the all-MiniLM-L6-v2 scoring model."
        ) from exc


@lru_cache(maxsize=512)
def _embedding(text: str) -> tuple[float, ...]:
    vector = _embedding_model().encode(text, normalize_embeddings=True)
    return tuple(float(value) for value in vector)


def semantic_similarity(left: str, right: str) -> float:
    """Return cosine similarity using normalized Sentence Transformer embeddings."""
    first = _embedding(left)
    second = _embedding(right)
    if len(first) != len(second):
        raise RuntimeError("The semantic model returned incompatible embeddings.")
    return sum(a * b for a, b in zip(first, second, strict=True))


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.casefold()).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    return bool(
        normalized_phrase
        and re.search(
            rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
            normalized_text,
        )
    )


def _skill_match_reason(skill: str, profile: ResumeProfile) -> str | None:
    sections = (
        ("CV skills", profile.skills),
        ("professional summary", profile.summary),
        ("projects", profile.projects),
        ("experience or training", profile.experience + profile.certifications),
    )
    forms = _skill_forms(skill)
    for section, evidence_items in sections:
        for item in evidence_items:
            for form in forms:
                if _contains_phrase(item, form):
                    return f'Found "{form}" in {section}: {item}'

    semantic_matches = [
        (semantic_similarity(skill, item), section, item)
        for section, evidence_items in sections
        for item in evidence_items
        if len(_normalize(skill).split()) > 1
    ]
    if semantic_matches:
        similarity, section, item = max(semantic_matches)
        if similarity >= 0.82:
            return (
                f"Semantic match ({similarity:.2f}) to {section}: {item}"
            )
    return None


def _skill_forms(skill: str) -> tuple[str, ...]:
    normalized_skill = _normalize(skill)
    for canonical, aliases in _SKILL_SYNONYMS.items():
        forms = tuple(dict.fromkeys((canonical, *aliases)))
        if normalized_skill in {_normalize(form) for form in forms}:
            return forms
    if "/" in skill:
        return tuple(part.strip() for part in skill.split("/") if part.strip())
    return (skill,)


def _skill_group(skill: str) -> str:
    normalized_skill = _normalize(skill)
    for canonical, aliases in _SKILL_SYNONYMS.items():
        if normalized_skill in {_normalize(form) for form in (canonical, *aliases)}:
            return canonical
    return normalized_skill


def _skill_evidence_matches(skill: str, evidence: list[str]) -> bool:
    forms = _skill_forms(skill)
    if any(_contains_phrase(item, form) for item in evidence for form in forms):
        return True
    return any(
        semantic_similarity(skill, item) >= 0.82
        for item in evidence
        if len(_normalize(skill).split()) > 1
    )


def _job_skills(
    required_skills: list[str],
    description: str | list[str],
) -> list[str]:
    skills: list[str] = []
    seen_groups: set[str] = set()
    for skill in required_skills:
        cleaned = skill.strip()
        group = _skill_group(cleaned)
        if cleaned and group not in seen_groups:
            skills.append(cleaned)
            seen_groups.add(group)
    if skills:
        return skills
    normalized_description = _normalize(
        description if isinstance(description, str) else " ".join(description)
    )
    return [
        skill
        for skill in _SKILL_LEXICON
        if re.search(rf"(?<!\w){re.escape(_normalize(skill))}(?!\w)", normalized_description)
    ]


def _best_similarity(phrase: str, evidence: list[str]) -> float:
    if not phrase or not evidence:
        return 0.0
    if any(_contains_phrase(item, phrase) for item in evidence):
        return 1.0
    return max(semantic_similarity(phrase, item) for item in evidence)


def _similarity_to_description(
    items: list[str],
    description: str | list[str],
) -> float:
    if not items:
        return 0.0
    targets = [description] if isinstance(description, str) else description
    if not targets:
        return 0.0
    strongest = sorted(
        (
            max(semantic_similarity(item, target) for target in targets)
            for item in items
        ),
        reverse=True,
    )[:3]
    normalized = [
        max(0.0, min((score - 0.3) / 0.4, 1.0))
        for score in strongest
    ]
    return sum(normalized) / len(normalized)


def _relevant_lines(
    items: list[str],
    description: str | list[str],
    limit: int = 5,
) -> list[str]:
    if not items:
        return []
    targets = [description] if isinstance(description, str) else description
    if not targets:
        return []
    ranked = sorted(
        (
            (
                item,
                max(semantic_similarity(item, target) for target in targets),
            )
            for item in items
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [item for item, similarity in ranked if similarity >= 0.3][:limit]


def _normalize_education(value: str) -> set[str]:
    normalized = _normalize(value).replace(".", " ")
    substitutions = (
        (r"\bb\s*\.?\s*s\s*\.?\b", " bachelor "),
        (r"\bbsc\b", " bachelor "),
        (r"\bbachelors?\b", " bachelor "),
        (r"\bmasters?\b", " master "),
        (r"\bm\s*\.?\s*s\s*\.?\b", " master "),
        (r"\bph\s*\.?\s*d\s*\.?\b", " doctorate "),
        (r"\bdoctorate\b", " doctorate "),
        (r"\bit\b", " information technology "),
        (r"\binformation tech\b", " information technology "),
    )
    for pattern, replacement in substitutions:
        normalized = re.sub(pattern, replacement, normalized)
    ignored = {"of", "in", "and", "degree", "the"}
    return {token for token in normalized.split() if token not in ignored}


def _education_requirement_matches(items: list[str], requirement: str) -> bool:
    required_terms = _normalize_education(requirement)
    if not required_terms:
        return False
    return any(required_terms <= _normalize_education(item) for item in items)


def _education_similarity(items: list[str], requirement: str | None) -> float:
    if not requirement or not items:
        return 0.0
    if _education_requirement_matches(items, requirement):
        return 1.0
    similarity = max(semantic_similarity(item, requirement) for item in items)
    return max(0.0, min((similarity - 0.4) / 0.45, 1.0))


def _years_of_experience(items: list[str]) -> float | None:
    explicit = [
        float(value)
        for line in items
        for value in re.findall(
            r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", line, re.I
        )
    ]
    return max(explicit) if explicit else None


def _deterministic_explanation(result: ResumeEvaluationResult) -> str:
    missing = (
        f" Missing required skills: {', '.join(result.missing_required_skills)}."
        if result.missing_required_skills
        else " All identified required skills have supporting evidence."
    )
    evidence = (
        f" Evidence includes {len(result.evidence)} CV item(s) relevant to the role."
        if result.evidence
        else " The CV contained limited role-related evidence."
    )
    strengths = (
        f" Candidate strengths include: {'; '.join(result.candidate_strengths[:3])}."
        if result.candidate_strengths
        else ""
    )
    rubric = result.rubric_scores
    excluded_categories = set(result.excluded_rubric_categories)
    experience_exclusion = (
        " Employment experience is excluded from the score because the selected "
        "role is entry-level and requires 0 years."
        if "relevant_experience" in excluded_categories
        else ""
    )
    applicable_points = sum(
        weight
        for category, weight in SCORING_WEIGHTS.items()
        if category not in excluded_categories
    )
    experience_breakdown = (
        "relevant experience not weighted (0 years required); "
        if "relevant_experience" in excluded_categories
        else (
            f"relevant experience "
            f"{rubric.get('relevant_experience', 0):g}/25; "
        )
    )
    score_breakdown = (
        " Score breakdown: "
        f"required skills {rubric.get('required_skills', 0):g}/40 "
        f"({len(result.matched_skills)} of "
        f"{len(result.matched_skills) + len(result.missing_required_skills)} matched); "
        f"{experience_breakdown}"
        f"projects {rubric.get('projects', 0):g}/20; "
        f"education and certifications "
        f"{rubric.get('education_and_certifications', 0):g}/10; "
        f"other relevant evidence "
        f"{rubric.get('other_relevant_evidence', 0):g}/5."
        f"{experience_exclusion} "
        f"The final score is normalized across {applicable_points} applicable "
        "rubric points."
    )
    return (
        f"Overall match: {result.score}/100 based on the stated rubric; "
        "this is not a probability of being hired."
        f"{score_breakdown}{strengths}{missing}{evidence} "
        "HR review and approval are required."
    )


def score_resume(
    profile: ResumeProfile,
    *,
    job_title: str,
    job_description: str,
    required_skills: list[str],
    required_experience_years: int | None,
    required_education: str | None = None,
) -> ResumeEvaluationResult:
    """Score only job-related evidence; generated scores never determine hiring decisions."""
    description = [job_title, job_description, *required_skills]
    job_skills = _job_skills(required_skills, description)
    skill_evidence = (
        profile.skills + profile.summary + profile.experience + profile.projects
    )
    matched: list[str] = []
    missing: list[str] = []
    skill_match_reasons: dict[str, str] = {}
    skill_scores: list[float] = []
    for skill in job_skills:
        reason = _skill_match_reason(skill, profile)
        is_matched = reason is not None
        skill_scores.append(1.0 if is_matched else 0.0)
        (matched if is_matched else missing).append(skill)
        skill_match_reasons[skill] = reason or "No supporting CV evidence found."

    skill_score = sum(skill_scores) / len(skill_scores) if skill_scores else (
        _similarity_to_description(profile.skills, description)
    )
    work_score = _similarity_to_description(profile.experience, description)
    years = _years_of_experience(profile.experience)
    if required_experience_years is not None and required_experience_years > 0:
        years_score = (
            min(years / required_experience_years, 1.0)
            if years is not None and required_experience_years > 0
            else 0.0
        )
        work_score = 0.65 * work_score + 0.35 * years_score
    project_score = _similarity_to_description(profile.projects, description)
    education_items = profile.education + profile.certifications
    education_score = _education_similarity(education_items, required_education)
    other_items = profile.certifications + profile.summary
    other_score = _similarity_to_description(other_items, description)

    categories = {
        "required_skills": skill_score,
        "relevant_experience": work_score,
        "projects": project_score,
        "education_and_certifications": education_score,
        "other_relevant_evidence": other_score,
    }
    rubric_scores = {
        category: round(weight * max(0.0, min(value, 1.0)), 2)
        for (category, weight), value in zip(
            SCORING_WEIGHTS.items(), categories.values(), strict=True
        )
    }
    excluded_categories: list[str] = []
    if required_experience_years == 0:
        excluded_categories.append("relevant_experience")
    applicable_points = sum(
        weight
        for category, weight in SCORING_WEIGHTS.items()
        if category not in excluded_categories
    )
    applicable_score = sum(
        points
        for category, points in rubric_scores.items()
        if category not in excluded_categories
    )
    score = round(applicable_score / applicable_points * 100)
    relevant_experience = _relevant_lines(profile.experience, description)
    relevant_projects = _relevant_lines(profile.projects, description)
    relevant_education = _relevant_lines(education_items, description)
    relevant_skills = _relevant_lines(profile.skills, description)
    missing_requirements = list(missing)
    if required_experience_years is not None and required_experience_years > 0 and (
        years is None or years < required_experience_years
    ):
        missing_requirements.append(
            f"At least {required_experience_years} years of relevant experience"
        )
    if required_education and not (
        _education_requirement_matches(education_items, required_education)
        or education_score >= 0.25
    ):
        missing_requirements.append(f"Education requirement: {required_education}")
    matched_skill_evidence = [
        item
        for item in skill_evidence
        if any(
            any(_contains_phrase(item, form) for form in _skill_forms(skill))
            for skill in matched
        )
    ]
    candidate_strengths = list(
        dict.fromkeys(
            [f"Demonstrated {skill}" for skill in matched]
            + [f"Relevant experience: {item}" for item in relevant_experience]
            + [f"Relevant project: {item}" for item in relevant_projects]
        )
    )[:5]
    evidence = list(
        dict.fromkeys(
            matched_skill_evidence
            + relevant_skills
            + relevant_experience
            + relevant_projects
            + relevant_education
        )
    )
    result = ResumeEvaluationResult(
        score=score,
        matched_skills=matched,
        missing_required_skills=missing,
        skill_match_reasons=skill_match_reasons,
        excluded_rubric_categories=excluded_categories,
        relevant_experience=relevant_experience,
        relevant_projects=relevant_projects,
        education_and_certifications=education_items,
        candidate_strengths=candidate_strengths,
        missing_requirements=missing_requirements,
        evidence=evidence[:10],
        rubric_scores=rubric_scores,
        explanation="",
    )
    result.explanation = _deterministic_explanation(result)
    return result
