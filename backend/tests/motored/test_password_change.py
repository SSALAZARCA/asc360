"""
Motored T3: change-own-password + session invalidation.

Covers token `iat`, rejection of tokens issued before `password_changed_at`,
the admin reset stamping that column, and `POST /api/motored/auth/password`.
Uses the real `get_current_motored_user` (only the DB seam is faked) so the
token checks and the SERVICIO_CLIENTE confinement run for real.
"""
import calendar
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash, verify_password
from app.main import app
from app.motored.auth import ALGORITHM, AUDIENCE, ISSUER, create_motored_token
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

URL = "/api/motored/auth/password"
SECRET = "password-change-test-motored-secret"
ACTUAL = "clave-actual-123"
NUEVA = "clave-nueva-456"


@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", "password-change-test-asc360")
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def _usuario(role="COMPRAS", **kw) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Carla", email="carla@motoredcolombia.com.co",
        hashed_password=get_password_hash(ACTUAL), role=role, activo=True, status="approved",
    )
    base.update(kw)
    return Usuario(**base)


def _token_for(usuario, **kw) -> str:
    return create_motored_token(sub=str(usuario.id), role=usuario.role, **kw)


def _session(usuario, changed_at=None):
    """Queue: SELECT 1 probe, lookup row (auth), then the endpoint's own fetch."""
    usuario.password_changed_at = changed_at
    return FakeAsyncSession(execute_queue=[[], [usuario], [usuario], [usuario]])


def _post(usuario, body, token=None, changed_at=None):
    session = _session(usuario, changed_at)
    override_motored_db(session)
    headers = {"Authorization": f"Bearer {token or _token_for(usuario)}"}
    return TestClient(app).post(URL, json=body, headers=headers), session


def test_token_carries_iat_in_seconds():
    claims = jwt.get_unverified_claims(create_motored_token(sub="u", role="ADMIN"))
    assert isinstance(claims["iat"], int)
    assert abs(claims["iat"] - _utc_now_ts()) <= 5


def _utc_now_ts() -> int:
    return calendar.timegm(datetime.datetime.utcnow().utctimetuple())


def _encode(sub, iat=None):
    claims = {"sub": sub, "role": "COMPRAS", "iss": ISSUER, "aud": AUDIENCE,
              "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
    if iat is not None:
        claims["iat"] = iat
    return jwt.encode(claims, SECRET, algorithm=ALGORITHM)


def _get_me(usuario, token, changed_at):
    usuario.password_changed_at = changed_at
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))
    return TestClient(app).get("/api/motored/auth/me", headers={"Authorization": f"Bearer {token}"})


def _auth_status(usuario, token, changed_at):
    return _get_me(usuario, token, changed_at).status_code


@pytest.fixture
def probe_route():
    from fastapi import APIRouter, Depends
    from app.motored.deps import get_current_motored_user
    router = APIRouter()

    @router.get("/api/motored/auth/me")
    async def _me(user: MotoredUser = Depends(get_current_motored_user)):
        return {"id": user.user_id}

    n = len(app.router.routes)
    app.include_router(router)
    yield
    del app.router.routes[n:]


def test_token_older_than_password_change_is_rejected(probe_route):
    u = _usuario()
    changed = datetime.datetime.utcnow()
    old = _encode(str(u.id), iat=_utc_now_ts() - 120)
    assert _auth_status(u, old, changed) == 401


def test_token_issued_after_password_change_is_accepted(probe_route):
    u = _usuario()
    changed = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    assert _auth_status(u, _token_for(u), changed) == 200


def test_token_issued_in_same_second_as_change_is_accepted(probe_route):
    u = _usuario()
    changed = datetime.datetime.utcnow()
    assert _auth_status(u, _token_for(u), changed) == 200


def test_token_without_iat_is_accepted_when_never_changed(probe_route):
    u = _usuario()
    assert _auth_status(u, _encode(str(u.id)), None) == 200


