"""
Phase 4 "API + Integration" — RBAC matrix across the 6 Motored routers
(sdd/motored-pedidos-cimientos, proposal §7.15, spec "RBAC role enforcement").

Proves, for a representative sample of endpoints, that each of the 4 roles
(ADMIN/COMPRAS/SUCURSAL/CONSULTA) gets EXACTLY the access the design/
proposal specifies -- not just "some 403s happen somewhere":

- maestros READ  -> all 4 roles
- maestros WRITE -> ADMIN|COMPRAS only
- carga (bulk upload, both validar and carga) -> ADMIN|COMPRAS only
- salud -> all 4 roles (read-only capability, no write exists)
- usuarios -> ADMIN only
- parametros WRITE (POST) -> ADMIN only
- parametros READ (GET vigente) -> all 4 roles

Uses the REAL `TestClient(app)` with `get_current_motored_user` overridden
to a fixed role per case (`override_motored_user`) and `get_motored_db`
overridden to a `FakeAsyncSession` (`override_motored_db`) -- real routing,
real `require_roles` dependency, real router wiring; only the DB and the
already-independently-tested user lookup (`test_usuario_lookup.py`) are
faked.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
WRITE_ROLES = {"ADMIN", "COMPRAS"}


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "rbac-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "rbac-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _client_as(role: str, execute_queue=None) -> TestClient:
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    # Generous buffer: dependency resolution order (role-check vs. `db`) is
    # an internal FastAPI implementation detail this test must not depend
    # on -- padding with empty results is harmless for cases that are
    # expected to be rejected before touching the DB, and exactly right for
    # cases that do reach a real (empty) read.
    override_motored_db(FakeAsyncSession(execute_queue=execute_queue or [[]] * 8))
    return TestClient(app)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_maestros_read_allowed_for_every_role(role):
    client = _client_as(role)
    response = client.get("/api/motored/maestros/sucursales")
    assert response.status_code == 200


@pytest.mark.parametrize("role", ALL_ROLES)
def test_maestros_write_restricted_to_admin_and_compras(role):
    client = _client_as(role)
    response = client.post("/api/motored/maestros/sucursales", json={"nombre": "CALI NORTE"})
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
def test_salud_allowed_for_every_role(role):
    client = _client_as(role)
    response = client.get("/api/motored/maestros/salud")
    assert response.status_code == 200


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
        json={"clave": "cobertura_default", "valor": 30, "vigente_desde": "2026-01-01"},
    )
    if role == "ADMIN":
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_parametros_read_vigente_allowed_for_every_role(role):
    from datetime import date

    from app.motored.models.parametro_metodologia import ParametroMetodologia

    vigente = ParametroMetodologia(
        id=uuid.uuid4(), clave="cobertura_default", valor=30, vigente_desde=date(2026, 1, 1)
    )
    client = _client_as(role, execute_queue=[[], [vigente]])
    response = client.get("/api/motored/parametros/cobertura_default/vigente")
    # A real, unambiguous 200 -- not "404 or 200", which would be
    # indistinguishable from a route that plain doesn't exist yet.
    assert response.status_code == 200
    assert response.json()["clave"] == "cobertura_default"
