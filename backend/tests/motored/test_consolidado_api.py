"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-8, decisión
F4-9, spec CO-01..CO-11): el contrato HTTP de
`GET /api/motored/corridas/{id}/consolidado`.

El servicio se reemplaza por un doble que graba sus argumentos
(`tests/motored/fixtures/corridas_api.py`): acá se prueba qué responde la
ruta (la forma del JSON, los decimales exactos, la tienda fallida marcada y
sin números), los límites de paginación (100 por página, nunca más), el 404
y lo que se le pide al servicio. Las reglas y el SQL están en
`test_consolidado_servicio.py` y contra Postgres real en
`pg_real/test_consolidado_pg.py`; el RBAC, en `test_corridas_rbac.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.api import corridas_vistas
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx

BASE = "/api/motored/corridas"
URL = f"{BASE}/{fx.CORRIDA_ID}/consolidado"
USUARIO = str(uuid.UUID(int=900))


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "cons-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "cons-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _cliente(rol="COMPRAS"):
    sesion = FakeAsyncSession(execute_queue=[[]] * 4)
    override_motored_user(MotoredUser(user_id=USUARIO, role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


def test_the_matrix_returns_columns_rows_and_totals_co_01(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(URL)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["corrida_id"] == str(fx.CORRIDA_ID)
    assert cuerpo["codigo"] == "PED-2026-S39-001"
    assert cuerpo["es_escenario"] is False
    assert cuerpo["totales"] == {"unidades": "12.00", "valor": "1200.00"}
    assert (cuerpo["total"], cuerpo["limite"], cuerpo["offset"]) == (
        1, 100, 0)


def test_a_row_carries_its_total_and_sparse_cells_co_02(espia):
    cliente, _ = _cliente()

    [fila] = cliente.get(URL).json()["filas"]

    assert fila["codigo"] == "94109-12000S" and fila["nombre"] == "Filtro"
    assert fila["total"] == "12.00"
    assert fila["celdas"] == {str(fx.SUC_A): "12.00"}


def test_a_failed_tienda_is_a_flagged_column_without_numbers_co_06(espia):
    cliente, _ = _cliente()

    [uno, dos] = cliente.get(URL).json()["tiendas"]

    assert (uno["estado"], uno["estado_pedido"]) == ("OK", "BORRADOR")
    assert uno["unidades"] == "12.00" and uno["valor"] == "1200.00"
    assert dos["estado"] == "FALLIDA" and dos["estado_pedido"] is None
    assert dos["codigo"] == "E-CORRIDA-020"
    assert dos["unidades"] is None and dos["valor"] is None


def test_the_service_gets_the_defaults_and_no_scope_co_01(espia):
    cliente, _ = _cliente()

    cliente.get(URL)

    _, args, kw = espia.ultima("consolidado")
    assert args == (fx.CORRIDA_ID,)
    assert kw == {"q": None, "estado_pedido": None, "limite": 100,
                  "offset": 0}


def test_the_filters_and_the_page_reach_the_service_co_05(espia):
    cliente, _ = _cliente()

    cliente.get(URL, params={
        "q": "  filtro ", "estado_pedido": "CERRADO", "limite": 50,
        "offset": 100})

    kw = espia.ultima("consolidado")[2]
    assert kw == {"q": "filtro", "estado_pedido": "CERRADO", "limite": 50,
                  "offset": 100}


def test_a_blank_search_is_no_search(espia):
    cliente, _ = _cliente()

    cliente.get(URL, params={"q": "   "})

    assert espia.ultima("consolidado")[2]["q"] is None


@pytest.mark.parametrize("params", [
    {"limite": 101}, {"limite": 1000}, {"limite": 0}, {"offset": -1},
    {"estado_pedido": "ANULADO"}])
def test_an_out_of_range_page_or_filter_is_a_422(espia, params):
    cliente, _ = _cliente()

    respuesta = cliente.get(URL, params=params)

    assert respuesta.status_code == 422
    assert espia.llamadas == []


def test_the_page_never_exceeds_one_hundred_references_co_03(espia):
    cliente, _ = _cliente()

    assert cliente.get(URL, params={"limite": 100}).status_code == 200


def test_an_unknown_corrida_is_a_404(espia):
    espia.consolidado = None
    cliente, _ = _cliente()

    respuesta = cliente.get(URL)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Corrida no encontrada."


def test_an_empty_matrix_is_a_200_not_an_error_co_10(espia):
    espia.consolidado = fx.consolidado_vista(
        estado="PENDIENTE", tiendas=[], filas=[], total=0,
        totales={"unidades": 0, "valor": 0})
    cliente, _ = _cliente()

    respuesta = cliente.get(URL)

    assert respuesta.status_code == 200
    assert respuesta.json()["filas"] == [] and respuesta.json()["total"] == 0


def test_reading_the_matrix_never_commits(espia):
    cliente, sesion = _cliente()

    cliente.get(URL)

    assert sesion.committed is False and sesion.added == []


def test_a_scenario_matrix_is_marked_co_10(espia):
    espia.consolidado = fx.consolidado_vista(es_escenario=True)
    cliente, _ = _cliente("ADMIN")

    assert cliente.get(URL).json()["es_escenario"] is True


# --- Superficie -------------------------------------------------------------


def test_the_vistas_router_exposes_exactly_the_two_read_operations():
    rutas = {
        (metodo, ruta.path)
        for ruta in corridas_vistas.router.routes for metodo in ruta.methods}

    assert rutas == {
        ("GET", "/corridas/{corrida_id}/consolidado"),
        ("GET", "/corridas/{corrida_id}/comparar"),
    }
