"""Server-side ElevenLabs Conversational AI telephony client."""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
ELEVENLABS_TWILIO_OUTBOUND_URL = (
    "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"
)


class ElevenLabsServiceError(RuntimeError):
    """Raised when ElevenLabs cannot create an outbound screening call."""


def create_outbound_call(payload: dict[str, object]) -> dict[str, Any]:
    """Start an outbound call using an ElevenLabs agent and linked phone number."""
    if not settings.elevenlabs_api_key:
        raise ElevenLabsServiceError("ELEVENLABS_API_KEY is not configured.")
    try:
        response = httpx.post(
            ELEVENLABS_TWILIO_OUTBOUND_URL,
            headers={
                "xi-api-key": settings.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        call = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "ElevenLabs call creation failed with HTTP %s",
            exc.response.status_code,
        )
        raise ElevenLabsServiceError(
            "ElevenLabs rejected the outbound call request. Check the agent, "
            "phone-number integration, and account calling permissions."
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.error("ElevenLabs call creation failed due to a transport/response error.")
        raise ElevenLabsServiceError(
            "ElevenLabs could not create the outbound call."
        ) from exc

    if (
        not isinstance(call, dict)
        or call.get("success") is not True
        or not isinstance(call.get("conversation_id"), str)
    ):
        raise ElevenLabsServiceError(
            "ElevenLabs response did not include a successful conversation ID."
        )
    return call
