"""
Phase 2 "Auth" — `app.motored.auth`.

Design (sdd/motored-pedidos-cimientos, ADR-1): Motored owns a completely
separate JWT verification path — own secret (`MOTORED_SECRET_KEY`), own
`iss`/`aud` claims (both `"motored"`) — so a token can never cross between
asc360 and Motored, even if an operator accidentally reuses the same
secret string for both (the fail-closed guard below).

These tests exercise `decode_motored_token` directly (pure unit — no
FastAPI, no DB). Cross-system HTTP-level rejection lives in
`test_auth_isolation.py`.
"""
from datetime import timedelta

import pytest
from jose import jwt

from app.config import settings


MOTORED_SECRET = "motored-test-secret-does-not-match-asc360"
ASC360_SECRET = "asc360-test-secret-does-not-match-motored"


@pytest.fixture(autouse=True)
def _motored_secret_configured(monkeypatch):
    """A safe, distinct MOTORED_SECRET_KEY for every test in this module,
    unless a test explicitly overrides it to exercise the fail-closed guard."""
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", MOTORED_SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", ASC360_SECRET)
    yield


def test_create_then_decode_round_trip_succeeds():
    from app.motored.auth import create_motored_token, decode_motored_token

    token = create_motored_token(sub="user-1", role="ADMIN")
    payload = decode_motored_token(token)

    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["role"] == "ADMIN"
    assert payload["iss"] == "motored"
    assert payload["aud"] == "motored"


def test_expired_token_is_rejected():
    from app.motored.auth import create_motored_token, decode_motored_token

    token = create_motored_token(sub="user-1", role="ADMIN", expires_delta=timedelta(seconds=-1))

    assert decode_motored_token(token) is None


def test_wrong_issuer_is_rejected():
    from app.motored.auth import decode_motored_token

    forged = jwt.encode(
        {"sub": "user-1", "role": "ADMIN", "iss": "not-motored", "aud": "motored"},
        MOTORED_SECRET,
        algorithm="HS256",
    )

    assert decode_motored_token(forged) is None


def test_wrong_audience_is_rejected():
    from app.motored.auth import decode_motored_token

    forged = jwt.encode(
        {"sub": "user-1", "role": "ADMIN", "iss": "motored", "aud": "not-motored"},
        MOTORED_SECRET,
        algorithm="HS256",
    )

    assert decode_motored_token(forged) is None


def test_token_signed_with_asc360_secret_is_rejected():
    """The core crossover guard: even a well-formed motored-shaped token
    signed with asc360's secret must fail signature verification."""
    from app.motored.auth import decode_motored_token

    forged = jwt.encode(
        {"sub": "user-1", "role": "ADMIN", "iss": "motored", "aud": "motored"},
        ASC360_SECRET,
        algorithm="HS256",
    )

    assert decode_motored_token(forged) is None


def test_garbage_token_is_rejected():
    from app.motored.auth import decode_motored_token

    assert decode_motored_token("not-a-real-token") is None


def test_create_token_fails_closed_when_secret_is_empty(monkeypatch):
    from app.motored.auth import MotoredAuthUnavailable, create_motored_token

    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "")

    with pytest.raises(MotoredAuthUnavailable):
        create_motored_token(sub="user-1", role="ADMIN")


def test_create_token_fails_closed_when_secret_equals_asc360_secret(monkeypatch):
    """Design ADR-1's defense-in-depth guard: an operator accidentally
    setting MOTORED_SECRET_KEY == SECRET_KEY must not silently work."""
    from app.motored.auth import MotoredAuthUnavailable, create_motored_token

    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", ASC360_SECRET)

    with pytest.raises(MotoredAuthUnavailable):
        create_motored_token(sub="user-1", role="ADMIN")


def test_decode_fails_closed_when_secret_is_empty(monkeypatch):
    """Even a well-formed, correctly-signed-with-empty-secret token must not
    decode when the guard trips -- decode must check the guard BEFORE
    attempting verification, not rely on jose rejecting an empty key."""
    from app.motored.auth import decode_motored_token

    token = jwt.encode(
        {"sub": "user-1", "role": "ADMIN", "iss": "motored", "aud": "motored"},
        MOTORED_SECRET,
        algorithm="HS256",
    )
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "")

    assert decode_motored_token(token) is None


def test_decode_fails_closed_when_secret_equals_asc360_secret(monkeypatch):
    from app.motored.auth import decode_motored_token

    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", ASC360_SECRET)
    token = jwt.encode(
        {"sub": "user-1", "role": "ADMIN", "iss": "motored", "aud": "motored"},
        ASC360_SECRET,
        algorithm="HS256",
    )

    assert decode_motored_token(token) is None
