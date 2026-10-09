"""
Owner decision 2026-10-05: the SUCURSAL and CONSULTA roles have no screens
yet, so the server denies them every Motored data endpoint with one 403.

They keep login and their own password change (`/api/motored/auth/*`).
The guard lives in `get_current_motored_user` (path confinement), so these
tests use the REAL dependency with a real token; only the user lookup and
the DB session are faked.

`test_every_motored_route_is_guarded_or_public` walks every Motored route
so a new endpoint cannot leak: it either depends on the guard, or it is
listed in `PUBLIC_ROUTES` (login, the bot-secret API and the public survey).
"""
import re
import uuid

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import (
    ROL_SIN_PANTALLAS_DETAIL,
    ROLES_SIN_ACCESO,
    get_current_motored_user,
    get_motored_user_lookup,
)
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db

BLOCKED_ROLES = ["SUCURSAL", "CONSULTA"]
DETAIL = "Tu rol todavía no tiene pantallas habilitadas."
PREFIX = "/api/motored"
ACTUAL = "clave-actual-123"
NUEVA = "clave-nueva-456"

# Routes that never use the web JWT: login, the bot-secret API (Lore/Sonia)
# and the public survey. Any other route MUST depend on the guard.
PUBLIC_ROUTES = {
    ("POST", "/api/motored/publico/informe/{token}/pendientes"),
    ("POST", "/api/motored/auth/login"),
    ("GET", "/api/motored/bot/yo"),
    ("GET", "/api/motored/bot/sucursales"),
    ("POST", "/api/motored/bot/registro"),
    ("POST", "/api/motored/bot/admin/vincular"),
    ("GET", "/api/motored/bot/admin/solicitudes"),
    ("POST", "/api/motored/bot/admin/solicitudes/{usuario_id}/aprobar"),
    ("POST", "/api/motored/bot/admin/solicitudes/{usuario_id}/rechazar"),
    ("POST", "/api/motored/bot/referencias/resolver"),
    ("POST", "/api/motored/bot/demanda-perdida"),
    ("GET", "/api/motored/bot/demanda-perdida/hoy"),
    ("PATCH", "/api/motored/bot/demanda-perdida/lineas/{linea_id}"),
    ("POST", "/api/motored/bot/demanda-perdida/{carga_id}/anular"),
    ("POST", "/api/motored/encuesta/publico/identificar"),
    ("POST", "/api/motored/encuesta/publico/respuestas"),
    ("POST", "/api/motored/publico/informe/{token}"),
    # Inventory-count pairs (no user account): their own device token.
    ("POST", "/api/motored/publico/conteos/{slug}/unirse"),
    ("GET", "/api/motored/publico/conteos/{slug}/sesion"),
    ("POST", "/api/motored/publico/conteos/{slug}/salir"),
    ("GET", "/api/motored/publico/conteos/{slug}/catalogo"),
    ("GET", "/api/motored/publico/conteos/{slug}/ubicaciones"),
    ("PUT", "/api/motored/publico/conteos/{slug}/ubicacion"),
    ("POST", "/api/motored/publico/conteos/{slug}/lecturas"),
    ("POST",
     "/api/motored/publico/conteos/{slug}/lecturas/{lectura_id}/anular"),
    ("GET", "/api/motored/publico/conteos/{slug}/lecturas/recientes"),
}

