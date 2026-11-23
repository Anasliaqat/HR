"""Regression tests for private ElevenLabs browser screening sessions."""
import hashlib
import hmac
import time

from app.api.screening import _transcript_text, _verify_elevenlabs_signature
from app.agents.screening_agent import candidate_consented_on_call
from app.config import settings
from app.services import voice_service


def test_browser_session_uses_private_token_and_api_key(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-api-key")
    monkeypatch.setattr(settings, "elevenlabs_agent_id", "agent-test")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"token": "short-lived-token"}

    def fake_get(url, params, headers, timeout):
        captured.update(url=url, params=params, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(voice_service.httpx, "get", fake_get)
    result = voice_service.create_browser_session("voice")

    assert result == {"token": "short-lived-token", "mode": "voice"}
    assert captured["url"] == voice_service.ELEVENLABS_TOKEN_URL
    assert captured["params"] == {"agent_id": "agent-test"}
    assert captured["headers"]["xi-api-key"] == "test-api-key"


def test_browser_text_session_uses_signed_websocket_url(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-api-key")
    monkeypatch.setattr(settings, "elevenlabs_agent_id", "agent-test")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"signed_url": "wss://example.test/session"}

    monkeypatch.setattr(voice_service.httpx, "get", lambda *args, **kwargs: FakeResponse())
    assert voice_service.create_browser_session("text") == {
        "signed_url": "wss://example.test/session",
        "mode": "text",
    }


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
    body = b"{}"
    digest = hmac.new(
        b"secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert _verify_elevenlabs_signature(body, f"t={timestamp},v0={digest}") is False


def test_elevenlabs_transcript_turns_are_normalized_for_consent_parser():
    text = _transcript_text([
        {"role": "agent", "message": "Do you consent to this screening?"},
        {"role": "user", "message": "Yes, I agree."},
    ])
    assert "AI: Do you consent" in text
    assert "User: Yes, I agree." in text


def test_candidate_withdrawal_overrides_initial_consent():
    transcript = (
        "AI: Do you consent to screening and transcription?\n"
        "User: Yes, I agree.\n"
        "AI: Please introduce yourself.\n"
        "User: I withdraw my consent."
    )
    assert candidate_consented_on_call(transcript) is False


def test_candidate_affirmative_consent_without_withdrawal_is_accepted():
    transcript = (
        "AI: Do you consent to screening and transcription?\n"
        "User: Yes, I agree.\n"
        "AI: Please introduce yourself.\n"
        "User: I am a Python developer."
    )
    assert candidate_consented_on_call(transcript) is True