def test_token_without_iat_is_rejected_when_password_was_changed(probe_route):
    u = _usuario()
    assert _auth_status(u, _encode(str(u.id)), datetime.datetime.utcnow()) == 401


def test_admin_reset_stamps_password_changed_at():
    admin = _usuario(role="ADMIN")
    objetivo = _usuario(email="otro@motoredcolombia.com.co")
    override_motored_user(MotoredUser(user_id=str(admin.id), role="ADMIN"))
    override_motored_db(FakeAsyncSession(execute_queue=[[], [objetivo]]))
    before = datetime.datetime.utcnow() - datetime.timedelta(seconds=1)

    r = TestClient(app).post(f"/api/motored/usuarios/{objetivo.id}/password", json={"password": NUEVA})

    assert r.status_code == 200, r.text
    assert objetivo.password_changed_at >= before


def test_change_success_returns_fresh_token_and_stores_hash():
    u = _usuario()
    r, session = _post(u, {"actual": ACTUAL, "nueva": NUEVA})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == str(u.id) and body["user"]["role"] == "COMPRAS"
    claims = jwt.decode(body["access_token"], SECRET, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    assert claims["sub"] == str(u.id)
    assert verify_password(NUEVA, u.hashed_password)
    assert u.password_changed_at is not None
    assert session.committed is True
    assert NUEVA not in r.text and ACTUAL not in r.text


def test_fresh_token_passes_and_old_token_fails_after_change(probe_route):
    u = _usuario()
    old = _encode(str(u.id), iat=_utc_now_ts() - 30)
    r, _ = _post(u, {"actual": ACTUAL, "nueva": NUEVA})
    fresh = r.json()["access_token"]
    assert _auth_status(u, fresh, u.password_changed_at) == 200
    assert _auth_status(u, old, u.password_changed_at) == 401


def test_wrong_current_password_is_rejected():
    u = _usuario()
    r, session = _post(u, {"actual": "otra-clave-999", "nueva": NUEVA})
    assert r.status_code == 400
    assert r.json()["detail"] == "La contraseña actual no es correcta."
    assert session.committed is False and u.password_changed_at is None


def test_same_password_is_rejected():
    u = _usuario()
    r, _ = _post(u, {"actual": ACTUAL, "nueva": ACTUAL})
    assert r.status_code == 422
    assert r.json()["detail"] == "La nueva contraseña debe ser distinta de la actual."


@pytest.mark.parametrize("nueva,fragment", [("corta", "al menos 10"), ("a" * 73, "72")])
def test_new_password_length_rules(nueva, fragment):
    u = _usuario()
    r, _ = _post(u, {"actual": ACTUAL, "nueva": nueva})
    assert r.status_code == 422
    assert fragment in r.json()["detail"]
    assert nueva not in r.text


def test_servicio_cliente_can_change_own_password():
    u = _usuario(role="SERVICIO_CLIENTE")
    r, _ = _post(u, {"actual": ACTUAL, "nueva": NUEVA})
    assert r.status_code == 200, r.text


def test_requires_authentication():
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    r = TestClient(app).post(URL, json={"actual": ACTUAL, "nueva": NUEVA})
    assert r.status_code == 401


def test_change_is_rate_limited():
    u = _usuario()
    codes = []
    for _ in range(7):
        r, _ = _post(u, {"actual": "mala-clave-000", "nueva": NUEVA})
        codes.append(r.status_code)
    assert codes[:5] == [400] * 5
    assert 429 in codes[5:]


def test_change_is_audited_with_actor_self_and_no_secrets():
    u = _usuario()
    _, session = _post(u, {"actual": ACTUAL, "nueva": NUEVA})
    filas = [a for a in session.added if a.entidad == "usuario"]
    assert len(filas) == 1
    assert filas[0].campo == "password" and filas[0].entidad_id == u.id
    assert filas[0].usuario_id == u.id
    assert filas[0].valor_anterior is None and filas[0].valor_nuevo is None
