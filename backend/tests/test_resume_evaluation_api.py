from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from docx import Document

from app.agents.resume_agent import ResumeEvaluationResult
from app.api import resumes as resume_routes
from app.database import connection
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if connection._engine is not None:
        connection._engine.dispose()
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(
        connection.settings,
        "database_url",
        f"sqlite:///{tmp_path / 'resume-evaluation.db'}",
    )
    monkeypatch.setattr(resume_routes, "UPLOAD_DIRECTORY", tmp_path / "uploads")

    with TestClient(app) as test_client:
        yield test_client

    connection.get_engine().dispose()
    monkeypatch.setattr(connection, "_engine", None)


def _create_resume(client: TestClient, tmp_path: Path) -> tuple[str, str, str]:
    candidate_response = client.post(
        "/api/candidates",
        json={"full_name": "Taylor Candidate", "email": "taylor@example.com"},
    )
    assert candidate_response.status_code == 201
    candidate_id = candidate_response.json()["id"]

    job_response = client.post(
        "/api/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Build Python services and reliable APIs.",
            "required_skills": ["Python", "SQL"],
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    document = Document()
    document.add_paragraph("Skills")
    document.add_paragraph("Python, SQL")
    document.add_paragraph("Experience")
    document.add_paragraph("Built Python services for production teams.")
    resume_path = tmp_path / "candidate.docx"
    document.save(resume_path)

    upload_response = client.post(
        "/api/resumes/upload",
        data={"candidate_id": candidate_id, "job_id": job_id},
        files={
            "file": (
                "candidate.docx",
                resume_path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_response.status_code == 201
    return candidate_id, job_id, upload_response.json()["id"]


def test_upload_evaluate_and_load_saved_result(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, job_id, resume_id = _create_resume(client, tmp_path)
    assert (tmp_path / "uploads" / f"{resume_id}.docx").is_file()

    def score_resume(profile, **job_context):
        assert profile.skills == ["Python", "SQL"]
        assert job_context == {
            "job_title": "Backend Engineer",
            "job_description": "Build Python services and reliable APIs.",
            "required_skills": ["Python", "SQL"],
            "required_experience_years": None,
            "required_education": None,
        }
        return ResumeEvaluationResult(
            score=82,
            matched_skills=["Python", "SQL"],
            relevant_experience=profile.experience,
            explanation="Review the supplied role-related evidence.",
            rubric_scores={"required_skills": 40.0},
        )

    monkeypatch.setattr(resume_routes, "score_resume", score_resume)
    evaluation_response = client.post(
        f"/api/resumes/{resume_id}/evaluate",
        json={"job_id": job_id},
    )
    assert evaluation_response.status_code == 200
    evaluation = evaluation_response.json()
    assert evaluation["job_id"] == job_id
    assert evaluation["job_title"] == "Backend Engineer"
    assert evaluation["score"] == 82
    assert "Built Python services" in evaluation["extracted_text"]

    history_response = client.get("/api/resumes")
    assert history_response.status_code == 200
    saved_resume = history_response.json()[0]
    assert saved_resume["score"] == 82
    assert saved_resume["evaluation_details"]["job_id"] == job_id

    saved_result_response = client.get(f"/api/resumes/{resume_id}/score")
    assert saved_result_response.status_code == 200
    assert saved_result_response.json()["extracted_text"] == evaluation["extracted_text"]


def test_async_evaluation_reports_processing_and_persists_actual_agent_result(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, job_id, resume_id = _create_resume(client, tmp_path)

    def score_resume(profile, **_job_context):
        return ResumeEvaluationResult(
            score=82,
            matched_skills=["Python", "SQL"],
            missing_required_skills=["PostgreSQL"],
            relevant_experience=profile.experience,
            candidate_strengths=["Built Python services for production teams."],
            missing_requirements=["No PostgreSQL experience stated."],
            explanation="Review the supplied role-related evidence.",
            rubric_scores={
                "required_skills": 35.0,
                "relevant_experience": 20.0,
            },
        )

    monkeypatch.setattr(resume_routes, "score_resume", score_resume)
    start_response = client.post(
        f"/api/resumes/{resume_id}/evaluate/async",
        json={"job_id": job_id},
    )

    assert start_response.status_code == 202
    assert start_response.json()["evaluation_status"] == "processing"

    status_response = client.get(f"/api/resumes/{resume_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["evaluation_status"] == "completed"

    saved_result = client.get(f"/api/resumes/{resume_id}/score")
    assert saved_result.status_code == 200
    assert saved_result.json()["score"] == 82
    assert saved_result.json()["matched_skills"] == ["Python", "SQL"]
    assert saved_result.json()["missing_required_skills"] == ["PostgreSQL"]
    assert saved_result.json()["candidate_strengths"] == [
        "Built Python services for production teams."
    ]
    assert saved_result.json()["missing_requirements"] == [
        "No PostgreSQL experience stated."
    ]


def test_async_evaluation_persists_failed_status(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, job_id, resume_id = _create_resume(client, tmp_path)

    def fail_scoring(*_args, **_kwargs):
        raise RuntimeError("The scoring model is unavailable.")

    monkeypatch.setattr(resume_routes, "score_resume", fail_scoring)
    start_response = client.post(
        f"/api/resumes/{resume_id}/evaluate/async",
        json={"job_id": job_id},
    )

    assert start_response.status_code == 202
    assert start_response.json()["evaluation_status"] == "processing"
    status_response = client.get(f"/api/resumes/{resume_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["evaluation_status"] == "failed"
    assert status_response.json()["evaluation_details"]["error"] == (
        "The scoring model is unavailable."
    )


def test_delete_resume_removes_record_and_uploaded_file(
    client: TestClient,
    tmp_path: Path,
) -> None:
    candidate_id, _, resume_id = _create_resume(client, tmp_path)
    uploaded_file = tmp_path / "uploads" / f"{resume_id}.docx"
    assert uploaded_file.is_file()

    delete_response = client.delete(f"/api/resumes/{resume_id}")

    assert delete_response.status_code == 204
    assert not uploaded_file.exists()
    assert client.get(f"/api/resumes/{resume_id}/score").status_code == 404
    assert client.get("/api/candidates").status_code == 200
    assert any(
        candidate["id"] == candidate_id
        for candidate in client.get("/api/candidates").json()
    )


def test_force_evaluation_replaces_saved_score_with_new_agent_result(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, job_id, resume_id = _create_resume(client, tmp_path)

    def first_score(_profile, **_job_context):
        return ResumeEvaluationResult(
            score=20,
            explanation="Initial score.",
        )

    monkeypatch.setattr(resume_routes, "score_resume", first_score)
    initial = client.post(
        f"/api/resumes/{resume_id}/evaluate",
        json={"job_id": job_id},
    )
    assert initial.status_code == 200
    assert initial.json()["score"] == 20

    def updated_score(_profile, **_job_context):
        return ResumeEvaluationResult(
            score=92,
            matched_skills=["Python", "SQL"],
            skill_match_reasons={
                "Python": 'Found "Python" in CV skills: Python',
            },
            explanation="Updated score.",
        )

    monkeypatch.setattr(resume_routes, "score_resume", updated_score)
    start = client.post(
        f"/api/resumes/{resume_id}/evaluate/async",
        json={"job_id": job_id, "force": True},
    )

    assert start.status_code == 202
    assert start.json()["evaluation_status"] == "processing"
    status_response = client.get(f"/api/resumes/{resume_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["evaluation_status"] == "completed"
    result = client.get(f"/api/resumes/{resume_id}/score")
    assert result.status_code == 200
    assert result.json()["score"] == 92
    assert result.json()["skill_match_reasons"]["Python"] == (
        'Found "Python" in CV skills: Python'
    )
    assert (tmp_path / "uploads" / f"{resume_id}.docx").is_file()
