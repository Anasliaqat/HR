from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from app.agents.email_automation_agent import (
    apply_resume_score_outcome,
    classify_score,
)
from app.config import settings
from app.database.connection import Base, migrate_email_automation_columns
from app.database import connection
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.email_log import EmailLog
from app.models.job import Job
from app.models.interview import Interview
from app.models.resume_evaluation import ResumeEvaluation
from app.services import email_automation_service
from app.services import email_service
from app.services.email_automation_service import (
    build_email_preview,
    send_application_email,
)


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'email-automation.db'}")
    Base.metadata.create_all(engine)
    migrate_email_automation_columns(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


def create_application(
    db: Session,
    *,
    score: int,
    email_consent: bool = False,
    matched_skills: list[str] | None = None,
) -> tuple[Application, ResumeEvaluation]:
    candidate = Candidate(
        full_name="Taylor Candidate",
        email="taylor@example.com",
        email_consent=email_consent,
    )
    job = Job(
        title="Backend Engineer",
        description="Build dependable backend systems.",
        required_skills=["Python"],
    )
    db.add_all([candidate, job])
    db.flush()
    application = Application(
        candidate_id=candidate.id,
        job_id=job.id,
        status="pending_review",
    )
    db.add(application)
    db.flush()
    resume = ResumeEvaluation(
        candidate_id=candidate.id,
        application_id=application.id,
        job_id=job.id,
        file_name="candidate.pdf",
        file_path="candidate.pdf",
        score=score,
        evaluation_details={
            "matched_skills": ["Python"] if matched_skills is None else matched_skills
        },
        evaluation_status="completed",
    )
    db.add(resume)
    db.commit()
    return application, resume


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (49, "agent_review"),
        (50, "hr_review"),
        (60, "hr_review"),
        (61, "hr_decision"),
        (69, "hr_decision"),
        (70, "interview_eligible"),
        (90, "interview_eligible"),
        (91, "hr_review"),
    ],
)
def test_score_boundaries_follow_configured_conservative_defaults(
    score: int,
    expected: str,
) -> None:
    assert classify_score(score) == expected


def test_missing_match_evidence_does_not_count_as_no_skill_match() -> None:
    assert classify_score(
        60,
        matched_skills=None,
        required_skills=["Python"],
    ) == "hr_review"


