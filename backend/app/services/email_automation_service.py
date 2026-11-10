"""Reusable ZETECH recruiting email templates and real delivery adapters."""

import hashlib
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.email_log import EmailLog
from app.models.interview import Interview
from app.services.phone_service import normalize_phone_number

logger = logging.getLogger(__name__)
RESEND_EMAILS_URL = "https://api.resend.com/emails"
EmailType = Literal[
    "rejection",
    "selection",
    "screening_invitation",
    "interview_invitation",
]
CONSENT_REQUIRED = "Candidate email consent has not been recorded."


class EmailAutomationError(RuntimeError):
    """A recruiting email could not be prepared or delivered."""


class EmailSendInProgress(EmailAutomationError):
    """An email with this idempotency key is already being delivered."""


@dataclass(frozen=True)
class EmailPreview:
    email_type: EmailType
    recipient_email: str
    subject: str
    body: str


def build_email_preview(
    application: Application,
    email_type: EmailType,
    interview: Interview | None = None,
) -> EmailPreview:
    candidate = application.candidate
    job = application.job
    if email_type == "rejection":
        subject = "Update Regarding Your Job Application at ZETECH"
        body = (
            f"Dear {candidate.full_name},\n\n"
            f"Thank you for applying for the {job.title} position at ZETECH and "
            "for taking the time to share your CV with us.\n\n"
            "After carefully reviewing your application, we regret to inform you "
            "that we will not be moving forward with your application at this time.\n\n"
            "We appreciate your interest in joining our team and encourage you to "
            "apply for future opportunities that match your skills and experience.\n\n"
            "We wish you success in your professional career.\n\n"
            "Best Regards,\nHR Team\nZETECH"
        )
    elif email_type == "selection":
        subject = "Congratulations! Your Application Has Been Shortlisted at ZETECH"
        body = (
            f"Dear {candidate.full_name},\n\n"
            f"We are pleased to inform you that your CV has been shortlisted for "
            f"the {job.title} position at ZETECH.\n\n"
            "Your skills, qualifications, and experience have attracted our "
            "attention, and we would like to proceed with the next stage of our "
            "recruitment process.\n\n"
            "Our HR team will coordinate the next steps with you.\n\n"
            "Congratulations, and thank you for your interest in ZETECH.\n\n"
            "Best Regards,\nHR Team\nZETECH"
        )
    elif email_type == "screening_invitation":
        if not settings.vapi_public_phone_number:
            raise EmailAutomationError(
                "Configure VAPI_PUBLIC_PHONE_NUMBER before inviting candidates to screening."
            )
        if normalize_phone_number(
            settings.vapi_public_phone_number, settings.phone_default_region
        ) is None:
            raise EmailAutomationError(
                "VAPI_PUBLIC_PHONE_NUMBER must be a valid international phone number."
            )
        if normalize_phone_number(
            candidate.phone, settings.phone_default_region
        ) is None:
            raise EmailAutomationError(
                "A valid candidate phone number is required for screening."
            )
        subject = f"Next Step for Your {job.title} Application"
        body = (
            f"Dear {candidate.full_name},\n\n"
            f"Thank you for applying for the {job.title} position at ZETECH. "
            "Your CV has been reviewed and we invite you to complete an initial "
            "AI-assisted screening.\n\n"
            f"Please call {settings.vapi_public_phone_number} and follow the "
            "assistant's instructions. The assistant will explain the screening "
            "and ask for your consent before proceeding. You may decline or end "
            "the call at any time.\n\n"
            "Best Regards,\nHR Team\nZETECH"
        )
    else:
        if interview is None:
            raise EmailAutomationError("Select a confirmed interview for this email.")
        if interview.interview_mode not in {"online", "on_site"}:
            raise EmailAutomationError(
                "Set the interview mode before sending the invitation."
            )
        if not interview.meeting_details:
            raise EmailAutomationError(
                "Set the meeting link or office address before sending the invitation."
            )
        start_at = interview.start_at
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        local_start = start_at.astimezone(ZoneInfo(settings.google_calendar_time_zone))
        subject = f"Interview Invitation – {job.title} at ZETECH"
        body = (
            f"Dear {candidate.full_name},\n\n"
            f"Congratulations! We are pleased to invite you for an interview for "
            f"the {job.title} position at ZETECH.\n\n"
            "Your interview details are:\n\n"
            f"- Date: {local_start.strftime('%A, %B %d, %Y')}\n"
            f"- Time: {local_start.strftime('%I:%M %p %Z')}\n"
            f"- Interview Mode: {'Online' if interview.interview_mode == 'online' else 'On-site'}\n"
            f"- Meeting Link or Location: {interview.meeting_details}\n\n"
            "Please confirm your availability by replying to this email.\n\n"
            "We look forward to speaking with you.\n\n"
            "Best Regards,\nHR Team\nZETECH"
        )
    return EmailPreview(
        email_type=email_type,
        recipient_email=candidate.email,
        subject=subject,
        body=body,
    )


def _idempotency_key(
    application: Application,
    email_type: EmailType,
    interview: Interview | None,
) -> str:
    if email_type == "interview_invitation" and interview is not None:
        start_at = interview.start_at.isoformat()
        return f"application-{application.id}-interview-{interview.id}-{start_at}"
    return f"application-{application.id}-{email_type}"


