"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3b, ADR-1, ADR-11,
spec CI-25..CI-36, decisiones F4-11, F4-13 y F4-15): el contrato HTTP de
enviar el pedido de una tienda, enviar varias a la vez y corregir el número
de orden.

Los servicios se reemplazan por dobles que graban sus argumentos
(`tests/motored/fixtures/corridas_api.py`): acá se prueba qué responde cada
endpoint, cómo traduce los errores codificados (404, 409, 422), qué se le
pide a cada capa y que sólo se confirma cuando todo salió bien. Las reglas
están en `test_envio_tienda.py` y contra Postgres real en
`pg_real/test_envio_pg.py`. El RBAC de cada ruta, en `test_corridas_rbac.py`.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos, envio
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
CUERPO = {"numero_pedido_proveedor": "12345", "fecha_envio": "2026-09-22"}
CONFLICTOS = [
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SIN_PEDIDO,
    codigos.E_CORRIDA_ENVIAR_NO_CERRADO,
    codigos.E_CORRIDA_ENVIAR_YA_ENVIADO,
    codigos.E_CORRIDA_ENVIO_DUPLICADO,
    codigos.E_CORRIDA_NADA_QUE_ENVIAR,
    codigos.E_CORRIDA_CORREGIR_NO_ENVIADO,
]


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "envio-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "envio-asc360")
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


def _rechazo(codigo, mensaje="no se puede", detalle=None):
    return ErrorCorrida(codigo, mensaje, detalle)


# --- POST .../sucursales/{sid}/enviar ----------------------------------------


def test_sending_one_tienda_returns_its_envio_and_commits_ci_25(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/enviar", json=CUERPO)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "corrida_id": str(CORRIDA), "sucursal_id": str(fx.SUC_A),
        "estado_pedido": "ENVIADO", "numero_pedido_proveedor": "12345",
        "fecha_envio": "2026-09-22", "enviada_por": str(fx.USUARIO_EDITOR),
        "enviada_en": "2026-09-21T10:00:00+00:00"}
    _, args, _ = espia.ultima("enviar_tienda")
    assert args == (
        CORRIDA, fx.SUC_A, "12345", "2026-09-22", uuid.UUID(USUARIO))
    assert sesion.committed is True


@pytest.mark.parametrize("cuerpo", [
    None, {}, {"numero_pedido_proveedor": 5, "fecha_envio": 20260922}])
def test_a_missing_or_untyped_payload_reaches_the_service_for_its_048(
        espia, cuerpo):
    """Sin cuerpo o con tipos raros el 422 lo da el servicio (048), después
    de los chequeos de estado, no el validador genérico."""
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{TIENDA}/enviar", json=cuerpo)

    assert respuesta.status_code == 200, respuesta.text
    _, args, _ = espia.ultima("enviar_tienda")
    esperado = cuerpo or {}
    assert args[2] == esperado.get("numero_pedido_proveedor")
    assert args[3] == esperado.get("fecha_envio")


def test_extra_fields_in_the_send_body_are_a_422(espia):
    cliente, _ = _cliente()

    respuesta = cliente.post(
        f"{TIENDA}/enviar", json={**CUERPO, "enviada_por": "otro"})

    assert respuesta.status_code == 422 and espia.llamadas == []


@pytest.mark.parametrize("codigo", CONFLICTOS)
def test_a_refused_single_send_is_a_coded_409(espia, codigo):
    espia.error = ({"enviar_tienda"}, _rechazo(codigo))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/enviar", json=CUERPO)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "no se puede"}
    assert sesion.committed is False and sesion.rolled_back is True


