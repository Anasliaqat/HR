"""SMTP email delivery for interview notifications."""

import hashlib
import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage

from app.config import settings
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Job

logger = logging.getLogger(__name__)


class EmailServiceError(RuntimeError):
    """Raised when a confirmation email cannot be sent."""


@dataclass(frozen=True)
class NotificationResult:
    status: str
    errors: list[str]


def _send_email(to: str, subject: str, text: str, idempotency_key: str) -> str:
    if settings.scheduling_test_mode:
        return "test-mode"
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise EmailServiceError(
            "SMTP_HOST, SMTP_USER, and SMTP_PASSWORD must be configured."
        )

    message = EmailMessage()
    message["From"] = settings.smtp_from_email or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = (
        f"<{hashlib.sha256(idempotency_key.encode()).hexdigest()}@zetech.local>"
    )
    message.set_content(text)

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
                context=ssl.create_default_context(),
            ) as client:
                client.login(settings.smtp_user, settings.smtp_password)
                client.send_message(message)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
            ) as client:
                client.ehlo()
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
                client.login(settings.smtp_user, settings.smtp_password)
                client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("SMTP interview notification authentication failed.")
        raise EmailServiceError(
            "SMTP authentication failed. For Gmail, use a Google App Password."
        ) from exc
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("SMTP interview notification delivery failed.")
        raise EmailServiceError(
            "SMTP could not deliver the interview notification. Check the SMTP settings."
        ) from exc

    return message["Message-ID"]


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
    if notify_candidate:
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
