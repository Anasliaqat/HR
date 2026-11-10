"""Server-side Vapi HTTP client."""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
VAPI_CALLS_URL = "https://api.vapi.ai/call"


class VapiServiceError(RuntimeError):
    """Raised when Vapi cannot create an outbound call."""


def create_outbound_call(payload: dict[str, object]) -> dict[str, Any]:
    """Create one call with the private Vapi key; no call is made unless invoked."""
    if not settings.vapi_api_key:
        raise VapiServiceError("VAPI_API_KEY is not configured.")
    try:
        response = httpx.post(
            VAPI_CALLS_URL,
            headers={
                "Authorization": f"Bearer {settings.vapi_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        call = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Vapi call creation failed with HTTP %s", exc.response.status_code)
        raise VapiServiceError("Vapi rejected the outbound call request.") from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.error("Vapi call creation failed due to a transport or response error.")
        raise VapiServiceError("Vapi could not create the outbound call.") from exc

    if not isinstance(call, dict) or not isinstance(call.get("id"), str):
        raise VapiServiceError("Vapi returned a response without a call ID.")
    return call
