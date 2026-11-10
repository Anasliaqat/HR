"""SQLAlchemy engine, session dependency, and database initialization."""

import importlib
import logging
import time
from collections.abc import Generator

from fastapi import HTTPException, status
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

INIT_DB_MAX_ATTEMPTS = 4
INIT_DB_RETRY_DELAYS = (1, 2, 4)


class DatabaseConfigurationError(RuntimeError):
    """Raised when DATABASE_URL is missing."""


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


_engine: Engine | None = None


def get_engine() -> Engine:
    """Create the configured SQLAlchemy engine on first use."""
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise DatabaseConfigurationError(
                "DATABASE_URL is required. Set it in backend/.env."
            )
        options: dict[str, object] = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
            if ":memory:" in settings.database_url:
                from sqlalchemy.pool import StaticPool

                options["poolclass"] = StaticPool
        elif settings.database_url.startswith(("postgresql://", "postgresql+")):
            options["connect_args"] = {"connect_timeout": 5}
        _engine = create_engine(settings.database_url, **options)
    return _engine


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request."""
    try:
        factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    except DatabaseConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    with factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


def init_db() -> None:
    """Create tables with bounded retries for a database that is becoming ready."""
    importlib.import_module("app.models")

    engine = get_engine()
    for attempt in range(1, INIT_DB_MAX_ATTEMPTS + 1):
        try:
            Base.metadata.create_all(bind=engine)
            migrate_job_columns(engine)
            migrate_resume_columns(engine)
            migrate_email_automation_columns(engine)
            migrate_screening_columns(engine)
            return
        except OperationalError:
            if attempt == INIT_DB_MAX_ATTEMPTS:
                logger.exception(
                    "Database initialization failed after %d attempts.",
                    INIT_DB_MAX_ATTEMPTS,
                )
                raise

            delay = INIT_DB_RETRY_DELAYS[attempt - 1]
            logger.warning(
                "Database initialization attempt %d/%d failed; retrying in %d seconds.",
                attempt,
                INIT_DB_MAX_ATTEMPTS,
                delay,
            )
            time.sleep(delay)


def migrate_job_columns(engine: Engine) -> None:
    """Add job fields absent from databases created by earlier app versions."""
    with engine.begin() as connection:
        existing_columns = {
            column["name"] for column in inspect(connection).get_columns("jobs")
        }
        additions = {
            "preferred_skills": "JSON NOT NULL DEFAULT '[]'",
            "education": "TEXT",
            "number_of_vacancies": "INTEGER NOT NULL DEFAULT 1",
            "status": "VARCHAR(20) NOT NULL DEFAULT 'draft'",
        }
        for column_name, column_definition in additions.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE jobs ADD COLUMN {column_name} "
                        f"{column_definition}"
                    )
                )


def migrate_resume_columns(engine: Engine) -> None:
    """Add job association and normalize status for existing resume records."""
    with engine.begin() as connection:
        existing_columns = {
            column["name"]
            for column in inspect(connection).get_columns("resume_evaluations")
        }
        if "job_id" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE resume_evaluations ADD COLUMN job_id "
                    "UUID REFERENCES jobs(id) ON DELETE SET NULL"
                )
            )
        if "extracted_text" not in existing_columns:
            connection.execute(
                text("ALTER TABLE resume_evaluations ADD COLUMN extracted_text TEXT")
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_resume_evaluations_job_id "
                "ON resume_evaluations (job_id)"
            )
        )
        connection.execute(
            text(
                "UPDATE resume_evaluations SET evaluation_status = "
                "CASE WHEN score IS NOT NULL THEN 'completed' "
                "WHEN evaluation_status IN ('not_evaluated', 'evaluated') "
                "THEN 'pending' ELSE evaluation_status END"
            )
        )


def migrate_email_automation_columns(engine: Engine) -> None:
    """Add consent, delivery audit, and interview details to existing databases."""
    additions = {
        "candidates": {
            "email_consent": "BOOLEAN NOT NULL DEFAULT FALSE",
            "email_consent_at": "TIMESTAMP",
        },
        "email_logs": {
            "email_type": "VARCHAR(40) NOT NULL DEFAULT 'legacy'",
            "body": "TEXT",
            "idempotency_key": "VARCHAR(255)",
            "interview_id": "UUID REFERENCES interviews(id) ON DELETE SET NULL",
            "deleted_at": "TIMESTAMP",
        },
        "interviews": {
            "interview_mode": "VARCHAR(20)",
            "meeting_details": "TEXT",
        },
        "applications": {
            "agent_review_reason": "TEXT",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_definition in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} "
                            f"{column_definition}"
                        )
                    )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_email_logs_idempotency_key ON email_logs (idempotency_key)"
            )
        )


def migrate_screening_columns(engine: Engine) -> None:
    """Add call timing and consent-gated recording fields to existing databases."""
    with engine.begin() as connection:
        existing_columns = {
            column["name"]
            for column in inspect(connection).get_columns("screenings")
        }
        timestamp_type = (
            "TIMESTAMP WITH TIME ZONE"
            if connection.dialect.name == "postgresql"
            else "TIMESTAMP"
        )
        additions = {
            "started_at": timestamp_type,
            "ended_at": timestamp_type,
            "recording_url": "TEXT",
            "end_report_received": "BOOLEAN NOT NULL DEFAULT FALSE",
        }
        for column_name, column_definition in additions.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE screenings ADD COLUMN {column_name} "
                        f"{column_definition}"
                    )
                )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_screenings_call_id "
                "ON screenings (call_id) WHERE call_id IS NOT NULL"
            )
        )
