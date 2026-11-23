"""Small in-memory brute-force guard for login and verification-code attempts.

State lives in this process only, which is right for a single backend instance. If
the API is ever run on several servers, move this to a shared store such as Redis.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_ACCOUNT = 8
MAX_FAILURES_PER_ADDRESS = 30

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)


def _recent(key: str, now: float) -> deque[float]:
    attempts = _failures[key]
    while attempts and now - attempts[0] > WINDOW_SECONDS:
        attempts.popleft()
    return attempts


def check_allowed(account: str, address: str) -> None:
    """Raise 429 when this account or address has failed too often recently."""
    now = time.monotonic()
    with _lock:
        for key, limit in ((f"a:{account}", MAX_FAILURES_PER_ACCOUNT), (f"ip:{address}", MAX_FAILURES_PER_ADDRESS)):
            attempts = _recent(key, now)
            if len(attempts) >= limit:
                wait = int(WINDOW_SECONDS - (now - attempts[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts. Please wait a few minutes and try again.",
                    headers={"Retry-After": str(wait)},
                )


def record_failure(account: str, address: str) -> None:
    now = time.monotonic()
    with _lock:
        _recent(f"a:{account}", now).append(now)
        _recent(f"ip:{address}", now).append(now)


def record_success(account: str) -> None:
    with _lock:
        _failures.pop(f"a:{account}", None)


def reset() -> None:
    with _lock:
        _failures.clear()