def test_an_invalid_payload_is_a_coded_422_048(espia):
    espia.error = ({"enviar_tienda"}, _rechazo(
        codigos.E_CORRIDA_ENVIO_INVALIDO, "número inválido"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/enviar", json=CUERPO)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-048"
    assert sesion.rolled_back is True


def test_the_duplicate_send_travels_with_corrida_and_number_in_detail(espia):
    detalle = {"tienda": "UNO", "corrida": "PED-2026-S39-000",
               "numero_pedido_proveedor": "12345"}
    espia.error = ({"enviar_tienda"}, _rechazo(
        codigos.E_CORRIDA_ENVIO_DUPLICADO, "ya enviada", detalle))
    cliente, _ = _cliente()

    cuerpo = cliente.post(f"{TIENDA}/enviar", json=CUERPO).json()["detail"]

    assert cuerpo["code"] == "E-CORRIDA-050" and cuerpo["detalle"] == detalle


def test_sending_an_unknown_corrida_or_tienda_is_a_404(espia):
    espia.error = ({"enviar_tienda"}, LookupError("La tienda no está"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/enviar", json=CUERPO)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "La tienda no está"
    assert sesion.committed is False and sesion.rolled_back is True


# --- POST /{id}/enviar: el lote ----------------------------------------------


def _lote(*ids_numeros):
    return {"envios": [
        {"sucursal_id": str(sid), "numero_pedido_proveedor": numero,
         "fecha_envio": "2026-09-22"} for sid, numero in ids_numeros]}


def test_a_batch_send_passes_each_tienda_and_returns_the_envios_ci_26(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.post(
        f"{BASE}/{CORRIDA}/enviar",
        json=_lote((fx.SUC_A, "12345"), (fx.SUC_B, "12346")))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id"] == str(CORRIDA)
    assert cuerpo["codigo"] == "PED-2026-S39-001"
    assert cuerpo["estado"] == "BORRADOR"
    assert [
        (e["sucursal_id"], e["numero_pedido_proveedor"])
        for e in cuerpo["enviadas"]] == [
        (str(fx.SUC_A), "12345"), (str(fx.SUC_B), "12346")]
    _, args, _ = espia.ultima("enviar_lote")
    assert args[0] == CORRIDA and args[2] == uuid.UUID(USUARIO)
    assert args[1] == [
        envio.PedidoEnviar(fx.SUC_A, "12345", "2026-09-22"),
        envio.PedidoEnviar(fx.SUC_B, "12346", "2026-09-22")]
    assert sesion.committed is True


@pytest.mark.parametrize("cuerpo", [
    None, {}, {"envios": []}, {"envios": "x"},
    {"envios": [{"numero_pedido_proveedor": "1"}]},
    {"envios": [{"sucursal_id": "no-uuid"}]},
    {"envios": [{"sucursal_id": str(fx.SUC_A), "otro": 1}]},
    {"envios": [{"sucursal_id": str(fx.SUC_A)}], "extra": 1},
    {"envios": [{"sucursal_id": str(uuid.UUID(int=n))} for n in range(201)]},
])
def test_a_malformed_batch_body_is_a_422_and_reaches_no_service(
        espia, cuerpo):
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{BASE}/{CORRIDA}/enviar", json=cuerpo)

    assert respuesta.status_code == 422 and espia.llamadas == []


def test_a_batch_of_exactly_200_tiendas_is_accepted(espia):
    cliente, _ = _cliente()
    cuerpo = {"envios": [
        {"sucursal_id": str(uuid.UUID(int=n))} for n in range(200)]}

    respuesta = cliente.post(f"{BASE}/{CORRIDA}/enviar", json=cuerpo)

    assert respuesta.status_code == 200, respuesta.text
    assert len(espia.ultima("enviar_lote")[1][1]) == 200


@pytest.mark.parametrize("codigo", CONFLICTOS)
def test_a_refused_batch_send_is_a_coded_409_naming_the_offender(
        espia, codigo):
    detalle = {"sucursal_id": str(fx.SUC_B), "tienda": "DOS"}
    espia.error = ({"enviar_lote"}, _rechazo(codigo, "DOS no", detalle))
    cliente, sesion = _cliente()

    respuesta = cliente.post(
        f"{BASE}/{CORRIDA}/enviar", json=_lote((fx.SUC_B, "1")))

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "DOS no", "detalle": detalle}
    assert sesion.committed is False and sesion.rolled_back is True


def test_a_batch_send_to_an_unknown_corrida_is_a_404(espia):
    espia.error = ({"enviar_lote"}, LookupError("Corrida no encontrada."))
    cliente, _ = _cliente()

    respuesta = cliente.post(
        f"{BASE}/{uuid.uuid4()}/enviar", json=_lote((fx.SUC_A, "1")))

    assert respuesta.status_code == 404


# --- PATCH .../sucursales/{sid}/envio: corregir el número (F4-15) -----------


def test_correcting_the_number_returns_the_envio_and_commits(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.patch(
        f"{TIENDA}/envio", json={"numero_pedido_proveedor": "99999"})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["numero_pedido_proveedor"] == "99999"
    assert cuerpo["estado_pedido"] == "ENVIADO"
    assert cuerpo["fecha_envio"] == "2026-09-22"
    _, args, _ = espia.ultima("corregir")
    assert args == (CORRIDA, fx.SUC_A, "99999", uuid.UUID(USUARIO))
    assert sesion.committed is True


@pytest.mark.parametrize("cuerpo", [None, {}])
def test_a_missing_corrected_number_reaches_the_service_for_its_048(
        espia, cuerpo):
    cliente, _ = _cliente()

    respuesta = cliente.patch(f"{TIENDA}/envio", json=cuerpo)

    assert respuesta.status_code == 200, respuesta.text
    assert espia.ultima("corregir")[1][2] is None


def test_the_send_date_cannot_be_corrected_it_is_an_unknown_field(espia):
    cliente, _ = _cliente()

    respuesta = cliente.patch(f"{TIENDA}/envio", json={
        "numero_pedido_proveedor": "1", "fecha_envio": "2026-09-23"})

    assert respuesta.status_code == 422 and espia.llamadas == []


@pytest.mark.parametrize("codigo", [
    codigos.E_CORRIDA_CORREGIR_NO_ENVIADO, codigos.E_CORRIDA_SIN_PEDIDO,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA])
def test_a_refused_correction_is_a_coded_409(espia, codigo):
    espia.error = ({"corregir"}, _rechazo(codigo))
    cliente, sesion = _cliente()

    respuesta = cliente.patch(
        f"{TIENDA}/envio", json={"numero_pedido_proveedor": "1"})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == codigo
    assert sesion.committed is False and sesion.rolled_back is True


def test_an_invalid_corrected_number_is_a_coded_422_048(espia):
    espia.error = ({"corregir"}, _rechazo(codigos.E_CORRIDA_ENVIO_INVALIDO))
    cliente, _ = _cliente()

    respuesta = cliente.patch(
        f"{TIENDA}/envio", json={"numero_pedido_proveedor": ""})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-048"


def test_correcting_an_unknown_tienda_is_a_404(espia):
    espia.error = ({"corregir"}, LookupError("La tienda no está"))
    cliente, _ = _cliente()

    respuesta = cliente.patch(
        f"{TIENDA}/envio", json={"numero_pedido_proveedor": "1"})

    assert respuesta.status_code == 404


def test_a_no_op_correction_is_still_a_200(espia):
    espia.correccion = envio.ResultadoCorreccion(
        espia.correccion.tienda, fx.fila_envio(fx.SUC_A, "12345"), False)
    cliente, _ = _cliente()

    respuesta = cliente.patch(
        f"{TIENDA}/envio", json={"numero_pedido_proveedor": "12345"})

    assert respuesta.status_code == 200
    assert respuesta.json()["numero_pedido_proveedor"] == "12345"


def test_the_send_date_is_serialized_as_an_iso_date(espia):
    espia.envios = envio.ResultadoEnvios(
        espia.envios.corrida,
        [fx.fila_envio(fx.SUC_A, "1", fecha_envio=datetime.date(2026, 9, 25))])
    cliente, _ = _cliente()

    cuerpo = cliente.post(f"{TIENDA}/enviar", json=CUERPO).json()

    assert cuerpo["fecha_envio"] == "2026-09-25"
