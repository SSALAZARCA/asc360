"""
Motored satisfaction survey, slice T1: the SERVICIO_CLIENTE role.

Covers the enum value, its Alembic revision (static, mocked `op`, same
approach as `test_migration_lore_bot_schema.py`), the usuarios API accepting
the role, and -- the security-critical part -- the server-side confinement
enforced inside `get_current_motored_user`: many Motored read endpoints have
no role check, so hiding menu entries is not enough.

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
    SERVICIO_CLIENTE_ALLOWED_PREFIXES,
    get_current_motored_user,
    get_motored_user_lookup,
)
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
_MIGRATION_FILES = sorted(_VERSIONS_DIR.glob("*_servicio_cliente_role.py"))


def _load_migration():
    assert len(_MIGRATION_FILES) == 1, "expected exactly one servicio_cliente_role revision"
    spec = importlib.util.spec_from_file_location("servicio_cliente_role_migration", _MIGRATION_FILES[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEnum:
    def test_motored_role_has_servicio_cliente(self):
        assert MotoredRole("SERVICIO_CLIENTE") is MotoredRole.SERVICIO_CLIENTE
        assert MotoredRole.SERVICIO_CLIENTE.value == "SERVICIO_CLIENTE"


class TestMigration:
    def test_chains_onto_current_head(self):
        assert _load_migration().down_revision == "a3f7c91d2e58"

    def test_is_part_of_the_linear_chain(self):
        revisions, downs = set(), set()
        for path in _VERSIONS_DIR.glob("*.py"):
            spec = importlib.util.spec_from_file_location(f"m_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            revisions.add(module.revision)
            downs.add(module.down_revision)
        # Head-ness is asserted by the newest revision's own test; here we only
        # require this revision to stay in the chain (referenced as a parent).
        assert _load_migration().revision in downs

    def test_upgrade_adds_value_idempotently_inside_autocommit_block(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.upgrade()

        op_mock.get_context.return_value.autocommit_block.assert_called_once()
        op_mock.execute.assert_called_once()
        (executed,), _ = op_mock.execute.call_args
        assert "ALTER TYPE motored_role ADD VALUE IF NOT EXISTS 'SERVICIO_CLIENTE'" in str(executed)

    def test_downgrade_is_a_documented_no_op(self):
        migration = _load_migration()
        with patch.object(migration, "op") as op_mock:
            migration.downgrade()
        op_mock.execute.assert_not_called()
        op_mock.get_context.assert_not_called()


class TestAllowList:
    def test_includes_survey_and_case_prefixes(self):
        assert "/api/motored/encuesta" in SERVICIO_CLIENTE_ALLOWED_PREFIXES
        assert "/api/motored/detractores" in SERVICIO_CLIENTE_ALLOWED_PREFIXES

    def test_includes_auth_prefix(self):
        assert "/api/motored/auth" in SERVICIO_CLIENTE_ALLOWED_PREFIXES

    def test_does_not_include_anything_else(self):
        for forbidden in ("/api/motored/usuarios", "/api/motored/maestros", "/api/motored/cargas"):
            assert forbidden not in SERVICIO_CLIENTE_ALLOWED_PREFIXES


# ---------------------------------------------------------------------------
# Confinement through the real get_current_motored_user
# ---------------------------------------------------------------------------

SECRET = "servicio-cliente-test-secret"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", "servicio-cliente-asc360-secret")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def probe_routes():
    """Throwaway routes that depend on the real `get_current_motored_user`,
    one inside an allowed prefix and one outside, standing in for the
    survey/case routers that later slices add."""
    router = APIRouter()

    @router.get("/api/motored/encuesta/__probe__")
    async def _allowed(user: MotoredUser = Depends(get_current_motored_user)):
        return {"role": user.role}

    @router.get("/api/motored/encuesta-otra/__probe__")
    async def _lookalike(user: MotoredUser = Depends(get_current_motored_user)):
        return {"role": user.role}

    @router.get("/api/motored/detractores/__probe__/ping")
    async def _allowed_cases(user: MotoredUser = Depends(get_current_motored_user)):
        return {"role": user.role}

    before = len(app.routes)
    app.include_router(router)
    added = app.routes[before:]
    try:
        yield
    finally:
        for route in added:
            app.routes.remove(route)


def _request(role: str, path: str, queue=None):
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role=role)

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=queue or [[], [], [], []]))
    token = create_motored_token(sub=str(uuid.uuid4()), role=role)
    with TestClient(app) as client:
        return client.get(path, headers={"Authorization": f"Bearer {token}"})


DENIED_PATHS = [
    "/api/motored/maestros/sucursales",
    "/api/motored/maestros/salud",
    "/api/motored/maestros/referencias/buscar?q=abc",
    "/api/motored/cargas",
    "/api/motored/parametros/dias_seguridad/vigente",
    "/api/motored/usuarios",
    "/api/motored/demanda-perdida/cobertura-bot",
]


@pytest.mark.parametrize("path", DENIED_PATHS)
def test_servicio_cliente_is_forbidden_outside_the_allow_list(path):
    response = _request("SERVICIO_CLIENTE", path)

    assert response.status_code == 403, (path, response.text)


def test_servicio_cliente_reaches_encuesta_and_detractores_prefixes(probe_routes):
    for path in ("/api/motored/encuesta/__probe__", "/api/motored/detractores/__probe__/ping"):
        response = _request("SERVICIO_CLIENTE", path)
        assert response.status_code == 200, (path, response.text)
        assert response.json() == {"role": "SERVICIO_CLIENTE"}


def test_prefix_match_respects_segment_boundaries(probe_routes):
    response = _request("SERVICIO_CLIENTE", "/api/motored/encuesta-otra/__probe__")

    assert response.status_code == 403


def test_servicio_cliente_is_not_blocked_on_login():
    """Login is not behind `get_current_motored_user`; an inactive/unknown
    account still gets the generic 401, never a 403 from the confinement."""
    override_motored_db(FakeAsyncSession(execute_queue=[[], []]))
    with TestClient(app) as client:
        response = client.post(
            "/api/motored/auth/login", json={"email": "sc@x.com", "password": "12345678"}
        )
    assert response.status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "CONSULTA"])
def test_other_roles_are_not_confined(role, probe_routes):
    # An endpoint with no role check: both roles must still get through.
    response = _request(role, "/api/motored/parametros/dias_seguridad/vigente")
    assert response.status_code == 404  # reached the handler (no vigente version)

    response = _request(role, "/api/motored/encuesta/__probe__")
    assert response.status_code == 200


def test_admin_can_still_list_usuarios():
    response = _request("ADMIN", "/api/motored/usuarios", queue=[[], [], []])

    assert response.status_code == 200


def test_consulta_is_still_forbidden_by_its_own_role_check_on_usuarios():
    assert _request("CONSULTA", "/api/motored/usuarios").status_code == 403


# ---------------------------------------------------------------------------
# usuarios API accepts the new role
# ---------------------------------------------------------------------------

def test_admin_can_create_a_servicio_cliente_user_with_web_credentials():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    body = dict(
        nombre="Agente SC", email="sc@x.com", password="clave-valida-77", role="SERVICIO_CLIENTE"
    )
    response = TestClient(app).post("/api/motored/usuarios", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "SERVICIO_CLIENTE"
    created = session.added_of_type(Usuario)
    assert created and created[0].role is MotoredRole.SERVICIO_CLIENTE
    assert created[0].email == "sc@x.com" and created[0].hashed_password
