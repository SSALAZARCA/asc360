"""
Per-cedula failed-attempt limiter for the PUBLIC satisfaction survey.

Why: identification is cedula + last 4 celular digits, so the second factor has
only 10^4 values. The per-IP slowapi limit does not stop an attacker with many
IPs (or a spoofed X-Forwarded-For) from brute-forcing it for a known cedula.
Failures are therefore also counted per NORMALIZED cedula, whether or not the
cedula exists, so the lock reveals nothing about existence.

Policy: MAX_FAILED_ATTEMPTS failures inside a fixed WINDOW_SECONDS window that
starts at the first failure lock the cedula until that window ends. 5 keeps a
customer who mistypes the digits a few times comfortable, and caps a guesser at
5 guesses per 15 minutes per cedula (~480/day, about 5% of the space per day).
A success clears the counter: the caller proved both factors.

Storage is in-memory and per-process, and resets on deploy. That is acceptable
for this risk level (uvicorn runs as a single process here); a shared store
such as Redis would be the upgrade path for multiple workers. Memory is bounded
by evicting expired entries on every write and capping tracked cedulas.
Nothing awaits inside these functions, so they are atomic on the event loop; a
lock still guards them in case a sync endpoint or thread ever calls them.
"""
import threading
import time
from collections import OrderedDict
from typing import Tuple

from app.motored.services.encuesta_carga import normalize_cedula

MAX_FAILED_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
MAX_TRACKED = 10_000
LOCKED_DETAIL = "Demasiados intentos con esta cédula. Espera unos minutos e inténtalo de nuevo."

# cedula -> (window_start, failures); insertion order = window_start order.
_failures: "OrderedDict[str, Tuple[float, int]]" = OrderedDict()
_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def _live_entry(key: str) -> Tuple[float, int]:
    """The entry if its window is still open; expired ones are dropped."""
    entry = _failures.get(key)
    if entry is not None and _now() - entry[0] >= WINDOW_SECONDS:
        del _failures[key]
        return (0.0, 0)
    return entry or (0.0, 0)


def _evict_expired() -> None:
    now = _now()
    while _failures:
        oldest = next(iter(_failures))
        if now - _failures[oldest][0] < WINDOW_SECONDS:
            break
        del _failures[oldest]


def failure_count(cedula_raw: str) -> int:
    with _lock:
        return _live_entry(normalize_cedula(cedula_raw))[1]


def is_locked(cedula_raw: str) -> bool:
    return failure_count(cedula_raw) >= MAX_FAILED_ATTEMPTS


def record_failure(cedula_raw: str) -> None:
    key = normalize_cedula(cedula_raw)
    with _lock:
        _evict_expired()
        start, count = _live_entry(key)
        if count == 0:
            start = _now()
        _failures[key] = (start, count + 1)
        while len(_failures) > MAX_TRACKED:
            _failures.popitem(last=False)


def clear(cedula_raw: str) -> None:
    with _lock:
        _failures.pop(normalize_cedula(cedula_raw), None)


def tracked_count() -> int:
    with _lock:
        return len(_failures)


def reset() -> None:
    """Test helper: forget every counter."""
    with _lock:
        _failures.clear()
