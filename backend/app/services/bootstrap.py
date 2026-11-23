"""Startup tasks that make the portals usable without manual database work."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_engine
from app.models.user import User
from app.security import hash_password, verify_password

logger = logging.getLogger(__name__)
MIN_PASSWORD_LENGTH = 12


def ensure_hr_account() -> None:
    """Create or refresh the single HR login from HR_PASSWORD in backend/.env.

    Whoever controls the server environment controls this account, so no emailed
    verification code is needed. Leave HR_PASSWORD blank to use emailed signup.
    """
    password = settings.hr_password
    if not password:
        return
    if len(password) < MIN_PASSWORD_LENGTH:
        logger.error("HR_PASSWORD must be at least %d characters; HR login was not created.", MIN_PASSWORD_LENGTH)
        return
    email = settings.hr_allowed_email.strip().casefold()
    with Session(get_engine()) as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            db.add(User(
                email=email,
                full_name="HR Administrator",
                password_hash=hash_password(password),
                role="hr",
                is_active=True,
                is_verified=True,
            ))
        else:
            if not verify_password(password, user.password_hash):
                user.password_hash = hash_password(password)
            user.role = "hr"
            user.is_active = True
            user.is_verified = True
            user.verification_code_hash = None
            user.verification_expires_at = None
        db.commit()
    logger.info("HR login is ready for %s.", email)
