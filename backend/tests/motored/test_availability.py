"""
Phase 2 "Auth" — availability guards (sdd/motored-pedidos-cimientos, ADR-4).

`require_motored_ready` gates every Motored endpoint before it touches the
database: MOTORED_ENABLED=false or an unsafe secret (ADR-1's fail-closed
guard) must surface as 503 MOTORED_UNAVAILABLE. `get_motored_db_or_503`
gates the actual database access: an unreachable Motored Postgres must
surface as 503 MOTORED_DB_UNAVAILABLE -- and, critically, asc360 itself
must be completely unaffected by a Motored outage (motored-isolation
capability, "Motored outage does not affect asc360").
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _reset_motored_config(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "a-safe-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "a-different-asc360-secret")
    yield


async def test_require_motored_ready_passes_when_enabled_and_secret_is_safe():
    from app.motored.deps import require_motored_ready

    # Must not raise.
    await require_motored_ready()


async def test_require_motored_ready_503_when_disabled(monkeypatch):
    from app.motored.deps import MOTORED_UNAVAILABLE_DETAIL, require_motored_ready

    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)

    with pytest.raises(HTTPException) as exc_info:
        await require_motored_ready()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == MOTORED_UNAVAILABLE_DETAIL == {"code": "MOTORED_UNAVAILABLE"}


async def test_require_motored_ready_503_when_secret_empty(monkeypatch):
    from app.motored.deps import MOTORED_UNAVAILABLE_DETAIL, require_motored_ready

    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "")

    with pytest.raises(HTTPException) as exc_info:
        await require_motored_ready()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == MOTORED_UNAVAILABLE_DETAIL


async def test_require_motored_ready_503_when_secret_equals_asc360_secret(monkeypatch):
    from app.motored.deps import MOTORED_UNAVAILABLE_DETAIL, require_motored_ready

    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "a-different-asc360-secret")

    with pytest.raises(HTTPException) as exc_info:
        await require_motored_ready()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == MOTORED_UNAVAILABLE_DETAIL


async def test_motored_db_unreachable_returns_503_with_exact_error_code(monkeypatch):
    """The Motored path: an unreachable Postgres must surface as a clean
    503 MOTORED_DB_UNAVAILABLE, never an unhandled connection error."""
    from app.motored import database as motored_database
    from app.motored.deps import MOTORED_DB_UNAVAILABLE_DETAIL, get_motored_db_or_503

    # A closed local port -- connection is refused immediately, no DNS/
    # network timeout, keeping this test fast and deterministic.
    monkeypatch.setattr(
        settings, "MOTORED_DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/nonexistent"
    )
    motored_database.get_motored_engine.cache_clear()

    session = await motored_database.get_motored_db().__anext__()
    with pytest.raises(HTTPException) as exc_info:
        await get_motored_db_or_503(db=session)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == MOTORED_DB_UNAVAILABLE_DETAIL == {"code": "MOTORED_DB_UNAVAILABLE"}

    motored_database.get_motored_engine.cache_clear()


def test_asc360_endpoint_unaffected_by_motored_outage(monkeypatch):
    """Spec scenario (motored-isolation): 'Motored DB down, asc360 still
    serves requests' -- an asc360 endpoint unrelated to Motored keeps
    responding 200 even while MOTORED_DATABASE_URL points nowhere."""
    monkeypatch.setattr(
        settings, "MOTORED_DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/nonexistent"
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
