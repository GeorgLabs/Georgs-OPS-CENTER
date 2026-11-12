"""M4 - slow down password guessing.

A login form without a limit lets an attacker try thousands of passwords per minute.
Idea: remember failed attempts per (client address, username). After MAX_FAILURES inside
WINDOW_SECONDS, refuse further attempts with HTTP 429 and a `Retry-After` header.

(This version lives in memory, so it works for one server process. With several processes
you would keep the counters in Redis or the database - a good question for your mentor.)
"""

import time  # noqa: F401
import threading
from collections import deque


MAX_FAILURES = 5
WINDOW_SECONDS = 60

_failures: dict[tuple, deque[float]] = {}
_lock = threading.Lock()

def blocked_for(key: tuple) -> int:
    """TODO M4 - seconds until `key` may try again, 0 = allowed. (Right now: always allowed.)"""
    now = time.monotonic()
    with _lock:
        attempts = _failures.get(key)
        if not attempts:
            return 0
        while attempts and now - attempts[0] > WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            _failures.pop(key, None)
            return 0
        if len(attempts) >= MAX_FAILURES:
            return max(1, int(WINDOW_SECONDS - (now - attempts[0])) + 1)
        return 0


def record_failure(key: tuple) -> None:
    """TODO M4 - remember one failed attempt for `key`, with its time."""
    now = time.monotonic()
    with _lock:
        _failures.setdefault(key, deque()).append(now)
        if len(_failures) > 10_000:
            for stale in [k for k, v in _failures.items() if now - v[-1] > WINDOW_SECONDS]:
                _failures.pop(stale, None)


def reset(key: tuple) -> None:
    """TODO M4 - forget the failures of `key` (after a successful login)."""
    with _lock:
        _failures.pop(key, None)
