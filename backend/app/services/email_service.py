"""Resend email delivery with a no-send test mode."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Job

logger = logging.getLogger(__name__)
RESEND_EMAILS_URL = "https://api.resend.com/emails"


class EmailServiceError(RuntimeError):
    """Raised when a confirmation email cannot be sent."""


@dataclass(frozen=True)
class NotificationResult:
    status: str
    errors: list[str]


def _send_email(to: str, subject: str, text: str, idempotency_key: str) -> str:
    if settings.scheduling_test_mode:
        return "test-mode"
    if not settings.resend_api_key or not settings.email_from_address:
        raise EmailServiceError(
            "RESEND_API_KEY and EMAIL_FROM_ADDRESS must be configured."
        )
    try:
        response = httpx.post(
            RESEND_EMAILS_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            json={
                "from": settings.email_from_address,
                "to": [to],
                "subject": subject,
                "text": text,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        payload: Any = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Resend email request failed with HTTP %s", exc.response.status_code)
        raise EmailServiceError("Resend rejected an interview notification.") from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.error("Resend email request failed due to a transport or response error.")
        raise EmailServiceError("Resend could not deliver an interview notification.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise EmailServiceError("Resend returned no email ID.")
    return payload["id"]


def _appointment_text(
    candidate: Candidate,
    job: Job,
    interviewer_email: str,
    start_at: datetime,
    end_at: datetime,
    *,
    cancelled: bool,
) -> str:
    label = "cancelled" if cancelled else "scheduled"
    return (
        f"Hello,\n\nThe interview for {candidate.full_name} for "
        f"{job.title} has been {label}.\n\n"
        f"Interviewer: {interviewer_email}\n"
        f"Start: {start_at.isoformat()}\n"
        f"End: {end_at.isoformat()}\n\n"
        "Please contact the hiring team if you have questions.\n"
    )


def send_interview_notifications(
    interview: Interview,
    candidate: Candidate,
    job: Job,
    *,
    cancelled: bool = False,
    notify_candidate: bool = True,
) -> NotificationResult:
    """Notify both parties independently, reporting failures without hiding them."""
    subject = (
        f"Interview cancelled: {job.title}"
        if cancelled
        else f"Interview scheduled: {job.title}"
    )
    text = _appointment_text(
        candidate,
        job,
        interview.interviewer_email,
        interview.start_at,
        interview.end_at,
        cancelled=cancelled,
    )
    errors: list[str] = []
    recipients = [("interviewer", interview.interviewer_email)]
    if cancelled and notify_candidate:
        if candidate.email_consent:
            recipients.insert(0, ("candidate", candidate.email))
        else:
            errors.append("candidate: Candidate email consent has not been recorded.")
    sent_count = 0
    for recipient, address in recipients:
        try:
            _send_email(
                address,
                subject,
                text,
                f"interview-{interview.id}-{recipient}-{interview.start_at.isoformat()}",
            )
            sent_count += 1
        except EmailServiceError as exc:
            logger.warning(
                "Could not send %s interview notification for %s: %s",
                recipient,
                interview.id,
                exc,
            )
            errors.append(f"{recipient}: {exc}")

    if errors and sent_count:
        result_status = "partial_failed"
    elif errors:
        result_status = "failed"
    else:
        result_status = "test_mode" if settings.scheduling_test_mode else "sent"
    return NotificationResult(status=result_status, errors=errors)
