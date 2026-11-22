import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app import main


class HealthyConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _statement):
        return 1


class HealthyEngine:
    def connect(self):
        return HealthyConnection()


def test_health_check_confirms_database_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_engine", lambda: HealthyEngine())

    assert main.health_check() == {"status": "ok", "database": "connected"}


def test_health_check_returns_503_when_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableEngine:
        def connect(self):
            raise OperationalError("connect", {}, OSError("database unavailable"))

    monkeypatch.setattr(main, "get_engine", lambda: UnavailableEngine())

    with pytest.raises(HTTPException) as raised:
        main.health_check()

    assert raised.value.status_code == 503
    assert "Database is unavailable" in raised.value.detail