def _deliver(preview: EmailPreview, idempotency_key: str) -> str | None:
    smtp_configured = bool(settings.smtp_host)
    resend_configured = bool(settings.resend_api_key)
    if smtp_configured:
        from_address = settings.smtp_from_email or settings.email_from_address
        if not from_address:
            raise EmailAutomationError(
                "Configure SMTP_FROM_EMAIL or EMAIL_FROM_ADDRESS for SMTP delivery."
            )
        message = EmailMessage()
        message["From"] = from_address
        message["To"] = preview.recipient_email
        message["Subject"] = preview.subject
        message["Message-ID"] = (
            f"<{hashlib.sha256(idempotency_key.encode()).hexdigest()}@zetech.local>"
        )
        message.set_content(preview.body)
        try:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
            ) as client:
                client.starttls()
                if settings.smtp_user:
                    if not settings.smtp_password:
                        raise EmailAutomationError(
                            "SMTP_PASSWORD is required when SMTP_USER is configured."
                        )
                    client.login(settings.smtp_user, settings.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("SMTP recruiting email delivery failed.")
            raise EmailAutomationError("SMTP could not deliver the recruiting email.") from exc
        return message["Message-ID"]

    if not resend_configured or not settings.email_from_address:
        raise EmailAutomationError(
            "Configure RESEND_API_KEY and EMAIL_FROM_ADDRESS, or SMTP_HOST and a sender address."
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
                "to": [preview.recipient_email],
                "subject": preview.subject,
                "text": preview.body,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Resend recruiting email request failed with HTTP %s",
            exc.response.status_code,
        )
        raise EmailAutomationError(
            "Resend rejected the recruiting email."
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.error("Resend recruiting email request failed.")
        raise EmailAutomationError(
            "Resend could not deliver the recruiting email."
        ) from exc
    message_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(message_id, str):
        raise EmailAutomationError("Resend returned no email ID.")
    return message_id


def send_application_email(
    db: Session,
    application: Application,
    email_type: EmailType,
    interview: Interview | None = None,
) -> EmailLog:
    """Persist an auditable message, then deliver it at most once per key."""
    if (
        application.agent_review_reason
        and application.status == "over_agent_review"
    ):
        raise EmailAutomationError(
            "Candidate emails are disabled until HR decides an Over Agent Review application."
        )
    if email_type == "interview_invitation":
        if (
            interview is None
            or interview.status != "scheduled"
            or interview.test_mode
            or not interview.calendar_event_id
            or interview.candidate_id != application.candidate_id
            or interview.job_id != application.job_id
        ):
            raise EmailAutomationError(
                "An invitation requires a real, confirmed calendar booking."
            )
    elif email_type == "rejection" and application.status not in {
        "rejected",
        "rejected_by_hr",
    }:
        raise EmailAutomationError(
            "A rejection email requires a recorded rejection decision."
        )
    elif email_type == "selection" and application.status != "approved_by_hr":
        raise EmailAutomationError(
            "A selection email requires a recorded HR approval."
        )
    elif email_type == "screening_invitation" and application.status not in {
        "interview_eligible",
        "approved_by_hr",
    }:
        raise EmailAutomationError(
            "A screening invitation requires a CV-eligible application."
        )

    preview = build_email_preview(application, email_type, interview)
    key = _idempotency_key(application, email_type, interview)
    email_log = db.scalar(
        select(EmailLog).where(EmailLog.idempotency_key == key)
    )
    if email_log is not None and email_log.status == "sent":
        return email_log
    if (
        email_log is not None
        and email_log.status == "pending"
        and email_log.error_message != CONSENT_REQUIRED
    ):
        raise EmailSendInProgress("This email is already pending delivery.")

    if email_log is None:
        email_log = EmailLog(
            recipient_email=preview.recipient_email,
            subject=preview.subject,
            email_type=email_type,
            body=preview.body,
            idempotency_key=key,
            interview_id=interview.id if interview else None,
            status="pending",
            application_id=application.id,
        )
        db.add(email_log)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            email_log = db.scalar(
                select(EmailLog).where(EmailLog.idempotency_key == key)
            )
            if email_log is None:
                raise
            if email_log.status == "sent":
                return email_log
            if email_log.status == "pending":
                raise EmailSendInProgress(
                    "This email is already pending delivery."
                )
    else:
        email_log.recipient_email = preview.recipient_email
        email_log.subject = preview.subject
        email_log.body = preview.body
        email_log.status = "pending"
        email_log.error_message = None
        db.commit()

    if not application.candidate.email_consent:
        email_log.error_message = CONSENT_REQUIRED
        db.commit()
        db.refresh(email_log)
        return email_log

    try:
        provider_message_id = _deliver(preview, key)
    except EmailAutomationError as exc:
        email_log.status = "failed"
        email_log.error_message = str(exc)
        db.commit()
        db.refresh(email_log)
        return email_log
    email_log.status = "sent"
    email_log.provider_message_id = provider_message_id
    email_log.error_message = None
    email_log.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(email_log)
    return email_log


def get_email_log(db: Session, email_log_id: UUID) -> EmailLog | None:
    return db.scalar(
        select(EmailLog).where(EmailLog.id == email_log_id)
    )
