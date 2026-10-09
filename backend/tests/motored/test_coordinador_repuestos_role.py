"""
The COORDINADOR_REPUESTOS role (feature motored-coordinador-repuestos, C1/C2).

Covers the enum value, its Alembic revision (static, mocked `op`), the
usuarios API accepting the role, and the server-side confinement enforced
inside `get_current_motored_user`: the role reaches only auth, the KPI's
(`/tablero-asesores/kpis`, read-only), the "Gestión repuestos" prefix
(`/gestion-repuestos`) and, as a count leader (owner decision
2026-10-09), the inventory counts prefix (`/conteos`). Every other
guarded route answers 403, so a new endpoint is denied by default.

The "Gestión repuestos" prefix is a rule only (no endpoint yet): throwaway
probe routes on the real dependency stand in for it.
"""
import importlib.util
import re
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Depends
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import (
    COORDINADOR_REPUESTOS_ALLOWED_PREFIXES,
    CONTEOS_PREFIX,
    COORDINADOR_REPUESTOS_ROLE,
    GESTION_REPUESTOS_PREFIX,
    _CONFINED_ROLE_PREFIXES,
    get_current_motored_user,
    get_motored_user_lookup,
)
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

ROLE = "COORDINADOR_REPUESTOS"
PREFIX = "/api/motored"
KPIS = PREFIX + "/tablero-asesores/kpis"
GESTION = PREFIX + "/gestion-repuestos"
CONTEOS = PREFIX + "/conteos"
SECRET = "coordinador-test-secret"

_VERSIONS_DIR = (
    Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
)
_MIGRATION_FILES = sorted(_VERSIONS_DIR.glob("*_coordinador_repuestos*.py"))


def _load_migration():
    assert len(_MIGRATION_FILES) == 1
    spec = importlib.util.spec_from_file_location(
        "coordinador_repuestos_migration", _MIGRATION_FILES[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", SECRET)
    monkeypatch.setattr(settings, "SECRET_KEY", "coordinador-asc360")
    yield
    app.dependency_overrides.clear()


def _request(role, path, method="GET"):
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role=role)

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))
    token = create_motored_token(sub=str(uuid.uuid4()), role=role)
    with TestClient(app) as client:
        return client.request(
            method, path, headers={"Authorization": f"Bearer {token}"})


def test_role_constant_and_enum_value():
    assert COORDINADOR_REPUESTOS_ROLE == ROLE
    assert MotoredRole(ROLE) is MotoredRole.COORDINADOR_REPUESTOS


def test_migration_chains_onto_the_previous_head():
    assert _load_migration().down_revision == "c7e1a4b92d36"


def test_migration_adds_the_value_inside_an_autocommit_block():
    migration = _load_migration()
    with patch.object(migration, "op") as op_mock:
        migration.upgrade()

    op_mock.get_context.return_value.autocommit_block.assert_called_once()
    (executed,), _ = op_mock.execute.call_args
    assert (
        "ALTER TYPE motored_role ADD VALUE IF NOT EXISTS "
        "'COORDINADOR_REPUESTOS'"
    ) in str(executed)


def test_migration_downgrade_is_a_documented_no_op():
    migration = _load_migration()
    with patch.object(migration, "op") as op_mock:
        migration.downgrade()

    op_mock.execute.assert_not_called()


def test_allow_list_is_exactly_auth_kpis_and_gestion_repuestos():
    assert GESTION_REPUESTOS_PREFIX == GESTION
    assert set(COORDINADOR_REPUESTOS_ALLOWED_PREFIXES) == {
        PREFIX + "/auth", KPIS, GESTION,
    }


@pytest.mark.parametrize(
    "pestana", ["ventas", "tiendas", "asesores", "opciones"])
def test_role_reads_the_kpis(monkeypatch, pestana):
    from app.motored.services import tablero_asesores as t
    from app.motored.services import tablero_asesores_consultas as consultas
    from app.motored.services import tablero_kpis as kpis

    async def _filtro(db, meses, modo_hmcl, sucursal_ids=None):
        return t.filtro_de_meses(
            t.validar_meses(meses), modo_hmcl, sucursal_ids)

    async def _calculo(db, filtro=None):
        return {"ok": True}

    monkeypatch.setattr(consultas, "cargar_filtro", _filtro)
    for nombre in ("calcular_kpis_ventas", "calcular_kpis_tiendas",
                   "calcular_kpis_asesores", "calcular_opciones"):
        monkeypatch.setattr(kpis, nombre, _calculo)

    response = _request(ROLE, f"{KPIS}/{pestana}?meses=2026-01")

    assert response.status_code == 200, response.text


def test_role_cannot_rebuild_the_kpis():
    assert _request(ROLE, KPIS + "/recalcular", "POST").status_code == 403


