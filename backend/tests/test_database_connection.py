import pytest
from sqlalchemy.exc import OperationalError

from app.database import connection


def test_init_db_retries_transient_operational_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[int] = []

    def create_all(bind: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OperationalError("connect", {}, OSError("database unavailable"))

    monkeypatch.setattr(connection, "get_engine", lambda: object())
    monkeypatch.setattr(connection.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(connection, "migrate_job_columns", lambda engine: None)
    monkeypatch.setattr(connection, "migrate_resume_columns", lambda engine: None)
    monkeypatch.setattr(
        connection, "migrate_email_automation_columns", lambda engine: None
    )
    monkeypatch.setattr(connection, "migrate_screening_columns", lambda engine: None)
    monkeypatch.setattr(connection.time, "sleep", delays.append)

    connection.init_db()

    assert attempts == 3
    assert delays == [1, 2]


def test_init_db_reraises_after_retry_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[int] = []
    failure = OperationalError("connect", {}, OSError("database unavailable"))

    def create_all(bind: object) -> None:
        nonlocal attempts
        attempts += 1
        raise failure

    monkeypatch.setattr(connection, "get_engine", lambda: object())
    monkeypatch.setattr(connection.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(connection.time, "sleep", delays.append)

    with pytest.raises(OperationalError) as raised:
        connection.init_db()

    assert raised.value is failure
    assert attempts == connection.INIT_DB_MAX_ATTEMPTS
    assert delays == [1, 2, 4]
