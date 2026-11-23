"""Real login, token, role and candidate-portal behavior (no fake HR login)."""

import base64
import json
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import security
from app.api import portal
from app.config import settings
from app.database import connection
from app.services import login_throttle
from app.services.upload_security import UnsafeUploadError, validate_resume_content

pytestmark = pytest.mark.real_auth

HR_EMAIL = "hr@example.com"
HR_PASSWORD = "correct-horse-battery"
CANDIDATE_PASSWORD = "candidate-password-123"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if connection._engine is not None:
        connection._engine.dispose()
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setattr(settings, "auth_secret_key", "unit-test-secret-" + "x" * 32)
    monkeypatch.setattr(settings, "hr_allowed_email", HR_EMAIL)
    monkeypatch.setattr(settings, "hr_password", HR_PASSWORD)
    monkeypatch.setattr(portal, "UPLOAD_DIRECTORY", tmp_path / "uploads")
    scored: list[object] = []
    monkeypatch.setattr(portal, "_process_resume_evaluation", lambda *args: scored.append(args))
    login_throttle.reset()
    from app.main import app

    with TestClient(app) as test_client:
        test_client.scored = scored
        yield test_client
    connection.get_engine().dispose()
    monkeypatch.setattr(connection, "_engine", None)
    login_throttle.reset()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def hr_headers(client: TestClient) -> dict[str, str]:
    response = login(client, HR_EMAIL, HR_PASSWORD)
    assert response.status_code == 200, response.text
    return bearer(response.json()["access_token"])


