"""
Motored budgets/management, task T1: the GERENCIA role.

Covers the enum value, its Alembic revision (static, mocked `op`), the usuarios
API accepting the role and the server-side confinement enforced inside
`get_current_motored_user`: GERENCIA reaches only auth, the budgets API
(`/presupuestos`) and the advisor dashboard (`/tablero-asesores`).

Confinement tests run through the REAL `get_current_motored_user` (only the
user-lookup seam is swapped) so the path allow-list is actually exercised.
"""
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import (
    GERENCIA_ALLOWED_PREFIXES,
    get_current_motored_user,
    get_motored_user_lookup,
)
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
_MIGRATION_FILES = sorted(_VERSIONS_DIR.glob("*_gerencia_role.py"))


def _load_migration():
    assert len(_MIGRATION_FILES) == 1, "expected exactly one gerencia_role revision"
    spec = importlib.util.spec_from_file_location("gerencia_role_migration", _MIGRATION_FILES[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEnum:
    def test_motored_role_has_gerencia(self):
        assert MotoredRole("GERENCIA") is MotoredRole.GERENCIA
        assert MotoredRole.GERENCIA.value == "GERENCIA"


class TestMigration:
    def test_chains_onto_previous_head(self):
        assert _load_migration().down_revision == "b5d91e3a7c42"

    def test_upgrade_adds_value_idempotently_inside_autocommit_block(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        op_mock.get_context.return_value.autocommit_block.assert_called_once()
        op_mock.execute.assert_called_once()
        (executed,), _ = op_mock.execute.call_args
        assert "ALTER TYPE motored_role ADD VALUE IF NOT EXISTS 'GERENCIA'" in str(executed)

    def test_downgrade_is_a_documented_no_op(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()
        op_mock.execute.assert_not_called()
        op_mock.get_context.assert_not_called()


class TestAllowList:
    def test_is_exactly_auth_presupuestos_and_tablero(self):
        assert set(GERENCIA_ALLOWED_PREFIXES) == {
            "/api/motored/auth",
            "/api/motored/presupuestos",
            "/api/motored/tablero-asesores",
        }


SECRET = "gerencia-test-secret"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", "gerencia-asc360-secret")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def probe_routes():
    """Throwaway routes on the real `get_current_motored_user`, standing in for
    the budgets router that a later task adds."""
    router = APIRouter()

    @router.get("/api/motored/presupuestos/__probe__")
    async def _allowed(user: MotoredUser = Depends(get_current_motored_user)):
        return {"role": user.role}

    @router.get("/api/motored/presupuestos-otra/__probe__")
    async def _lookalike(user: MotoredUser = Depends(get_current_motored_user)):
        return {"role": user.role}

    before = len(app.routes)
    app.include_router(router)
    added = app.routes[before:]
    try:
        yield
    finally:
        for route in added:
            app.routes.remove(route)


def _request(role: str, path: str, method: str = "GET", queue=None):
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role=role)

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=queue or [[], [], [], []]))
    token = create_motored_token(sub=str(uuid.uuid4()), role=role)
    with TestClient(app) as client:
        return client.request(method, path, headers={"Authorization": f"Bearer {token}"})


DENIED_PATHS = [
    "/api/motored/maestros/sucursales",
    "/api/motored/maestros/salud",
    "/api/motored/maestros/referencias/buscar?q=abc",
    "/api/motored/cargas",
    "/api/motored/parametros/dias_seguridad/vigente",
    "/api/motored/usuarios",
    "/api/motored/corridas",
    "/api/motored/usuarios/me/telegram",
    "/api/motored/encuesta/cargas/plantilla",
    "/api/motored/detractores",
    "/api/motored/demanda-perdida/cobertura-bot",
]


@pytest.mark.parametrize("path", DENIED_PATHS)
def test_gerencia_is_forbidden_outside_the_allow_list(path):
    response = _request("GERENCIA", path)

    assert response.status_code == 403, (path, response.text)


def test_gerencia_reaches_the_presupuestos_prefix(probe_routes):
    response = _request("GERENCIA", "/api/motored/presupuestos/__probe__")

    assert response.status_code == 200, response.text
    assert response.json() == {"role": "GERENCIA"}


def test_prefix_match_respects_segment_boundaries(probe_routes):
    assert _request("GERENCIA", "/api/motored/presupuestos-otra/__probe__").status_code == 403


def test_gerencia_can_read_the_tablero(monkeypatch):
    from app.motored.services import tablero_asesores_consultas as consultas

    async def _fake(db, desde, hasta, modo_hmcl):
        return {"filas": [], "venta_sin_linea": 0.0}

    monkeypatch.setattr(consultas, "calcular_tablero", _fake)

    response = _request("GERENCIA", "/api/motored/tablero-asesores?desde=2026-01&hasta=2026-01&hmcl=incluir")

    assert response.status_code == 200, response.text


def test_tablero_still_rejects_roles_outside_its_list():
    assert _request("CONSULTA", "/api/motored/tablero-asesores?desde=2026-01&hasta=2026-01&hmcl=incluir").status_code == 403


def test_auth_prefix_stays_reachable_for_password_change():
    """Password change after a forced reset must not hit the confinement 403."""
    response = _request("GERENCIA", "/api/motored/auth/password", method="POST")

    assert response.status_code != 403, response.text


def test_gerencia_is_not_blocked_on_login():
    override_motored_db(FakeAsyncSession(execute_queue=[[], []]))
    with TestClient(app) as client:
        response = client.post(
            "/api/motored/auth/login", json={"email": "g@x.com", "password": "12345678"}
        )
    assert response.status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "COMPRAS"])
def test_other_roles_are_not_confined(role):
    response = _request(role, "/api/motored/parametros/dias_seguridad/vigente")
    assert response.status_code == 404  # reached the handler (no vigente version)


def test_admin_can_create_a_gerencia_user_with_web_credentials():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    body = dict(nombre="Gerente", email="g@x.com", password="clave-valida-77", role="GERENCIA")
    response = TestClient(app).post("/api/motored/usuarios", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "GERENCIA"
    created = session.added_of_type(Usuario)
    assert created and created[0].role is MotoredRole.GERENCIA
    assert created[0].email == "g@x.com" and created[0].hashed_password


@pytest.mark.parametrize("pestana", ["ventas", "tiendas", "asesores", "opciones"])
def test_gerencia_reaches_the_kpis_endpoints_through_the_real_confinement(monkeypatch, pestana):
    from app.motored.services import tablero_asesores as t
    from app.motored.services import tablero_asesores_consultas as consultas
    from app.motored.services import tablero_kpis as kpis

    async def _filtro(db, meses, modo_hmcl, sucursal_ids=None):
        return t.filtro_de_meses(t.validar_meses(meses), modo_hmcl, sucursal_ids)

    async def _calculo(db, filtro=None):
        return {"ok": True}

    monkeypatch.setattr(consultas, "cargar_filtro", _filtro)
    for nombre in ("calcular_kpis_ventas", "calcular_kpis_tiendas", "calcular_kpis_asesores", "calcular_opciones"):
        monkeypatch.setattr(kpis, nombre, _calculo)

    path = f"/api/motored/tablero-asesores/kpis/{pestana}?meses=2026-01"

    assert _request("GERENCIA", path).status_code == 200
    assert _request("COMPRAS", path).status_code == 200
    assert _request("CONSULTA", path).status_code == 403
