"""Server-side ElevenLabs browser conversation credential service; no telephony."""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
ELEVENLABS_TOKEN_URL = "https://api.elevenlabs.io/v1/convai/conversation/token"
ELEVENLABS_SIGNED_URL = "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"


class ElevenLabsServiceError(RuntimeError):
    """Raised when ElevenLabs cannot authorize a browser conversation."""


def create_browser_session(mode: str = "voice") -> dict[str, Any]:
    """Create a short-lived credential for a private browser conversation.

    Voice sessions use WebRTC conversation tokens. Text-only sessions use a
    signed WebSocket URL. The ElevenLabs API key never leaves the backend.
    """
    if not settings.elevenlabs_api_key or not settings.elevenlabs_agent_id:
        raise ElevenLabsServiceError(
            "Set ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID in backend/.env."
        )
    if mode not in {"voice", "text"}:
        raise ValueError("Conversation mode must be 'voice' or 'text'.")
    endpoint = ELEVENLABS_TOKEN_URL if mode == "voice" else ELEVENLABS_SIGNED_URL
    try:
        response = httpx.get(
            endpoint,
            params={"agent_id": settings.elevenlabs_agent_id},
            headers={"xi-api-key": settings.elevenlabs_api_key},
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("ElevenLabs browser session authorization failed: HTTP %s", exc.response.status_code)
        raise ElevenLabsServiceError(
            "ElevenLabs could not authorize this browser session. Check the agent and API key."
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.exception("ElevenLabs browser session request failed.")
        raise ElevenLabsServiceError("Could not connect to ElevenLabs.") from exc

    key = "token" if mode == "voice" else "signed_url"
    credential = body.get(key) if isinstance(body, dict) else None
    if not isinstance(credential, str) or not credential:
        raise ElevenLabsServiceError("ElevenLabs did not return a browser session credential.")
    return {key: credential, "mode": mode}