def register_candidate(client: TestClient, email: str = "sam@example.com") -> dict[str, str]:
    response = client.post(
        "/api/auth/candidate/register",
        json={"full_name": "Sam Candidate", "email": email, "password": CANDIDATE_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return bearer(response.json()["access_token"])


def open_job(client: TestClient) -> str:
    response = client.post(
        "/api/jobs",
        json={"title": "ML Engineer", "description": "Build ML systems.", "status": "open"},
        headers=hr_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def apply(client: TestClient, headers: dict[str, str], job_id: str, **overrides):
    data = {"job_id": job_id, "email_consent": "true", "phone": "", "notes": ""}
    data.update(overrides)
    return client.post(
        "/api/portal/apply",
        data=data,
        files={"file": ("cv.txt", b"Skills\nPython, machine learning\n", "text/plain")},
        headers=headers,
    )


# ---------- HR login ----------

def test_hr_logs_in_with_the_configured_password(client: TestClient) -> None:
    ok = login(client, HR_EMAIL, HR_PASSWORD)
    assert ok.status_code == 200
    assert ok.json()["role"] == "hr"
    assert login(client, HR_EMAIL.upper(), HR_PASSWORD).status_code == 200
    assert login(client, HR_EMAIL, "wrong-password-123").status_code == 401


def test_changing_hr_password_in_env_updates_the_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.bootstrap import ensure_hr_account

    monkeypatch.setattr(settings, "hr_password", "a-brand-new-password")
    ensure_hr_account()
    assert login(client, HR_EMAIL, "a-brand-new-password").status_code == 200
    assert login(client, HR_EMAIL, HR_PASSWORD).status_code == 401


def test_short_hr_password_is_refused(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.bootstrap import ensure_hr_account

    monkeypatch.setattr(settings, "hr_password", "short")
    ensure_hr_account()
    assert login(client, HR_EMAIL, "short").status_code == 401


def test_only_the_allowed_email_can_start_hr_signup(client: TestClient) -> None:
    response = client.post(
        "/api/auth/hr/register",
        json={"full_name": "Intruder", "email": "intruder@example.com", "password": "intruder-password-1"},
    )
    assert response.status_code == 403


# ---------- roles and route protection ----------

def test_hr_routes_require_an_hr_token(client: TestClient) -> None:
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/candidates").status_code == 401
    candidate = register_candidate(client)
    assert client.get("/api/jobs", headers=candidate).status_code == 403
    assert client.get("/api/email-automation/applications", headers=candidate).status_code == 403
    assert client.get("/api/jobs", headers=hr_headers(client)).status_code == 200


def test_portal_routes_require_a_candidate_token(client: TestClient) -> None:
    job_id = open_job(client)
    assert client.get("/api/portal/applications").status_code == 401
    assert apply(client, hr_headers(client), job_id).status_code == 403


def test_garbage_forged_and_expired_tokens_are_rejected(client: TestClient) -> None:
    assert client.get("/api/auth/me", headers=bearer("not-a-token")).status_code == 401

    def forge(header: dict, payload: dict, secret: bytes) -> str:
        def part(value: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
        import hashlib, hmac
        signing = f"{part(header)}.{part(payload)}"
        signature = base64.urlsafe_b64encode(hmac.new(secret, signing.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        return f"{signing}.{signature}"

    soon = int(time.time()) + 600
    none_alg = f"{base64.urlsafe_b64encode(json.dumps({'alg': 'none'}).encode()).rstrip(b'=').decode()}." \
               f"{base64.urlsafe_b64encode(json.dumps({'sub': 'x', 'role': 'hr', 'exp': soon}).encode()).rstrip(b'=').decode()}."
    assert client.get("/api/auth/me", headers=bearer(none_alg)).status_code == 401
    wrong_key = forge({"alg": "HS256", "typ": "JWT"}, {"sub": "x", "role": "hr", "exp": soon}, b"some-other-secret-key-0123456789")
    assert client.get("/api/auth/me", headers=bearer(wrong_key)).status_code == 401
    expired = forge({"alg": "HS256", "typ": "JWT"}, {"sub": "x", "role": "hr", "exp": int(time.time()) - 5}, security._secret())
    assert client.get("/api/auth/me", headers=bearer(expired)).status_code == 401


def test_me_reports_the_role_of_the_token(client: TestClient) -> None:
    assert client.get("/api/auth/me", headers=hr_headers(client)).json()["role"] == "hr"
    assert client.get("/api/auth/me", headers=register_candidate(client)).json()["role"] == "candidate"


def test_provider_webhook_is_reachable_without_an_hr_token_but_needs_its_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vapi_webhook_secret", "webhook-secret")
    body = {"message": {"type": "status-update", "status": "ringing", "call": {"id": "unknown"}}}
    assert client.post("/api/screening/webhook", json=body).status_code == 401  # the webhook's own check
    ok = client.post("/api/screening/webhook", json=body, headers={"x-vapi-secret": "webhook-secret"})
    assert ok.status_code == 200


# ---------- candidate accounts ----------

def test_candidate_registers_logs_in_and_cannot_register_twice(client: TestClient) -> None:
    register_candidate(client)
    assert login(client, "sam@example.com", CANDIDATE_PASSWORD).json()["role"] == "candidate"
    duplicate = client.post(
        "/api/auth/candidate/register",
        json={"full_name": "Sam", "email": "SAM@example.com", "password": CANDIDATE_PASSWORD},
    )
    assert duplicate.status_code == 409


def test_hr_email_cannot_be_used_for_a_candidate_account(client: TestClient) -> None:
    response = client.post(
        "/api/auth/candidate/register",
        json={"full_name": "Hr Person", "email": HR_EMAIL, "password": CANDIDATE_PASSWORD},
    )
    assert response.status_code == 403


def test_short_candidate_password_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/auth/candidate/register",
        json={"full_name": "Sam", "email": "sam@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_repeated_wrong_passwords_are_throttled(client: TestClient) -> None:
    for _ in range(login_throttle.MAX_FAILURES_PER_ACCOUNT):
        assert login(client, HR_EMAIL, "wrong-password-123").status_code == 401
    locked = login(client, HR_EMAIL, HR_PASSWORD)
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers


def test_a_successful_login_clears_the_failure_count(client: TestClient) -> None:
    for _ in range(login_throttle.MAX_FAILURES_PER_ACCOUNT - 1):
        login(client, HR_EMAIL, "wrong-password-123")
    assert login(client, HR_EMAIL, HR_PASSWORD).status_code == 200
    assert login(client, HR_EMAIL, "wrong-password-123").status_code == 401


# ---------- candidate portal ----------

def test_candidate_sees_open_jobs_only(client: TestClient) -> None:
    open_id = open_job(client)
    client.post(
        "/api/jobs",
        json={"title": "Closed role", "description": "Hidden.", "status": "closed"},
        headers=hr_headers(client),
    )
    jobs = client.get("/api/portal/jobs", headers=register_candidate(client)).json()
    assert [job["id"] for job in jobs] == [open_id]


def test_apply_creates_the_application_cv_and_consent_then_starts_scoring(client: TestClient) -> None:
    job_id = open_job(client)
    candidate = register_candidate(client)

    response = apply(client, candidate, job_id, phone="0300 1234567", notes="Available now")

    assert response.status_code == 201, response.text
    assert response.json()["stage"] == "under_review"
    assert len(client.scored) == 1  # CV scoring was queued
    hr = hr_headers(client)
    people = client.get("/api/candidates", headers=hr).json()
    assert people[0]["email_consent"] is True
    assert people[0]["email_consent_at"] is not None
    assert people[0]["phone"] == "+923001234567"
    assert people[0]["details"]["notes"] == "Available now"
    assert len(client.get("/api/applications", headers=hr).json()) == 1
    assert len(client.get("/api/resumes", headers=hr).json()) == 1
    mine = client.get("/api/portal/applications", headers=candidate).json()
    assert [(item["job_title"], item["stage"]) for item in mine] == [("ML Engineer", "under_review")]
    assert "score" not in json.dumps(mine).lower()


def test_apply_requires_consent_a_valid_phone_and_a_new_job(client: TestClient) -> None:
    job_id = open_job(client)
    candidate = register_candidate(client)
    assert apply(client, candidate, job_id, email_consent="false").status_code == 422
    assert apply(client, candidate, job_id, phone="abc").status_code == 422
    assert client.get("/api/portal/applications", headers=candidate).json() == []

    assert apply(client, candidate, job_id).status_code == 201
    assert apply(client, candidate, job_id).status_code == 409
    assert len(client.scored) == 1


def test_apply_rejects_closed_and_unknown_jobs(client: TestClient) -> None:
    candidate = register_candidate(client)
    closed = client.post(
        "/api/jobs",
        json={"title": "Closed", "description": "No.", "status": "closed"},
        headers=hr_headers(client),
    ).json()["id"]
    assert apply(client, candidate, closed).status_code == 404
    assert apply(client, candidate, "00000000-0000-4000-8000-000000000000").status_code == 404


def test_apply_rejects_files_whose_content_does_not_match_their_type(client: TestClient) -> None:
    job_id = open_job(client)
    candidate = register_candidate(client)
    fake_pdf = client.post(
        "/api/portal/apply",
        data={"job_id": job_id, "email_consent": "true"},
        files={"file": ("cv.pdf", b"<script>alert(1)</script>", "application/pdf")},
        headers=candidate,
    )
    assert fake_pdf.status_code == 415
    exe = client.post(
        "/api/portal/apply",
        data={"job_id": job_id, "email_consent": "true"},
        files={"file": ("cv.exe", b"MZ", "application/octet-stream")},
        headers=candidate,
    )
    assert exe.status_code == 415
    assert client.get("/api/portal/applications", headers=candidate).json() == []


# ---------- signing key ----------

def test_placeholder_secret_is_never_used_for_signing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_file = tmp_path / ".auth_secret"
    monkeypatch.setattr(security, "AUTH_SECRET_FILE", secret_file)
    monkeypatch.setattr(security, "_local_secret_cache", None)
    monkeypatch.setattr(settings, "auth_secret_key", "replace-with-a-random-secret-at-least-32-characters")

    key = security._secret()

    assert key != b"replace-with-a-random-secret-at-least-32-characters"
    assert secret_file.read_text(encoding="utf-8").encode() == key
    assert len(key) >= 32
    monkeypatch.setattr(security, "_local_secret_cache", None)
    assert security._secret() == key  # stable across restarts


def test_a_proper_configured_secret_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_secret_key", "k" * 40)
    assert security._secret() == b"k" * 40


# ---------- uploads ----------

def make_docx(extra: dict[str, bytes] | None = None) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_upload_content_checks() -> None:
    validate_resume_content(b"%PDF-1.7 ...", ".pdf")
    validate_resume_content(make_docx(), ".docx")
    validate_resume_content("plain résumé".encode(), ".txt")
    for content, extension in [
        (b"GIF89a", ".pdf"),
        (b"not a zip", ".docx"),
        (make_docx().replace(b"word/document.xml", b"word/other.xml!!!!")[:0] or b"PK\x03\x04junk", ".docx"),
        (b"abc\x00def", ".txt"),
        (b"\xff\xfe\xfa", ".txt"),
        (b"MZ", ".exe"),
    ]:
        with pytest.raises(UnsafeUploadError):
            validate_resume_content(content, extension)


def test_docx_without_a_document_part_is_refused() -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "hello")
    with pytest.raises(UnsafeUploadError):
        validate_resume_content(buffer.getvalue(), ".docx")
