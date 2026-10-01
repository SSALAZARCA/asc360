"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-9, spec
"RBAC (T19)") y Fase 4 (sdd/motored-pedidos-ui, decision F4-16): quién
puede qué en `/corridas`.

Matriz de roles sobre CADA endpoint: sólo ADMIN y COMPRAS leen, crean,
cierran y anulan; SUCURSAL, CONSULTA y SERVICIO_CLIENTE reciben 403 en todo
y sin credenciales es 401. SERVICIO_CLIENTE pasa por la dependencia real. El
alcance por sucursal sigue existiendo como defensa en profundidad dentro de
las consultas (`test_corrida_consultas.py` y `pg_real/test_corridas_api_pg.py`
lo prueban a nivel de servicio); la API ya no lo necesita porque ningún rol
restringido llega a ella.
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
LECTURA = ["ADMIN", "COMPRAS"]
DENEGADOS = ["SUCURSAL", "CONSULTA", "SERVICIO_CLIENTE"]
TODOS = LECTURA + DENEGADOS + ["ASESOR_MOSTRADOR"]

LECTURAS_F3 = [
    ("GET", BASE, None),
    ("GET", f"{BASE}/{ID}", None),
    ("GET", f"{BASE}/{ID}/progreso", None),
    ("GET", f"{BASE}/{ID}/lineas", None),
]
# Fase 4 (B2): el historial de una línea es otra lectura de /corridas.
LECTURAS = LECTURAS_F3 + [
    ("GET", f"{BASE}/{ID}/lineas/7/historial", None),
    # Fase 4 (B3a): la cabecera de una tienda y su línea de tiempo.
    ("GET", f"{BASE}/{ID}/sucursales/{fx.SUC_A}", None),
    ("GET", f"{BASE}/{ID}/sucursales/{fx.SUC_A}/eventos", None),
]
ESCRITURAS = [
    ("POST", BASE, {"fecha_corte": "2026-09-21"}),
    ("POST", f"{BASE}/{ID}/cerrar", None),
    ("POST", f"{BASE}/{ID}/anular", {"motivo": "motivo de prueba"}),
    # Fase 4 (B2): la edición de una línea (ED-20, F4-16).
    ("PATCH", f"{BASE}/{ID}/lineas/7", {"pedido_final": 60}),
    # Fase 4 (B3a): cerrar y reabrir el pedido de una tienda (CI-11, CI-24).
    ("POST", f"{BASE}/{ID}/sucursales/{fx.SUC_A}/cerrar", None),
    ("POST", f"{BASE}/{ID}/sucursales/{fx.SUC_A}/reabrir",
     {"motivo": "Corrección de cantidades"}),
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
def test_only_admin_and_compras_can_read(espia, rol, metodo, ruta, cuerpo):
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


# --- Lectura denegada (F4-16) ------------------------------------------------


@pytest.mark.parametrize("rol", DENEGADOS)
@pytest.mark.parametrize("metodo,ruta,cuerpo", LECTURAS)
def test_sucursal_consulta_and_servicio_cliente_get_403_on_every_read(
        espia, rol, metodo, ruta, cuerpo):
    cliente = _como(rol, [fx.SUC_A])

    respuesta = _pedir(cliente, metodo, ruta, cuerpo)

    assert respuesta.status_code == 403
    assert espia.llamadas == []


@pytest.mark.parametrize("rol", DENEGADOS)
def test_a_denied_role_is_refused_even_with_a_sucursal_filter(espia, rol):
    cliente = _como(rol, [fx.SUC_A])

    respuesta = cliente.get(
        f"{BASE}/{ID}/lineas", params={"sucursal_id": str(fx.SUC_A)})

    assert respuesta.status_code == 403
    assert espia.llamadas == []


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
def test_unrestricted_roles_read_with_no_scope(espia, rol):
    cliente = _como(rol, [fx.SUC_A])

    for _, ruta, _ in LECTURAS_F3:
        cliente.get(ruta)

    alcances = [
        c[2]["alcance"] if c[0] == "listar" else c[1][1]
        for c in espia.llamadas]
    assert alcances == [None, None, None, None]


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS"])
def test_any_sucursal_filter_is_fine_for_an_allowed_role(espia, rol):
    cliente = _como(rol)

    respuesta = cliente.get(
        f"{BASE}/{ID}/lineas", params={"sucursal_id": str(fx.SUC_B)})

    assert respuesta.status_code == 200
    assert espia.ultima("lineas")[2]["sucursal_id"] == fx.SUC_B


@pytest.mark.parametrize("ruta", [
    f"{BASE}/{ID}", f"{BASE}/{ID}/progreso", f"{BASE}/{ID}/lineas"])
def test_a_missing_corrida_is_a_404_for_an_allowed_role(espia, ruta):
    espia.detalle = espia.progreso = espia.lineas = None
    cliente = _como("COMPRAS")

    assert cliente.get(ruta).status_code == 404


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
