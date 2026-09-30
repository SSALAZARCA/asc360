"""
Per-cedula failed-attempt limit of the PUBLIC survey (login-hardening T5).
The per-IP slowapi limit cannot stop a many-IP brute force of the 4 celular
digits, so failures are also counted per normalized cedula.
"""
from datetime import datetime

import pytest

from app.core.limiter import limiter
from app.main import app
from app.config import settings
from app.motored.services import encuesta_intentos as intentos
from tests.motored.test_encuesta_publica_api import (
    _identificar, _payload, _reg, _session, _submit, _target,
)

LOCKED_DETAIL = "Demasiados intentos con esta cédula. Espera unos minutos e inténtalo de nuevo."
MAX_FAILS = intentos.MAX_FAILED_ATTEMPTS


@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "encuesta-intentos-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "encuesta-intentos-test-asc360-secret")
    limiter.reset()
    intentos.reset()
    yield
    limiter.reset()
    intentos.reset()
    app.dependency_overrides.clear()


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(intentos, "_now", lambda: now["t"])
    return now


def _fail_identificar(cedula="1.234.567-8", times=MAX_FAILS):
    for _ in range(times):
        limiter.reset()  # isolate from the per-IP limit
        _session([])
        assert _identificar(cedula=cedula).status_code == 200


def _assert_locked(response):
    assert response.status_code == 429
    assert response.json() == {"detail": LOCKED_DETAIL}


def test_constants_are_five_failures_in_fifteen_minutes():
    assert (intentos.MAX_FAILED_ATTEMPTS, intentos.WINDOW_SECONDS) == (5, 900)


def test_locks_after_max_failures_even_with_correct_digits(clock):
    _fail_identificar()
    _session([_reg()])  # would match now
    _assert_locked(_identificar())


def test_locked_attempt_does_not_query_the_database(clock):
    _fail_identificar()
    session = _session([_reg()])
    _identificar()
    assert len(session.executed_statements) == 1  # only the readiness probe


def test_formatting_variants_share_one_counter(clock):
    _fail_identificar("1.234.567-8", times=3)
    _fail_identificar("12345678", times=2)
    _session([_reg()])
    _assert_locked(_identificar("1234 5678"))


def test_other_cedula_is_unaffected(clock):
    _fail_identificar()
    _session([_reg()])
    assert _identificar(cedula="999").status_code == 200


def test_below_threshold_is_not_locked(clock):
    _fail_identificar(times=MAX_FAILS - 1)
    _session([_reg()])
    assert _identificar().json()["estado"] == "PENDIENTE"


def test_non_existent_cedula_locks_with_the_same_body(clock):
    _fail_identificar("55555555")
    _session([])
    _assert_locked(_identificar("55555555"))


def test_lock_lapses_after_the_window(clock):
    _fail_identificar()
    clock["t"] += intentos.WINDOW_SECONDS + 1
    _session([_reg()])
    assert _identificar().json()["estado"] == "PENDIENTE"


def test_still_locked_just_before_the_window_ends(clock):
    _fail_identificar()
    clock["t"] += intentos.WINDOW_SECONDS - 1
    limiter.reset()
    _session([_reg()])
    _assert_locked(_identificar())


def test_success_clears_the_counter(clock):
    _fail_identificar(times=MAX_FAILS - 1)
    limiter.reset()
    _session([_reg()])
    assert _identificar().json()["estado"] == "PENDIENTE"
    _fail_identificar(times=MAX_FAILS - 1)
    limiter.reset()
    _session([_reg()])
    assert _identificar().status_code == 200


def test_already_answered_also_clears_the_counter(clock):
    _fail_identificar(times=MAX_FAILS - 1)
    limiter.reset()
    _session([_reg(respondida=datetime(2026, 9, 2))])
    assert _identificar().json()["estado"] == "YA_RESPONDIDA"
    assert intentos.is_locked("12345678") is False
    _fail_identificar(times=MAX_FAILS - 1)
    assert intentos.is_locked("12345678") is False


def test_respuestas_locked_cedula_is_429(clock):
    _fail_identificar()
    rid, row = _target()
    session = _session([row])
    _assert_locked(_submit(_payload(rid)))
    assert session.committed is False


def test_respuestas_404_counts_as_a_failure(clock):
    for _ in range(MAX_FAILS):
        limiter.reset()
        _session([])
        assert _submit(_payload(_target()[0])).status_code == 404
    limiter.reset()
    _session([_reg()])
    _assert_locked(_identificar())


def test_respuestas_success_clears_the_counter(clock):
    _fail_identificar(times=MAX_FAILS - 1)
    rid, row = _target()
    limiter.reset()
    _session([row])
    assert _submit(_payload(rid)).status_code == 200
    assert intentos.is_locked("12345678") is False
    _fail_identificar(times=MAX_FAILS - 1)
    assert intentos.is_locked("12345678") is False


def test_respuestas_409_keeps_identity_verified_and_clears(clock):
    _fail_identificar(times=MAX_FAILS - 1)
    rid, row = _target(respondida=True)
    limiter.reset()
    _session([row])
    assert _submit(_payload(rid)).status_code == 409
    _fail_identificar(times=MAX_FAILS - 1)
    assert intentos.is_locked("12345678") is False


def test_per_ip_limit_still_applies(clock):
    for _ in range(10):
        _session([_reg()])
        assert _identificar(cedula="777").status_code == 200
    _session([_reg()])
    assert _identificar(cedula="777").status_code == 429


# --- unit: memory bounds --------------------------------------------------------

def test_expired_entries_are_evicted_opportunistically(clock):
    intentos.record_failure("111")
    clock["t"] += intentos.WINDOW_SECONDS + 1
    intentos.record_failure("222")
    assert intentos.cantidad_rastreada() == 1


def test_tracked_cedulas_are_capped_dropping_the_oldest(clock, monkeypatch):
    monkeypatch.setattr(intentos, "MAX_TRACKED", 3)
    for cedula in ["1", "2", "3", "4"]:
        clock["t"] += 1
        intentos.record_failure(cedula)
    assert intentos.cantidad_rastreada() == 3
    assert intentos.failure_count("1") == 0
    assert intentos.failure_count("4") == 1
