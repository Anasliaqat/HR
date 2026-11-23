"""One place that sends mail through the configured SMTP account (Gmail supported)."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)
SMTP_SSL_PORT = 465


class SmtpDeliveryError(RuntimeError):
    """The message could not be delivered; the text is safe to show to HR."""


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def _detail(exc: Exception) -> str:
    """A short server reason such as '535 5.7.8 Username and Password not accepted'."""
    code = getattr(exc, "smtp_code", None)
    raw = getattr(exc, "smtp_error", None)
    reason = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or exc)
    reason = " ".join(reason.split())[:200]
    return f"{code} {reason}".strip() if code else f"{type(exc).__name__}: {reason}"


def send_message(message: EmailMessage) -> None:
    if not smtp_configured():
        raise SmtpDeliveryError(
            "Email is not configured. Set SMTP_HOST, SMTP_USER and SMTP_PASSWORD in backend/.env "
            "(for Gmail use a Google App Password)."
        )
    try:
        if settings.smtp_port == SMTP_SSL_PORT:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=20,
                context=ssl.create_default_context(),
            ) as client:
                client.login(settings.smtp_user, settings.smtp_password)
                client.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
                client.ehlo()
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
                client.login(settings.smtp_user, settings.smtp_password)
                client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("SMTP authentication failed: %s", _detail(exc))
        raise SmtpDeliveryError(
            "SMTP login was rejected. Check SMTP_USER and use a Google App Password "
            f"(not your normal Gmail password) in SMTP_PASSWORD. Server said: {_detail(exc)}."
        ) from exc
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("SMTP delivery failed: %s", _detail(exc))
        raise SmtpDeliveryError(
            f"SMTP could not deliver the email ({_detail(exc)}). Check SMTP_HOST, SMTP_PORT and the account settings."
        ) from exc
