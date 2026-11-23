"""Shared test setup: HR routes are protected, so tests act as a logged-in HR user.

Tests marked ``real_auth`` skip this and exercise the real login and token code.
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real_auth: use real tokens instead of a fake HR login")


@pytest.fixture(autouse=True)
def hr_logged_in(request):
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    from app.main import app
    from app.security import get_principal

    app.dependency_overrides[get_principal] = lambda: {
        "id": "test-hr",
        "role": "hr",
        "email": "hr@example.com",
    }
    yield
    app.dependency_overrides.pop(get_principal, None)
