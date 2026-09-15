"""
Phase 2 "Auth" — cross-system token rejection (sdd/motored-pedidos-cimientos,
ADR-1, motored-isolation capability).

Uses the REAL `TestClient(app)` around the real production `app.main.app`
object -- deliberately WITHOUT any `app.dependency_overrides` -- to prove
the actual, wired authentication paths of both systems reject each other's
tokens. A dependency-override-based test could pass even if the real
`decode_access_token`/`decode_motored_token` wiring were broken; this test
exercises the genuine code path.

No Motored HTTP router exists yet (that's Phase 4), so direction 2
(asc360 token -> Motored endpoint) is exercised via a minimal, throwaway
route added directly onto the real `app` object for the duration of this
module only (`app.include_router`/`app.routes.remove`, not a
`dependency_override`): it genuinely calls the real
`get_current_motored_user` dependency through a real HTTP request, and is
removed again after the module's tests run so it never leaks into any
other test module's view of `app.routes`.
"""
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.core.security import create_access_token
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import MotoredUser, get_current_motored_user

MOTORED_SECRET = "motored-isolation-test-secret"
ASC360_SECRET = "asc360-isolation-test-secret"

# An existing, already-protected, real asc360 endpoint (requires
# `get_current_user`) -- used unmodified for direction 1.
ASC360_PROTECTED_URL = "/api/v1/vehicle-models"


@pytest.fixture(autouse=True)
def _distinct_secrets(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", MOTORED_SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", ASC360_SECRET)
    yield


async def _fake_motored_user_lookup(user_id: str):
    return MotoredUser(user_id=user_id, role="ADMIN")


@pytest.fixture()
def motored_test_route():
    """Mounts ONE throwaway route on the real `app` object that genuinely
    depends on `get_current_motored_user` -- not a dependency override of
    that function itself, just a minimal real consumer of it, since no
    production Motored route exists until Phase 4. Provides only the
    swappable user-lookup seam (Phase 3 wires the real DB query), which is
    exactly what that seam is for.
    """
    router = APIRouter()

    @router.get("/__test_motored_protected__")
    async def _protected(user: MotoredUser = Depends(get_current_motored_user)):
        return {"user_id": user.user_id, "role": user.role}

    app.include_router(router)
    from app.motored.deps import get_motored_user_lookup

    app.dependency_overrides[get_motored_user_lookup] = lambda: _fake_motored_user_lookup

    added_route = app.routes[-1]
    try:
        yield "/__test_motored_protected__"
    finally:
        app.routes.remove(added_route)
        app.dependency_overrides.pop(get_motored_user_lookup, None)


def test_motored_token_rejected_by_asc360_endpoint():
    """Direction 1: a Motored-issued token must not authenticate an asc360
    request. Uses a real, already-existing, already-protected asc360
    endpoint -- zero new routes needed for this direction."""
    token = create_motored_token(sub="motored-user-1", role="ADMIN")

    with TestClient(app) as client:
        response = client.get(
            ASC360_PROTECTED_URL, headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401


def test_asc360_token_rejected_by_motored_endpoint(motored_test_route):
    """Direction 2: an asc360-issued token must not authenticate a Motored
    request."""
    token = create_access_token({"sub": "asc360-user-1", "role": "superadmin"})

    with TestClient(app) as client:
        response = client.get(
            motored_test_route, headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401


def test_motored_token_with_forged_issuer_rejected_by_motored_endpoint(motored_test_route):
    """Defense-in-depth: even a token correctly signed with
    `MOTORED_SECRET_KEY` but with a hand-forged wrong `iss` must be
    rejected -- this is specifically what `iss`/`aud` exist to catch."""
    forged = jwt.encode(
        {"sub": "motored-user-1", "role": "ADMIN", "iss": "not-motored", "aud": "motored"},
        MOTORED_SECRET,
        algorithm="HS256",
    )

    with TestClient(app) as client:
        response = client.get(
            motored_test_route, headers={"Authorization": f"Bearer {forged}"}
        )

    assert response.status_code == 401


def test_motored_token_with_forged_audience_rejected_by_motored_endpoint(motored_test_route):
    forged = jwt.encode(
        {"sub": "motored-user-1", "role": "ADMIN", "iss": "motored", "aud": "not-motored"},
        MOTORED_SECRET,
        algorithm="HS256",
    )

    with TestClient(app) as client:
        response = client.get(
            motored_test_route, headers={"Authorization": f"Bearer {forged}"}
        )

    assert response.status_code == 401


def test_valid_motored_token_accepted_by_motored_endpoint(motored_test_route):
    """Sanity control: the real dependency DOES accept a genuine Motored
    token via the swappable lookup seam -- proves the 401s above are about
    rejection logic, not a broken route."""
    token = create_motored_token(sub="motored-user-1", role="ADMIN")

    with TestClient(app) as client:
        response = client.get(
            motored_test_route, headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": "motored-user-1", "role": "ADMIN"}
