"""
Phase 4 "API + Integration" — RBAC matrix across the Motored routers
(sdd/motored-pedidos-cimientos, proposal §7.15, spec "RBAC role
enforcement").

Proves, for a representative sample of endpoints, that each of the 4
original roles (ADMIN/COMPRAS/SUCURSAL/CONSULTA) gets EXACTLY the access
the design specifies -- not just "some 403s happen somewhere":

- maestros READ  -> ADMIN|COMPRAS
- maestros WRITE -> ADMIN|COMPRAS
- carga (bulk upload, both validar and carga) -> ADMIN|COMPRAS
- salud -> ADMIN|COMPRAS
- usuarios -> ADMIN only
- parametros WRITE (POST) -> ADMIN only
- parametros READ (GET vigente) -> ADMIN|COMPRAS

Owner decision 2026-10-05: SUCURSAL and CONSULTA have no screens yet, so
the server denies them every data endpoint (`deps.ROLES_SIN_ACCESO`); the
full sweep lives in `test_roles_sin_acceso.py`.

Uses the REAL `TestClient(app)` and the REAL `get_current_motored_user`
(real token, real path confinement, real `require_roles`); only the user
lookup seam (`get_motored_user_lookup`) and the DB (`FakeAsyncSession`)
are faked.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import get_motored_user_lookup
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
WRITE_ROLES = {"ADMIN", "COMPRAS"}
READ_ROLES = {"ADMIN", "COMPRAS"}
SUCURSAL_ROW = {"nombre": "CALI NORTE", "codigo_co": "E01"}


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(
        settings, "MOTORED_SECRET_KEY", "rbac-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "rbac-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _client_as(role: str, execute_queue=None) -> TestClient:
    user = MotoredUser(user_id=str(uuid.uuid4()), role=role)

    async def _lookup(user_id: str):
        return user

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    # Generous buffer: dependency resolution order (role-check vs. `db`) is
    # an internal FastAPI implementation detail this test must not depend
    # on -- padding with empty results is harmless for cases that are
    # expected to be rejected before touching the DB, and exactly right for
    # cases that do reach a real (empty) read.
    queue = execute_queue or [[]] * 8
    override_motored_db(FakeAsyncSession(execute_queue=queue))
    token = create_motored_token(sub=user.user_id, role=role)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.parametrize("role", ALL_ROLES)
def test_maestros_read_restricted_to_roles_with_screens(role):
    client = _client_as(role)
    response = client.get("/api/motored/maestros/sucursales")
    assert response.status_code == (200 if role in READ_ROLES else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_maestros_write_restricted_to_admin_and_compras(role):
    client = _client_as(role)
    response = client.post(
        "/api/motored/maestros/sucursales", json=SUCURSAL_ROW)
    if role in WRITE_ROLES:
        assert response.status_code in (200, 201), response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_carga_validar_restricted_to_admin_and_compras(role):
    client = _client_as(role)
    response = client.post(
        "/api/motored/maestros/sucursal/carga/validar",
        json={"filas": [{"nombre": "CALI NORTE"}]},
    )
    if role in WRITE_ROLES:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_carga_commit_restricted_to_admin_and_compras(role):
    client = _client_as(role)
    response = client.post(
        "/api/motored/maestros/sucursal/carga",
        json={"filas": [{"nombre": "CALI NORTE"}]},
    )
    if role in WRITE_ROLES:
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_salud_restricted_to_roles_with_screens(role):
    client = _client_as(role)
    response = client.get("/api/motored/maestros/salud")
    assert response.status_code == (200 if role in READ_ROLES else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_usuarios_list_restricted_to_admin_only(role):
    client = _client_as(role)
    response = client.get("/api/motored/usuarios")
    if role == "ADMIN":
        assert response.status_code == 200
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_parametros_write_restricted_to_admin_only(role):
    client = _client_as(role)
    response = client.post(
        "/api/motored/parametros",
        # Desde S4b el POST valida contra el registro de claves.
        json={
            "clave": "dias_ventana_ingresos", "valor": 30,
            "vigente_desde": "2026-01-01",
        },
    )
    if role == "ADMIN":
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_parametros_read_vigente_restricted_to_roles_with_screens(role):
    vigente = ParametroMetodologia(
        id=uuid.uuid4(), clave="cobertura_default", valor=30,
        vigente_desde=date(2026, 1, 1),
    )
    client = _client_as(role, execute_queue=[[], [vigente]])
    response = client.get("/api/motored/parametros/cobertura_default/vigente")
    if role not in READ_ROLES:
        assert response.status_code == 403
        return
    # A real, unambiguous 200 -- not "404 or 200", which would be
    # indistinguishable from a route that plain doesn't exist yet.
    assert response.status_code == 200
    assert response.json()["clave"] == "cobertura_default"
