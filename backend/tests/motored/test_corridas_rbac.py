"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-9, spec
"RBAC (T19)"): quién puede qué en `/corridas`.

Matriz de roles sobre CADA endpoint (ADMIN/COMPRAS crean, cierran, anulan y
leen; CONSULTA y SUCURSAL sólo leen), el alcance por sucursal de SUCURSAL
(el doble de las consultas recibe el conjunto de sus sucursales; ningún otro
rol recibe restricción; una sucursal ajena es 403) y el confinamiento de
SERVICIO_CLIENTE, que pasa por la dependencia real. Que las consultas reales
honren ese alcance se prueba en `test_corrida_consultas.py` y en
`pg_real/test_corridas_api_pg.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.auth import create_motored_token
from app.motored.deps import get_motored_user_lookup
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx

BASE = "/api/motored/corridas"
USUARIO = str(uuid.UUID(int=900))
ID = fx.CORRIDA_ID
ESCRITURA = {"ADMIN", "COMPRAS"}
LECTURA = ["ADMIN", "COMPRAS", "CONSULTA", "SUCURSAL"]
TODOS = LECTURA + ["SERVICIO_CLIENTE", "ASESOR_MOSTRADOR"]

LECTURAS = [
    ("GET", BASE, None),
    ("GET", f"{BASE}/{ID}", None),
    ("GET", f"{BASE}/{ID}/progreso", None),
    ("GET", f"{BASE}/{ID}/lineas", None),
]
ESCRITURAS = [
    ("POST", BASE, {"fecha_corte": "2026-09-21"}),
    ("POST", f"{BASE}/{ID}/cerrar", None),
    ("POST", f"{BASE}/{ID}/anular", {"motivo": "motivo de prueba"}),
]


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "rbac-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "rbac-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _como(rol, sucursales=()):
    usuario = MotoredUser(
        user_id=USUARIO, role=rol, sucursal_ids=[str(s) for s in sucursales])
    override_motored_user(usuario)
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 8))
    return TestClient(app)


def _pedir(cliente, metodo, ruta, cuerpo):
    return cliente.request(metodo, ruta, json=cuerpo)


# --- Matriz de roles --------------------------------------------------------


@pytest.mark.parametrize("rol", TODOS)
@pytest.mark.parametrize("metodo,ruta,cuerpo", LECTURAS)
def test_only_the_four_panel_roles_can_read(espia, rol, metodo, ruta, cuerpo):
    respuesta = _pedir(_como(rol, [fx.SUC_A]), metodo, ruta, cuerpo)

    if rol in LECTURA:
        assert respuesta.status_code == 200, respuesta.text
    else:
        assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", TODOS)
@pytest.mark.parametrize("metodo,ruta,cuerpo", ESCRITURAS)
def test_only_admin_and_compras_can_write(espia, rol, metodo, ruta, cuerpo):
    respuesta = _pedir(_como(rol), metodo, ruta, cuerpo)

    if rol in ESCRITURA:
        assert respuesta.status_code in (200, 202), respuesta.text
    else:
        assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA"])
@pytest.mark.parametrize("metodo,ruta,cuerpo", ESCRITURAS)
def test_a_refused_write_reaches_no_service_and_commits_nothing(
        espia, rol, metodo, ruta, cuerpo):
    cliente = _como(rol, [fx.SUC_A])

    _pedir(cliente, metodo, ruta, cuerpo)

    assert espia.llamadas == [] and espia.encolados == []


# --- Alcance por sucursal ---------------------------------------------------


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "CONSULTA"])
def test_unrestricted_roles_read_with_no_scope(espia, rol):
    cliente = _como(rol, [fx.SUC_A])

    for _, ruta, _ in LECTURAS:
        cliente.get(ruta)

    alcances = [
        c[2]["alcance"] if c[0] == "listar" else c[1][1]
        for c in espia.llamadas]
    assert alcances == [None, None, None, None]


def test_a_sucursal_user_reads_with_the_set_of_its_own_sucursales(espia):
    cliente = _como("SUCURSAL", [fx.SUC_A, fx.SUC_B])

    for _, ruta, _ in LECTURAS:
        assert cliente.get(ruta).status_code == 200

    alcances = [
        c[2]["alcance"] if c[0] == "listar" else c[1][1]
        for c in espia.llamadas]
    assert alcances == [frozenset({fx.SUC_A, fx.SUC_B})] * 4


def test_a_sucursal_user_with_no_sucursales_gets_an_empty_scope(espia):
    cliente = _como("SUCURSAL", [])

    cliente.get(BASE)

    assert espia.ultima("listar")[2]["alcance"] == frozenset()


def test_a_foreign_sucursal_in_the_lines_is_a_403(espia):
    cliente = _como("SUCURSAL", [fx.SUC_A])

    respuesta = cliente.get(
        f"{BASE}/{ID}/lineas", params={"sucursal_id": str(fx.SUC_B)})

    assert respuesta.status_code == 403
    assert espia.llamadas == []


def test_an_own_sucursal_in_the_lines_is_served(espia):
    cliente = _como("SUCURSAL", [fx.SUC_A])

    respuesta = cliente.get(
        f"{BASE}/{ID}/lineas", params={"sucursal_id": str(fx.SUC_A)})

    assert respuesta.status_code == 200
    kw = espia.ultima("lineas")[2]
    assert kw["sucursal_id"] == fx.SUC_A


def test_lines_without_a_sucursal_are_left_to_the_scope(espia):
    cliente = _como("SUCURSAL", [fx.SUC_A])

    cliente.get(f"{BASE}/{ID}/lineas")

    _, args, kw = espia.ultima("lineas")
    assert args == (ID, frozenset({fx.SUC_A})) and kw["sucursal_id"] is None


def test_any_sucursal_filter_is_fine_for_an_unrestricted_role(espia):
    cliente = _como("CONSULTA")

    respuesta = cliente.get(
        f"{BASE}/{ID}/lineas", params={"sucursal_id": str(fx.SUC_B)})

    assert respuesta.status_code == 200


@pytest.mark.parametrize("ruta", [
    f"{BASE}/{ID}", f"{BASE}/{ID}/progreso", f"{BASE}/{ID}/lineas"])
def test_a_corrida_with_none_of_its_sucursales_is_a_404(espia, ruta):
    espia.detalle = espia.progreso = espia.lineas = None
    cliente = _como("SUCURSAL", [fx.SUC_A])

    assert cliente.get(ruta).status_code == 404


def test_a_malformed_sucursal_id_in_the_user_is_ignored(espia):
    usuario = MotoredUser(
        user_id=USUARIO, role="SUCURSAL",
        sucursal_ids=[str(fx.SUC_A), "no-uuid"])
    override_motored_user(usuario)
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))

    TestClient(app).get(BASE)

    assert espia.ultima("listar")[2]["alcance"] == frozenset({fx.SUC_A})


# --- Dependencia real: SERVICIO_CLIENTE y sin credenciales ------------------


def _con_dependencia_real(rol):
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role=rol)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))
    token = create_motored_token(sub=USUARIO, role=rol)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("metodo,ruta,cuerpo", LECTURAS + ESCRITURAS)
def test_servicio_cliente_is_confined_out_of_corridas(
        espia, metodo, ruta, cuerpo):
    cliente, cabeceras = _con_dependencia_real("SERVICIO_CLIENTE")

    respuesta = cliente.request(
        metodo, ruta, json=cuerpo, headers=cabeceras)

    assert respuesta.status_code == 403
    assert espia.llamadas == []


def test_a_compras_token_reaches_corridas_through_the_real_dependency(espia):
    cliente, cabeceras = _con_dependencia_real("COMPRAS")

    assert cliente.get(BASE, headers=cabeceras).status_code == 200


@pytest.mark.parametrize("metodo,ruta,cuerpo", LECTURAS + ESCRITURAS)
def test_unauthenticated_requests_are_a_401(espia, metodo, ruta, cuerpo):
    app.dependency_overrides.clear()
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 4))

    respuesta = TestClient(app).request(metodo, ruta, json=cuerpo)

    assert respuesta.status_code == 401
    assert espia.llamadas == []
