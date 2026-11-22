"""Regression tests for the ElevenLabs outbound screening integration."""

import hashlib
import hmac
import time

import httpx

from app.agents.screening_agent import build_elevenlabs_call_payload
from app.api.screening import _transcript_text, _verify_elevenlabs_signature
from app.config import settings
from app.models.candidate import Candidate
from app.models.job import Job
from app.services import voice_service


def test_elevenlabs_payload_contains_existing_screening_context(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_agent_id", "agent-test")
    monkeypatch.setattr(settings, "elevenlabs_agent_phone_number_id", "phone-test")
    candidate = Candidate(
        full_name="Taylor Candidate",
        email="taylor@example.com",
        phone="+923001234567",
    )
    job = Job(
        title="Python Developer",
        description="Build APIs with Python and FastAPI.",
        required_skills=["Python", "FastAPI"],
    )

    payload = build_elevenlabs_call_payload(candidate, job, "screening-123")

    assert payload["agent_id"] == "agent-test"
    assert payload["agent_phone_number_id"] == "phone-test"
    assert payload["to_number"] == "+923001234567"
    assert payload["call_recording_enabled"] is False
    variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert variables["company_name"] == "ZETECH"
    assert variables["candidate_name"] == "Taylor Candidate"
    assert variables["job_title"] == "Python Developer"
    assert "FastAPI" in variables["required_skills"]
    assert variables["screening_id"] == "screening-123"


def test_elevenlabs_http_client_uses_api_key_and_expected_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-api-key")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "conversation_id": "conv-123",
                "callSid": "CA123",
            }

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(voice_service.httpx, "post", fake_post)
    result = voice_service.create_outbound_call({"agent_id": "agent-test"})

    assert result["conversation_id"] == "conv-123"
    assert captured["url"] == voice_service.ELEVENLABS_TWILIO_OUTBOUND_URL
    assert captured["headers"]["xi-api-key"] == "test-api-key"


def test_elevenlabs_webhook_signature_accepts_valid_and_rejects_invalid(monkeypatch):
    secret = "test-webhook-secret"
    monkeypatch.setattr(settings, "elevenlabs_webhook_secret", secret)
    body = b'{"type":"post_call_transcription","data":{"conversation_id":"conv-123"}}'
    timestamp = str(int(time.time()))
    signed = timestamp.encode() + b"." + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v0={digest}"

    assert _verify_elevenlabs_signature(body, header) is True
    assert _verify_elevenlabs_signature(body, f"t={timestamp},v0=bad") is False
    assert _verify_elevenlabs_signature(body, None) is False


def test_elevenlabs_webhook_signature_rejects_stale_timestamp(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_webhook_secret", "secret")
    timestamp = str(int(time.time()) - 3600)
    body = b'{}'
    digest = hmac.new(
        b"secret",
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    assert _verify_elevenlabs_signature(body, f"t={timestamp},v0={digest}") is False


def test_elevenlabs_transcript_turns_are_normalized_for_consent_parser():
    text = _transcript_text(
        [
            {"role": "agent", "message": "Do you consent to this call?"},
            {"role": "user", "message": "Yes, I agree."},
        ]
    )

    assert "AI: Do you consent" in text
    assert "User: Yes, I agree." in text