# One representative read per router.
REPRESENTATIVE_PATHS = [
    "/api/motored/maestros/sucursales",
    "/api/motored/maestros/referencias/buscar?q=abc",
    "/api/motored/maestros/salud",
    "/api/motored/cargas",
    "/api/motored/corridas",
    "/api/motored/tablero-asesores?desde=2026-01&hasta=2026-01",
    "/api/motored/tablero-asesores/kpis/ventas",
    "/api/motored/presupuestos/tiendas",
    "/api/motored/parametros/configuracion",
    "/api/motored/parametros/dias_seguridad/vigente",
    "/api/motored/usuarios",
    "/api/motored/usuarios/me/telegram",
    "/api/motored/vendedores",
    "/api/motored/clientes-tecnired",
    "/api/motored/demanda-perdida/cobertura-bot",
    "/api/motored/encuesta/cargas",
    "/api/motored/detractores",
    "/api/motored/avisos-antiguedad",
    "/api/motored/inicio",
]


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "sin-acceso-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "sin-acceso-asc360")
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def _as_user(user: MotoredUser, queue=None) -> dict:
    async def _lookup(user_id: str):
        return user

    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=queue or [[]] * 4))
    token = create_motored_token(sub=user.user_id, role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _request(role: str, method: str, path: str):
    user = MotoredUser(user_id=str(uuid.uuid4()), role=role)
    headers = _as_user(user)
    with TestClient(app) as client:
        return client.request(method, path, headers=headers)


def _route_calls(dependant) -> set:
    calls, pending = set(), [dependant]
    while pending:
        current = pending.pop()
        calls.add(current.call)
        pending.extend(current.dependencies)
    return calls


def _motored_routes():
    for ctx in iter_route_contexts(app.routes):
        if (ctx.path or "").startswith(PREFIX + "/"):
            for method in sorted(ctx.methods):
                yield method, ctx.path, ctx.original_route.dependant


def _guarded_routes():
    return [
        (method, path)
        for method, path, dependant in _motored_routes()
        if get_current_motored_user in _route_calls(dependant)
        and not path.startswith(PREFIX + "/auth/")
    ]


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_blocked_roles_constant_is_exactly_sucursal_and_consulta():
    assert set(ROLES_SIN_ACCESO) == set(BLOCKED_ROLES)
    assert ROL_SIN_PANTALLAS_DETAIL == DETAIL


@pytest.mark.parametrize("role", BLOCKED_ROLES)
@pytest.mark.parametrize("path", REPRESENTATIVE_PATHS)
def test_blocked_role_gets_403_on_every_router(role, path):
    response = _request(role, "GET", path)

    assert response.status_code == 403, (path, response.text)
    assert response.json()["detail"] == DETAIL


def test_every_motored_route_is_guarded_or_public():
    unguarded = {
        (method, path)
        for method, path, dependant in _motored_routes()
        if get_current_motored_user not in _route_calls(dependant)
    }

    assert unguarded == PUBLIC_ROUTES


@pytest.mark.parametrize("role", BLOCKED_ROLES)
def test_guard_denies_blocked_roles_on_every_guarded_route(role):
    routes = _guarded_routes()
    assert len(routes) > 50
    leaks = []
    for method, path in routes:
        response = _request(role, method, _fill(path))
        if response.status_code != 403 or (
            response.json().get("detail") != DETAIL
        ):
            leaks.append((method, path, response.status_code))

    assert leaks == []


def _usuario(role: str, **kw) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana", email="ana@motoredcolombia.com.co",
        hashed_password=get_password_hash(ACTUAL), role=role, activo=True,
        status="approved",
    )
    base.update(kw)
    return Usuario(**base)


def _change_password(usuario: Usuario, must_change: bool = False):
    user = MotoredUser(
        user_id=str(usuario.id), role=usuario.role,
        must_change_password=must_change,
    )
    headers = _as_user(user, queue=[[], [usuario], [usuario]])
    with TestClient(app) as client:
        return client.post(
            PREFIX + "/auth/password",
            json={"actual": ACTUAL, "nueva": NUEVA},
            headers=headers,
        )


@pytest.mark.parametrize("role", BLOCKED_ROLES)
def test_blocked_role_can_change_own_password(role):
    response = _change_password(_usuario(role))

    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == role


@pytest.mark.parametrize("role", BLOCKED_ROLES)
def test_blocked_role_can_complete_forced_first_login_change(role):
    usuario = _usuario(role, must_change_password=True)

    response = _change_password(usuario, must_change=True)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", BLOCKED_ROLES)
def test_blocked_role_is_not_blocked_on_login(role):
    override_motored_db(FakeAsyncSession(execute_queue=[[], []]))
    with TestClient(app) as client:
        response = client.post(
            PREFIX + "/auth/login",
            json={"email": "s@x.com", "password": "12345678"},
        )

    assert response.status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "COMPRAS"])
def test_full_access_roles_still_reach_the_handler(role):
    path = PREFIX + "/parametros/dias_seguridad/vigente"

    response = _request(role, "GET", path)

    assert response.status_code == 404  # handler ran: no vigente version


@pytest.mark.parametrize(
    "role,path",
    [
        ("GERENCIA", "/api/motored/presupuestos/meses"),
        ("SERVICIO_CLIENTE", "/api/motored/encuesta/cargas/plantilla"),
    ],
)
def test_confined_roles_keep_their_own_prefixes(role, path):
    response = _request(role, "GET", path)

    assert response.status_code != 403, response.text


@pytest.mark.parametrize("role", ["GERENCIA", "SERVICIO_CLIENTE"])
def test_confined_roles_keep_their_own_detail_outside_prefixes(role):
    response = _request(role, "GET", PREFIX + "/usuarios")

    assert response.status_code == 403
    assert response.json()["detail"] != DETAIL