def stub_delivery(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace real delivery and record each recipient that would be emailed."""
    sent_to: list[str] = []

    def fake_deliver(preview, idempotency_key):
        sent_to.append(preview.recipient_email)
        return f"message-{len(sent_to)}"

    monkeypatch.setattr(email_automation_service, "_deliver", fake_deliver)
    return sent_to


def test_low_score_is_rejected_and_candidate_is_emailed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    application, resume = create_application(
        db_session, score=42, email_consent=True
    )

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    email_log = db_session.scalar(select(EmailLog))
    assert application.status == "rejected"
    assert "42%" in application.agent_review_reason
    assert "below" in application.agent_review_reason
    assert email_log is not None
    assert email_log.email_type == "rejection"
    assert email_log.status == "sent"
    assert sent_to == ["taylor@example.com"]

    apply_resume_score_outcome(db_session, resume)
    assert len(db_session.scalars(select(EmailLog)).all()) == 1
    assert sent_to == ["taylor@example.com"]


def test_low_score_queues_for_hr_when_auto_reject_is_disabled(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "email_automation_auto_reject", False)
    application, resume = create_application(
        db_session, score=42, email_consent=True
    )

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    assert application.status == "over_agent_review"
    assert db_session.scalar(select(EmailLog)) is None


def test_auto_rejection_waits_for_consent_then_sends_once_recorded(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    application, resume = create_application(db_session, score=30)

    apply_resume_score_outcome(db_session, resume)

    email_log = db_session.scalar(select(EmailLog))
    assert application.status == "rejected"
    assert email_log.status == "pending"
    assert email_log.error_message == email_automation_service.CONSENT_REQUIRED
    assert sent_to == []

    application.candidate.email_consent = True
    db_session.commit()
    delivered = email_automation_service.send_consent_pending_emails(
        db_session, application.candidate
    )

    assert [log.status for log in delivered] == ["sent"]
    assert sent_to == ["taylor@example.com"]
    assert email_automation_service.send_consent_pending_emails(
        db_session, application.candidate
    ) == []


def test_consent_requirement_can_be_disabled(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "email_automation_require_consent", False)
    sent_to = stub_delivery(monkeypatch)
    application, resume = create_application(db_session, score=30)

    apply_resume_score_outcome(db_session, resume)

    assert db_session.scalar(select(EmailLog)).status == "sent"
    assert sent_to == ["taylor@example.com"]


class FakeSmtp:
    instances: list["FakeSmtp"] = []

    def __init__(self, host, port, timeout=None):
        self.calls: list[str] = []
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, *_args):
        self.calls.append("login")

    def send_message(self, _message):
        self.calls.append("send")


@pytest.mark.parametrize(
    ("port", "smtp_attr", "expected_calls"),
    [
        (587, "SMTP", ["starttls", "login", "send"]),
        (465, "SMTP_SSL", ["login", "send"]),
    ],
)
def test_smtp_uses_the_right_transport_for_the_configured_port(
    monkeypatch: pytest.MonkeyPatch,
    port: int,
    smtp_attr: str,
    expected_calls: list[str],
) -> None:
    FakeSmtp.instances = []
    monkeypatch.setattr(email_automation_service.smtplib, smtp_attr, FakeSmtp)
    for key, value in {
        "smtp_host": "smtp.example.com",
        "smtp_port": port,
        "smtp_user": "hr@example.com",
        "smtp_password": "app-password",
        "smtp_from_email": "hr@example.com",
    }.items():
        monkeypatch.setattr(settings, key, value)
    preview = email_automation_service.EmailPreview(
        email_type="rejection",
        recipient_email="taylor@example.com",
        subject="Subject",
        body="Body",
    )

    message_id = email_automation_service._deliver(preview, "key-1")

    assert message_id
    assert FakeSmtp.instances[0].calls == expected_calls


def test_review_score_stays_pending_without_sending_email(
    db_session: Session,
) -> None:
    application, resume = create_application(db_session, score=60)

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    assert application.status == "pending_review"
    assert db_session.scalar(select(EmailLog)) is None


def test_eligible_score_does_not_send_selection_email_automatically(
    db_session: Session,
) -> None:
    application, resume = create_application(db_session, score=82)

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    assert application.status == "interview_eligible"
    assert db_session.scalar(select(EmailLog)) is None


def test_eligible_score_sends_consent_gated_screening_invitation(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, resume = create_application(
        db_session,
        score=82,
        email_consent=True,
    )
    application.candidate.phone = "03001234567"
    monkeypatch.setattr(settings, "phone_default_region", "PK")
    monkeypatch.setattr(settings, "vapi_public_phone_number", "+14055541013")
    monkeypatch.setattr(
        email_automation_service,
        "_deliver",
        lambda *_args, **_kwargs: "screening-invitation-id",
    )

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    email_log = db_session.scalar(select(EmailLog))
    assert application.status == "interview_eligible"
    assert email_log is not None
    assert email_log.email_type == "screening_invitation"
    assert email_log.status == "sent"
    assert "+14055541013" in email_log.body
    assert "assistant's instructions" in email_log.body


def test_no_required_skill_match_is_rejected_with_email(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    application, resume = create_application(
        db_session,
        score=85,
        email_consent=True,
        matched_skills=[],
    )
    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    email_log = db_session.scalar(select(EmailLog))
    assert application.status == "rejected"
    assert "No required job skills were matched" in application.agent_review_reason
    assert email_log.email_type == "rejection"
    assert email_log.status == "sent"
    assert sent_to == ["taylor@example.com"]


def test_explicitly_empty_relevance_evidence_is_rejected_with_email(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    application, resume = create_application(
        db_session, score=65, email_consent=True
    )
    resume.evaluation_details = {
        "matched_skills": ["Python"],
        "evidence": [],
        "candidate_strengths": [],
        "relevant_experience": [],
        "relevant_projects": [],
    }

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    assert application.status == "rejected"
    assert "no relevant CV evidence" in application.agent_review_reason
    assert db_session.scalar(select(EmailLog)).status == "sent"
    assert sent_to == ["taylor@example.com"]


def test_missing_relevance_evidence_is_not_assumed_irrelevant(
    db_session: Session,
) -> None:
    application, resume = create_application(db_session, score=65)

    apply_resume_score_outcome(db_session, resume)

    db_session.refresh(application)
    assert application.status == "pending_review"
    assert application.agent_review_reason is None


def test_email_template_uses_candidate_and_job_values(db_session: Session) -> None:
    application, _ = create_application(db_session, score=25)
    application.status = "rejected"
    db_session.commit()

    preview = build_email_preview(application, "rejection")

    assert preview.recipient_email == "taylor@example.com"
    assert preview.subject == "Update Regarding Your Job Application at ZETECH"
    assert "Dear Taylor Candidate," in preview.body
    assert "Backend Engineer position at ZETECH" in preview.body


def test_flagged_application_requires_hr_decision_before_email(
    db_session: Session,
) -> None:
    application, _ = create_application(
        db_session,
        score=45,
        email_consent=True,
    )
    application.status = "over_agent_review"
    application.agent_review_reason = "CV score below configured threshold."
    db_session.commit()

    with pytest.raises(email_automation_service.EmailAutomationError):
        send_application_email(db_session, application, "selection")
    assert db_session.scalar(select(EmailLog)) is None

    application.status = "approved_by_hr"
    db_session.commit()
    email_log = send_application_email(db_session, application, "selection")
    assert email_log.email_type == "selection"
    assert email_log.status == "failed"


def test_agent_review_cancellation_notice_does_not_email_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = Candidate(
        id=UUID("99e88a68-2a7d-4c36-bc4c-9df60cbef992"),
        full_name="Taylor Candidate",
        email="taylor@example.com",
        email_consent=True,
    )
    job = Job(
        id=UUID("95c8ebf3-908e-4e16-9b9f-5379f453ce57"),
        title="Backend Engineer",
        description="Build dependable backend systems.",
        required_skills=["Python"],
    )
    start_at = datetime.now(timezone.utc)
    interview = Interview(
        id=UUID("0a5b67ca-a084-4ca6-80fb-59a232cb1874"),
        candidate_id=candidate.id,
        job_id=job.id,
        interviewer_email="manager@example.com",
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
    )
    deliveries: list[tuple[str, str, str, str]] = []

    def record_delivery(
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> str:
        deliveries.append((recipient, subject, body, idempotency_key))
        return "message-id"

    monkeypatch.setattr(email_service, "_send_email", record_delivery)
    monkeypatch.setattr(settings, "scheduling_test_mode", False)

    result = email_service.send_interview_notifications(
        interview,
        candidate,
        job,
        cancelled=True,
        notify_candidate=False,
    )

    assert result.status == "sent"
    assert [delivery[0] for delivery in deliveries] == ["manager@example.com"]


def test_real_delivery_configuration_failure_is_persisted_for_retry(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _ = create_application(
        db_session,
        score=25,
        email_consent=True,
    )
    application.status = "rejected"
    db_session.commit()
    for key in (
        "resend_api_key",
        "email_from_address",
        "smtp_host",
        "smtp_from_email",
        "smtp_user",
        "smtp_password",
    ):
        monkeypatch.setattr(settings, key, "")

    email_log = send_application_email(db_session, application, "rejection")

    assert email_log.status == "failed"
    assert email_log.sent_at is None
    assert "Configure RESEND_API_KEY" in (email_log.error_message or "")


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if connection._engine is not None:
        connection._engine.dispose()
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(
        settings,
        "database_url",
        f"sqlite:///{tmp_path / 'email-api.db'}",
    )
    for key in (
        "resend_api_key",
        "email_from_address",
        "smtp_host",
        "smtp_from_email",
        "smtp_user",
        "smtp_password",
    ):
        monkeypatch.setattr(settings, key, "")
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    connection.get_engine().dispose()
    monkeypatch.setattr(connection, "_engine", None)


def test_hr_decision_and_history_api_preserve_consent_gate(
    api_client: TestClient,
) -> None:
    candidate_response = api_client.post(
        "/api/candidates",
        json={"full_name": "Taylor Candidate", "email": "taylor@example.com"},
    )
    assert candidate_response.status_code == 201
    candidate_id = candidate_response.json()["id"]
    job_response = api_client.post(
        "/api/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Build dependable backend systems.",
            "status": "open",
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]
    application_response = api_client.post(
        "/api/applications",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]

    factory = sessionmaker(bind=connection.get_engine(), expire_on_commit=False)
    with factory() as db:
        db.add(
            ResumeEvaluation(
                candidate_id=UUID(candidate_id),
                application_id=UUID(application_id),
                job_id=UUID(job_id),
                file_name="candidate.pdf",
                file_path="candidate.pdf",
                score=65,
                evaluation_status="completed",
            )
        )
        db.commit()

    assert api_client.patch(
        f"/api/applications/{application_id}",
        json={"status": "approved_by_hr"},
    ).status_code == 409

    dashboard = api_client.get("/api/email-automation/applications")
    assert dashboard.status_code == 200
    assert dashboard.json()[0]["score_action"] == "hr_decision"
    assert dashboard.json()[0]["email_consent"] is False
    preview = api_client.get(
        f"/api/email-automation/applications/{application_id}/preview",
        params={"email_type": "selection"},
    )
    assert preview.status_code == 200
    assert preview.json()["can_send"] is False

    decision = api_client.post(
        f"/api/email-automation/applications/{application_id}/decision",
        json={"decision": "approve"},
    )
    assert decision.status_code == 200
    assert decision.json()["email_type"] == "selection"
    assert decision.json()["status"] == "pending"
    assert decision.json()["sent_at"] is None

    application = api_client.get(f"/api/applications/{application_id}")
    assert application.json()["status"] == "approved_by_hr"
    history = api_client.get("/api/email-automation/history").json()
    assert history[0]["status"] == "pending"

    consent = api_client.put(
        f"/api/candidates/{candidate_id}/email-consent",
        json={"email_consent": True},
    )
    assert consent.status_code == 200
    assert consent.json()["email_consent"] is True
    assert consent.json()["email_consent_at"] is not None
    approved_preview = api_client.get(
        f"/api/email-automation/applications/{application_id}/preview",
        params={"email_type": "selection"},
    )
    assert approved_preview.status_code == 200
    assert approved_preview.json()["can_send"] is True

    retry = api_client.post(
        f"/api/email-automation/history/{history[0]['id']}/retry"
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "failed"
    assert "Configure RESEND_API_KEY" in retry.json()["error_message"]
    assert retry.json()["sent_at"] is None

    delete_history = api_client.delete(
        f"/api/email-automation/applications/{application_id}/history"
    )
    assert delete_history.status_code == 204
    assert api_client.get("/api/applications/" + application_id).status_code == 200
    dashboard = api_client.get("/api/email-automation/applications")
    assert dashboard.json()[0]["emails"] == []
    assert api_client.get("/api/email-automation/history").json() == []
    assert api_client.post(
        f"/api/email-automation/history/{history[0]['id']}/retry"
    ).status_code == 410


@pytest.mark.parametrize(
    ("hr_decision", "expected_status", "expected_email"),
    [
        ("approve", "approved_by_hr", "selection"),
        ("reject", "rejected_by_hr", "rejection"),
    ],
)
def test_agent_review_decision_attempts_matching_email_with_audit_record(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    hr_decision: str,
    expected_status: str,
    expected_email: str,
) -> None:
    monkeypatch.setattr(settings, "email_automation_auto_reject", False)
    candidate_response = api_client.post(
        "/api/candidates",
        json={"full_name": "Taylor Candidate", "email": "taylor@example.com"},
    )
    candidate_id = candidate_response.json()["id"]
    api_client.put(
        f"/api/candidates/{candidate_id}/email-consent",
        json={"email_consent": True},
    )
    job_response = api_client.post(
        "/api/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Build dependable backend systems.",
            "status": "open",
        },
    )
    job_id = job_response.json()["id"]
    application_response = api_client.post(
        "/api/applications",
        json={"candidate_id": candidate_id, "job_id": job_id},
    )
    application_id = application_response.json()["id"]
    factory = sessionmaker(bind=connection.get_engine(), expire_on_commit=False)
    with factory() as db:
        resume = ResumeEvaluation(
            candidate_id=UUID(candidate_id),
            application_id=UUID(application_id),
            job_id=UUID(job_id),
            file_name="candidate.pdf",
            file_path="candidate.pdf",
            score=45,
            evaluation_details={
                "matched_skills": [],
                "missing_required_skills": ["Python"],
            },
            evaluation_status="completed",
        )
        db.add(resume)
        db.commit()
        apply_resume_score_outcome(db, resume)

    queue_response = api_client.get("/api/email-automation/review-queue")
    assert queue_response.status_code == 200
    queue_item = queue_response.json()[0]
    assert queue_item["application_id"] == application_id
    assert queue_item["cv_score"] == 45
    assert queue_item["matched_skills"] == []
    assert queue_item["missing_skills"] == ["Python"]
    assert "below" in queue_item["reason"]
    assert api_client.get("/api/email-automation/history").json() == []

    decision = api_client.post(
        f"/api/email-automation/review-queue/{application_id}/decision",
        json={"decision": hr_decision},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == expected_status
    assert decision.json()["email"]["email_type"] == expected_email
    assert decision.json()["email"]["status"] == "failed"
    assert "Configure RESEND_API_KEY" in decision.json()["email"]["error_message"]
    assert api_client.get("/api/email-automation/review-queue").json() == []

    preview = api_client.get(
        f"/api/email-automation/applications/{application_id}/preview",
        params={"email_type": expected_email},
    )
    assert preview.status_code == 200
    assert preview.json()["can_send"] is True

    manual_send = api_client.post(
        f"/api/email-automation/applications/{application_id}/send",
        json={"email_type": expected_email},
    )
    assert manual_send.status_code == 200
    assert manual_send.json()["status"] == "failed"
    assert len(api_client.get("/api/email-automation/history").json()) == 1


def seed_application_via_api(
    api_client: TestClient,
    *,
    score: int,
    consent: bool,
    details: dict | None = None,
) -> tuple[str, str]:
    candidate_id = api_client.post(
        "/api/candidates",
        json={"full_name": "Taylor Candidate", "email": "taylor@example.com"},
    ).json()["id"]
    if consent:
        api_client.put(
            f"/api/candidates/{candidate_id}/email-consent",
            json={"email_consent": True},
        )
    job_id = api_client.post(
        "/api/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Build dependable backend systems.",
            "status": "open",
        },
    ).json()["id"]
    application_id = api_client.post(
        "/api/applications",
        json={"candidate_id": candidate_id, "job_id": job_id},
    ).json()["id"]
    factory = sessionmaker(bind=connection.get_engine(), expire_on_commit=False)
    with factory() as db:
        resume = ResumeEvaluation(
            candidate_id=UUID(candidate_id),
            application_id=UUID(application_id),
            job_id=UUID(job_id),
            file_name="candidate.pdf",
            file_path="candidate.pdf",
            score=score,
            evaluation_details=details,
            evaluation_status="completed",
        )
        db.add(resume)
        db.commit()
        apply_resume_score_outcome(db, resume)
    return candidate_id, application_id


@pytest.mark.parametrize(
    ("hr_decision", "expected_status", "expected_email"),
    [
        ("approve", "approved_by_hr", "selection"),
        ("reject", "rejected_by_hr", "rejection"),
    ],
)
def test_hr_decision_sends_email_when_consented_and_delivery_works(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    hr_decision: str,
    expected_status: str,
    expected_email: str,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    _, application_id = seed_application_via_api(
        api_client, score=65, consent=True
    )

    decision = api_client.post(
        f"/api/email-automation/applications/{application_id}/decision",
        json={"decision": hr_decision},
    )

    assert decision.status_code == 200
    assert decision.json()["email_type"] == expected_email
    assert decision.json()["status"] == "sent"
    assert sent_to == ["taylor@example.com"]
    application = api_client.get(f"/api/applications/{application_id}")
    assert application.json()["status"] == expected_status


def test_recording_consent_releases_held_hr_approval_email(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    candidate_id, application_id = seed_application_via_api(
        api_client, score=65, consent=False
    )

    decision = api_client.post(
        f"/api/email-automation/applications/{application_id}/decision",
        json={"decision": "approve"},
    )
    assert decision.json()["status"] == "pending"
    assert sent_to == []

    consent = api_client.put(
        f"/api/candidates/{candidate_id}/email-consent",
        json={"email_consent": True},
    )

    assert consent.status_code == 200
    assert sent_to == ["taylor@example.com"]
    history = api_client.get("/api/email-automation/history").json()
    assert [(item["email_type"], item["status"]) for item in history] == [
        ("selection", "sent")
    ]


def test_hr_can_override_an_automatic_rejection(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to = stub_delivery(monkeypatch)
    _, application_id = seed_application_via_api(
        api_client,
        score=40,
        consent=True,
        details={"matched_skills": ["Python"]},
    )
    assert api_client.get(f"/api/applications/{application_id}").json()[
        "status"
    ] == "rejected"
    assert sent_to == ["taylor@example.com"]

    decision = api_client.post(
        f"/api/email-automation/review-queue/{application_id}/decision",
        json={"decision": "approve"},
    )

    assert decision.status_code == 200
    assert decision.json()["status"] == "approved_by_hr"
    assert decision.json()["email"]["email_type"] == "selection"
    assert decision.json()["email"]["status"] == "sent"
    assert sent_to == ["taylor@example.com", "taylor@example.com"]
