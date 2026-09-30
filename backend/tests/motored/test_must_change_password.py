"""
Motored T8: forced password change after admin create / admin reset. The flag
is set by those two paths, cleared by the own change, exposed in the login
payload, and enforced server-side in `get_current_motored_user`: while it is
set the user may only call POST /api/motored/auth/password.
"""
import uuid

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import get_current_motored_user, get_motored_user_lookup
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

CODE = {"code": "PASSWORD_CHANGE_REQUIRED"}
ACTUAL = "clave-actual-123"
NUEVA = "clave-nueva-4567"


@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "must-change-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "must-change-test-asc360-secret")
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def _usuario(**kw) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Carla", email="carla@motoredcolombia.com.co",
        hashed_password=get_password_hash(ACTUAL), role="COMPRAS", activo=True, status="approved",
    )
    base.update(kw)
    return Usuario(**base)


# --- flag set / cleared -----------------------------------------------------
def test_admin_create_sets_the_flag():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    body = dict(nombre="N", email="nuevo@x.com", password="clave-valida-77", role="CONSULTA")

    response = TestClient(app).post("/api/motored/usuarios", json=body)

    assert response.status_code == 201, response.text
    assert session.added_of_type(Usuario)[0].must_change_password is True


def test_admin_reset_sets_the_flag():
    objetivo = _usuario()
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    override_motored_db(FakeAsyncSession(execute_queue=[[], [objetivo]]))

    response = TestClient(app).post(
        f"/api/motored/usuarios/{objetivo.id}/password", json={"password": NUEVA}
    )

    assert response.status_code == 200, response.text
    assert objetivo.must_change_password is True


def test_own_change_clears_the_flag_and_returns_it_false():
    u = _usuario(must_change_password=True)
    override_motored_db(FakeAsyncSession(execute_queue=[[], [u], [u]]))
    token = create_motored_token(sub=str(u.id), role="COMPRAS")

    response = TestClient(app).post(
        "/api/motored/auth/password", json={"actual": ACTUAL, "nueva": NUEVA},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert u.must_change_password is False
    assert response.json()["user"]["must_change_password"] is False


@pytest.mark.parametrize("flag", [True, False])
def test_login_payload_carries_the_flag(flag):
    u = _usuario(must_change_password=flag)
    u.sucursales = []
    override_motored_db(FakeAsyncSession(execute_queue=[[], [u]]))

    response = TestClient(app).post(
        "/api/motored/auth/login", json={"email": u.email, "password": ACTUAL}
    )

    assert response.json()["user"]["must_change_password"] is flag


# --- enforcement ------------------------------------------------------------
@pytest.fixture
def probe_routes():
    router = APIRouter()

    @router.get("/api/motored/encuesta/__probe__")
    async def _survey(user: MotoredUser = Depends(get_current_motored_user)):
        return {"role": user.role}

    before = len(app.routes)
    app.include_router(router)
    added = app.routes[before:]
    try:
        yield
    finally:
        for route in added:
            app.routes.remove(route)


def _get(role, path, must_change, queue=None):
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role=role, must_change_password=must_change)

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=queue or [[], [], [], []]))
    token = create_motored_token(sub=str(uuid.uuid4()), role=role)
    with TestClient(app) as client:
        return client.get(path, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.parametrize("role", ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA", "SERVICIO_CLIENTE"])
@pytest.mark.parametrize("path", [
    "/api/motored/maestros/sucursales", "/api/motored/usuarios", "/api/motored/cargas",
])
def test_flagged_user_is_blocked_everywhere_else(role, path):
    response = _get(role, path, must_change=True)

    assert response.status_code == 403, (role, path, response.text)
    assert response.json()["detail"] == CODE


def test_flagged_servicio_cliente_is_blocked_inside_its_own_prefix(probe_routes):
    response = _get("SERVICIO_CLIENTE", "/api/motored/encuesta/__probe__", must_change=True)

    assert response.status_code == 403
    assert response.json()["detail"] == CODE


def test_unflagged_user_is_not_blocked(probe_routes):
    assert _get("COMPRAS", "/api/motored/encuesta/__probe__", must_change=False).status_code == 200


def test_unflagged_servicio_cliente_allow_list_still_works(probe_routes):
    assert _get("SERVICIO_CLIENTE", "/api/motored/encuesta/__probe__", False).status_code == 200
    assert _get("SERVICIO_CLIENTE", "/api/motored/usuarios", False).status_code == 403


@pytest.mark.parametrize("role", ["COMPRAS", "SERVICIO_CLIENTE"])
def test_flagged_user_can_still_change_the_password(role):
    u = _usuario(role=role, must_change_password=True)
    override_motored_db(FakeAsyncSession(execute_queue=[[], [u], [u]]))
    token = create_motored_token(sub=str(u.id), role=role)

    response = TestClient(app).post(
        "/api/motored/auth/password", json={"actual": ACTUAL, "nueva": NUEVA},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
