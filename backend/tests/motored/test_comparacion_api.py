"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-9, decisión
F4-8, spec SC-07..SC-13): el contrato HTTP de
`GET /api/motored/corridas/{id}/comparar?con=<real_id>`.

El servicio se reemplaza por un doble que graba sus argumentos
(`tests/motored/fixtures/corridas_api.py`): acá se prueba la forma del JSON
(el delta con signo, los totales de los dos lados, las tiendas que no se
comparan), los parámetros que llegan al servicio, el 422 codificado del
emparejamiento inválido (E-CORRIDA-063) y el 404 del escenario que no
existe. Las reglas y el SQL, en `test_comparacion_servicio.py` y contra
Postgres real en `pg_real/test_comparacion_pg.py`; el RBAC, en
`test_corridas_rbac.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos
from app.motored.services.corridas.codigos import ErrorCorrida
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx

BASE = "/api/motored/corridas"
ESCENARIO = fx.ESCENARIO_ID
REAL = fx.CORRIDA_ID
URL = f"{BASE}/{ESCENARIO}/comparar"
USUARIO = str(uuid.UUID(int=900))


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "comp-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "comp-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _cliente(rol="ADMIN"):
    sesion = FakeAsyncSession(execute_queue=[[]] * 4)
    override_motored_user(MotoredUser(user_id=USUARIO, role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


def _comparar(cliente, **params):
    return cliente.get(URL, params={"con": str(REAL), **params})


def test_the_comparison_names_both_corridas_and_the_corte(espia):
    cliente, _ = _cliente()

    respuesta = _comparar(cliente)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["escenario"]["id"] == str(ESCENARIO)
    assert cuerpo["escenario"]["es_escenario"] is True
    assert cuerpo["real"]["id"] == str(REAL)
    assert cuerpo["fecha_corte"] == "2026-09-21"
    assert (cuerpo["total"], cuerpo["limite"], cuerpo["offset"]) == (
        1, 100, 0)


def test_a_row_shows_both_sides_and_the_delta_sc_07(espia):
    cliente, _ = _cliente()

    [fila] = _comparar(cliente).json()["filas"]

    assert fila["sucursal"] == "UNO" and fila["codigo"] == "94109-12000S"
    assert fila["sugerido_real"] == "50.00"
    assert fila["sugerido_prueba"] == "62.00"
    assert fila["delta"] == "12.00"
    assert fila["pedido_final_real"] == "55.00"
    assert (fila["clase_real"], fila["clase_prueba"]) == ("AF", "AF")


def test_totals_per_tienda_show_both_sides_sc_09(espia):
    cliente, _ = _cliente()

    [total] = _comparar(cliente).json()["totales_por_sucursal"]

    assert total["unidades_real"] == "50.00"
    assert total["unidades_prueba"] == "62.00"
    assert total["diferencia_unidades"] == "12.00"
    assert total["diferencia_valor"] == "120.00"


def test_the_not_comparable_tiendas_are_listed_sc_13(espia):
    cliente, _ = _cliente()

    [dos] = _comparar(cliente).json()["no_comparables"]

    assert dos["nombre"] == "DOS"
    assert (dos["estado_real"], dos["estado_prueba"]) == ("FALLIDA", "OK")
    assert "FALLIDA" in dos["motivo"]


def test_the_service_gets_the_pairing_and_the_defaults(espia):
    cliente, _ = _cliente()

    _comparar(cliente)

    _, args, kw = espia.ultima("comparar")
    assert args == (ESCENARIO, REAL)
    assert kw == {"sucursal_id": None, "solo_diferencias": False,
                  "limite": 100, "offset": 0}


def test_the_filters_and_the_page_reach_the_service_sc_12(espia):
    cliente, _ = _cliente()

    _comparar(cliente, sucursal_id=str(fx.SUC_B), solo_diferencias="true",
              limite=25, offset=50)

    kw = espia.ultima("comparar")[2]
    assert kw == {"sucursal_id": fx.SUC_B, "solo_diferencias": True,
                  "limite": 25, "offset": 50}


def test_without_the_real_corrida_the_request_is_a_422(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(URL)

    assert respuesta.status_code == 422
    assert espia.llamadas == []


@pytest.mark.parametrize("params", [
    {"con": "no-es-un-uuid"}, {"limite": 101}, {"limite": 0},
    {"offset": -1}, {"sucursal_id": "no-es-un-uuid"}])
def test_an_invalid_parameter_is_a_422(espia, params):
    cliente, _ = _cliente()

    respuesta = cliente.get(URL, params={"con": str(REAL), **params})

    assert respuesta.status_code == 422
    assert espia.llamadas == []


def test_an_invalid_pairing_is_a_coded_422_sc_10_sc_11(espia):
    codigo = codigos.E_CORRIDA_COMPARACION_INVALIDA
    espia.error = (["comparar"], ErrorCorrida(
        codigo, codigos.mensaje(codigo, detalle="mismo corte")))
    cliente, _ = _cliente()

    respuesta = _comparar(cliente)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == {
        "code": "E-CORRIDA-063",
        "message": "No se puede comparar: mismo corte."}


def test_an_unknown_scenario_is_a_404(espia):
    espia.comparacion = None
    cliente, _ = _cliente()

    respuesta = _comparar(cliente)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Corrida no encontrada."


def test_compras_reads_the_comparison_too(espia):
    cliente, _ = _cliente("COMPRAS")

    assert _comparar(cliente).status_code == 200


def test_reading_the_comparison_never_commits(espia):
    cliente, sesion = _cliente()

    _comparar(cliente)

    assert sesion.committed is False and sesion.added == []
