"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5b, ADR-6, spec
TP-08..TP-14b, TP-24..TP-33, decisión F4-7): el contrato HTTP del tope de
presupuesto por corrida y por tienda.

- `GET /corridas/{id}/topes`: el resumen por tienda.
- `GET /corridas/{id}/sucursales/{sid}/recorte`: la propuesta y su token.
- `POST /corridas/{id}/sucursales/{sid}/recorte {token}`: aplicarla.

El servicio se reemplaza por dobles que graban sus argumentos
(`tests/motored/fixtures/corridas_api.py`): acá se prueba qué responde cada
ruta, cómo traduce los errores codificados (404, 409), qué se le pide al
servicio y que sólo se confirma cuando todo salió bien. Las reglas están en
`test_tope_servicio.py` y contra Postgres real en `pg_real/test_tope_pg.py`.
El RBAC de cada ruta, en `test_corridas_rbac.py`.
"""
import json
import uuid
from decimal import Decimal

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
USUARIO = str(uuid.UUID(int=900))
CORRIDA = fx.CORRIDA_ID
TIENDA = f"{BASE}/{CORRIDA}/sucursales/{fx.SUC_A}"
TOKEN = "ab" * 32
CONFLICTOS = [
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SIN_PEDIDO,
    codigos.E_CORRIDA_RECORTE_MODO_OFF,
    codigos.E_CORRIDA_RECORTE_SIN_TOPE,
    codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA,
    codigos.E_CORRIDA_RECORTE_NO_BORRADOR,
]


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "tope-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "tope-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _cliente(rol="COMPRAS"):
    sesion = FakeAsyncSession(execute_queue=[[]] * 8)
    override_motored_user(MotoredUser(user_id=USUARIO, role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


# --- GET /{id}/topes --------------------------------------------------------


def test_the_corrida_summary_lists_each_tienda_with_its_cap_tp_09(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(f"{BASE}/{CORRIDA}/topes")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "activo": True, "corrida_id": str(CORRIDA),
        "tiendas": [{
            "sucursal_id": str(fx.SUC_A), "nombre": "UNO",
            "estado_pedido": "BORRADOR", "tope": "9000",
            "valor_a_pedir": "11000.00", "exceso": "2000.00",
            "lineas_sin_precio": 2}]}
    assert espia.ultima("topes")[1] == (CORRIDA,)


def test_an_inactive_summary_has_no_tiendas_tp_10(espia):
    espia.topes = fx.resumen_topes(activo=False, tiendas=[])
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{CORRIDA}/topes").json()

    assert cuerpo["activo"] is False and cuerpo["tiendas"] == []


def test_a_tienda_without_cap_serializes_null_cap_and_excess(espia):
    espia.topes = fx.resumen_topes(tiendas=[{
        "sucursal_id": fx.SUC_B, "nombre": "DOS",
        "estado_pedido": "CERRADO", "tope": None,
        "valor_a_pedir": Decimal("5.00"), "exceso": None,
        "lineas_sin_precio": 0}])
    cliente, _ = _cliente()

    [fila] = cliente.get(f"{BASE}/{CORRIDA}/topes").json()["tiendas"]

    assert fila["tope"] is None and fila["exceso"] is None


def test_a_summary_of_an_unknown_corrida_is_404_and_rolls_back(espia):
    espia.error = (["topes"], LookupError("Corrida no encontrada."))
    cliente, sesion = _cliente()

    respuesta = cliente.get(f"{BASE}/{CORRIDA}/topes")

    assert respuesta.status_code == 404
    assert sesion.rolled_back is True


# --- GET .../recorte ---------------------------------------------------------


def test_the_preview_returns_the_proposal_and_its_token_tp_09(espia):
    cliente, _ = _cliente()

    respuesta = cliente.get(f"{TIENDA}/recorte")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["activo"] is True
    assert cuerpo["token"] == TOKEN
    assert cuerpo["tope"] == "9000"
    assert cuerpo["exceso"] == "2000.00"
    assert cuerpo["recortes"] == [{
        "linea_id": 1, "codigo": "C-1", "nombre": "PARTE",
        "clase_abc": "C", "unidad_empaque": 10,
        "pedido_actual": "50.00", "pedido_propuesto": "30.00",
        "empaques_recortados": "2", "valor_recortado": "2000.00"}]
    assert espia.ultima("recorte_ver")[1] == (CORRIDA, fx.SUC_A)


def test_an_inactive_preview_carries_the_reason_and_no_proposal(espia):
    espia.propuesta = fx.propuesta_recorte(
        activo=False, motivo_inactivo="NO_BORRADOR", tope=None,
        valor_actual=None, exceso=None, recortes=[], valor_final=None,
        exceso_residual=None, lineas_sin_precio=0, token=None)
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{TIENDA}/recorte").json()

    assert cuerpo["activo"] is False
    assert cuerpo["motivo_inactivo"] == "NO_BORRADOR"
    assert cuerpo["recortes"] == [] and cuerpo["token"] is None


def test_the_warnings_of_the_preview_travel_with_code_and_message(espia):
    aviso = {"codigo": "A-CORRIDA-121", "mensaje": "2 líneas sin precio"}
    espia.propuesta = fx.propuesta_recorte(
        advertencias=[aviso], lineas_sin_precio=2)
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{TIENDA}/recorte").json()

    assert cuerpo["advertencias"] == [aviso]
    assert cuerpo["lineas_sin_precio"] == 2


def test_a_preview_of_an_unknown_tienda_is_404(espia):
    espia.error = (
        ["recorte_ver"], LookupError("La tienda no está en la corrida."))
    cliente, _ = _cliente()

    respuesta = cliente.get(f"{TIENDA}/recorte")

    assert respuesta.status_code == 404
    assert "tienda" in respuesta.json()["detail"]


# --- POST .../recorte -------------------------------------------------------


def test_applying_returns_the_new_numbers_and_commits_tp_24(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/recorte", json={"token": TOKEN})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["lineas_recortadas"] == 1
    assert cuerpo["valor_liberado"] == "2000.00"
    assert cuerpo["valor_final"] == "9000.00"
    assert cuerpo["exceso_residual"] == "0.00"
    assert cuerpo["totales_tienda"]["valor_a_pedir"] == "6000000.00"
    _, args, _ = espia.ultima("recorte_aplicar")
    assert args == (CORRIDA, fx.SUC_A, TOKEN, uuid.UUID(USUARIO))
    assert sesion.committed is True


@pytest.mark.parametrize("cuerpo", [None, {}, {"token": 12}])
def test_a_missing_or_untyped_token_reaches_the_service_for_its_060(
        espia, cuerpo):
    """Sin token o con otro tipo, el 409 (060) lo da el servicio, no el 422
    genérico del validador."""
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{TIENDA}/recorte", json=cuerpo)

    assert respuesta.status_code == 200, respuesta.text
    esperado = (cuerpo or {}).get("token")
    assert espia.ultima("recorte_aplicar")[1][2] == esperado


def test_extra_fields_in_the_apply_body_are_a_422(espia):
    cliente, _ = _cliente()

    respuesta = cliente.post(
        f"{TIENDA}/recorte", json={"token": TOKEN, "tope": "1"})

    assert respuesta.status_code == 422
    assert "recorte_aplicar" not in [c[0] for c in espia.llamadas]


@pytest.mark.parametrize("codigo", CONFLICTOS)
def test_a_rejected_apply_is_a_coded_409_and_rolls_back(espia, codigo):
    espia.error = (
        ["recorte_aplicar"], ErrorCorrida(codigo, "no se puede", None))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/recorte", json={"token": TOKEN})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "no se puede"}
    assert sesion.rolled_back is True and sesion.committed is False


def test_a_stale_proposal_returns_the_fresh_one_in_detalle_tp_25(espia):
    fresca = {"token": "cd" * 32, "recortes": [], "tope": "9000"}
    espia.error = (["recorte_aplicar"], ErrorCorrida(
        codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA, "cambió",
        {"propuesta": fresca}))
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{TIENDA}/recorte", json={"token": TOKEN})

    cuerpo = respuesta.json()["detail"]
    assert cuerpo["code"] == "E-CORRIDA-060"
    assert json.loads(json.dumps(cuerpo["detalle"]["propuesta"])) == fresca


def test_applying_on_an_unknown_tienda_is_404(espia):
    espia.error = (
        ["recorte_aplicar"], LookupError("La tienda no está en la corrida."))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/recorte", json={"token": TOKEN})

    assert respuesta.status_code == 404
    assert sesion.rolled_back is True


def test_admin_can_apply_too(espia):
    cliente, _ = _cliente("ADMIN")

    assert cliente.post(
        f"{TIENDA}/recorte", json={"token": TOKEN}).status_code == 200