DENIED_PATHS = [
    "/api/motored/maestros/sucursales",
    "/api/motored/maestros/salud",
    "/api/motored/maestros/referencias/buscar?q=abc",
    "/api/motored/cargas",
    "/api/motored/corridas",
    "/api/motored/parametros/configuracion",
    "/api/motored/parametros/dias_seguridad/vigente",
    "/api/motored/usuarios",
    "/api/motored/usuarios/me/telegram",
    "/api/motored/encuesta/cargas/plantilla",
    "/api/motored/detractores",
    "/api/motored/demanda-perdida/cobertura-bot",
    "/api/motored/tablero-asesores?desde=2026-01&hasta=2026-01",
    "/api/motored/presupuestos/tiendas",
    "/api/motored/vendedores",
    "/api/motored/clientes-tecnired",
    "/api/motored/avisos-antiguedad",
    "/api/motored/inicio",
]


@pytest.mark.parametrize("path", DENIED_PATHS)
def test_role_is_forbidden_outside_its_allow_list(path):
    response = _request(ROLE, path)

    assert response.status_code == 403, (path, response.text)


def _calls(dependant) -> set:
    calls, pending = set(), [dependant]
    while pending:
        current = pending.pop()
        calls.add(current.call)
        pending.extend(current.dependencies)
    return calls


def _guarded_routes_outside_allow_list():
    allowed = (PREFIX + "/auth/", KPIS + "/", KPIS + "?",
               PREFIX + "/gestion-repuestos/", CONTEOS + "/")
    for ctx in iter_route_contexts(app.routes):
        path = ctx.path or ""
        if (not path.startswith(PREFIX + "/") or path == CONTEOS
                or path.startswith(allowed)):
            continue
        if get_current_motored_user in _calls(ctx.original_route.dependant):
            for method in sorted(ctx.methods):
                yield method, path


def test_every_other_guarded_route_is_denied_by_default():
    leaks = []
    for method, path in _guarded_routes_outside_allow_list():
        filled = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
        response = _request(ROLE, filled, method)
        if response.status_code != 403:
            leaks.append((method, path, response.status_code))

    assert leaks == []


@pytest.fixture
def probe_routes():
    router = APIRouter()

    @router.get(GESTION + "/__probe__")
    async def _allowed(
        user: MotoredUser = Depends(get_current_motored_user),
    ):
        return {"role": user.role}

    @router.get(GESTION + "-otra/__probe__")
    async def _lookalike(
        user: MotoredUser = Depends(get_current_motored_user),
    ):
        return {"role": user.role}

    before = len(app.routes)
    app.include_router(router)
    added = app.routes[before:]
    try:
        yield
    finally:
        for route in added:
            app.routes.remove(route)


@pytest.mark.parametrize(
    "role", ["ADMIN", "COMPRAS", "GERENCIA", "COORDINADOR_REPUESTOS"])
def test_gestion_repuestos_prefix_lets_the_four_roles_through(
        probe_routes, role):
    response = _request(role, GESTION + "/__probe__")

    assert response.status_code == 200, response.text
    assert response.json() == {"role": role}


@pytest.mark.parametrize(
    "role", ["SERVICIO_CLIENTE", "SUCURSAL", "CONSULTA"])
def test_gestion_repuestos_prefix_denies_the_other_roles(
        probe_routes, role):
    assert _request(role, GESTION + "/__probe__").status_code == 403


def test_gestion_prefix_match_respects_segment_boundaries(probe_routes):
    response = _request(ROLE, GESTION + "-otra/__probe__")

    assert response.status_code == 403


def test_role_reaches_the_counts_prefix_as_a_count_leader():
    """Owner decision 2026-10-09: the coordinator also leads counts. The
    prefix sits in its confined entry, not in the pinned allow-list."""
    assert CONTEOS_PREFIX == CONTEOS
    prefixes, _ = _CONFINED_ROLE_PREFIXES[ROLE]
    assert set(prefixes) == {PREFIX + "/auth", KPIS, GESTION, CONTEOS}
    response = _request(ROLE, CONTEOS + "/no-existe/a/b/c")

    assert response.status_code in (404, 405), response.text


def test_auth_prefix_stays_reachable_for_password_change():
    response = _request(ROLE, PREFIX + "/auth/password", "POST")

    assert response.status_code != 403, response.text


def test_admin_can_create_a_coordinador_user_with_web_credentials():
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    body = dict(nombre="Coordinador", email="c@x.com",
                password="clave-valida-77", role=ROLE)

    response = TestClient(app).post("/api/motored/usuarios", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["role"] == ROLE
    created = session.added_of_type(Usuario)
    assert created[0].role is MotoredRole.COORDINADOR_REPUESTOS
    assert created[0].hashed_password
