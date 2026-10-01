"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3a, ADR-1, spec
CI-05..CI-24, DM-04): el contrato HTTP del ciclo de vida del pedido por
tienda.

Los servicios y las lecturas se reemplazan por dobles que graban sus
argumentos (`tests/motored/fixtures/corridas_api.py`): acá se prueba qué
responde cada endpoint, cómo traduce los errores codificados (404, 409, 422,
403), qué se le pide a cada capa y que sólo se confirma cuando todo salió
bien. Las reglas están en `test_pedido_tienda.py` y contra Postgres real en
`pg_real/test_pedido_tienda_pg.py`. El RBAC de cada ruta, en
`test_corridas_rbac.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.api import corridas_pedido
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


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "pedido-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "pedido-asc360")
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


# --- POST /{id}/cerrar: el lote ---------------------------------------------


def test_closing_without_a_body_closes_every_borrador_tienda(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{BASE}/{CORRIDA}/cerrar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "id": str(CORRIDA), "codigo": "PED-2026-S39-001",
        "estado": "BORRADOR",
        "cerradas": [str(fx.SUC_A), str(fx.SUC_B)], "ya_cerradas": 0}
    _, args, _ = espia.ultima("cerrar")
    assert args == (CORRIDA, uuid.UUID(USUARIO), None)
    assert sesion.committed is True


def test_closing_named_tiendas_passes_them_to_the_service_ci_06(espia):
    cliente, _ = _cliente()

    respuesta = cliente.post(
        f"{BASE}/{CORRIDA}/cerrar",
        json={"sucursal_ids": [str(fx.SUC_B), str(fx.SUC_A)]})

    assert respuesta.status_code == 200, respuesta.text
    _, args, _ = espia.ultima("cerrar")
    assert args[2] == [fx.SUC_B, fx.SUC_A]


@pytest.mark.parametrize("cuerpo", [
    {"sucursal_ids": []}, {"sucursal_ids": ["no-es-un-uuid"]},
    {"todas": True}, {"sucursal_ids": None, "otro": 1}])
def test_a_malformed_batch_body_is_a_422_and_reaches_no_service(
        espia, cuerpo):
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{BASE}/{CORRIDA}/cerrar", json=cuerpo)

    assert respuesta.status_code == 422
    assert espia.llamadas == []


def test_an_empty_json_body_also_means_all(espia):
    cliente, _ = _cliente()

    assert cliente.post(
        f"{BASE}/{CORRIDA}/cerrar", json={}).status_code == 200
    assert espia.ultima("cerrar")[1][2] is None


@pytest.mark.parametrize("codigo", [
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_CERRAR_NO_BORRADOR,
    codigos.E_CORRIDA_SIN_PEDIDO,
])
def test_a_refused_batch_close_is_a_coded_409(espia, codigo):
    espia.error = ({"cerrar"}, _rechazo(codigo, "no se puede cerrar"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{BASE}/{CORRIDA}/cerrar")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "no se puede cerrar"}
    assert sesion.committed is False and sesion.rolled_back is True


def test_the_offender_of_a_refused_batch_travels_in_the_detail(espia):
    detalle = {"sucursal_id": str(fx.SUC_B), "tienda": "DOS"}
    espia.error = ({"cerrar"}, _rechazo(
        codigos.E_CORRIDA_CERRAR_NO_BORRADOR, "DOS ya cerrada", detalle))
    cliente, _ = _cliente()

    cuerpo = cliente.post(f"{BASE}/{CORRIDA}/cerrar").json()["detail"]

    assert cuerpo["detalle"] == detalle


def test_closing_an_unknown_corrida_or_tienda_is_a_404(espia):
    espia.error = ({"cerrar"}, LookupError("no existe"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{BASE}/{uuid.uuid4()}/cerrar")

    assert respuesta.status_code == 404
    assert sesion.committed is False and sesion.rolled_back is True


# --- POST .../sucursales/{sid}/cerrar y /reabrir ----------------------------


def test_closing_one_tienda_returns_its_pedido_state(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/cerrar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "corrida_id": str(CORRIDA), "sucursal_id": str(fx.SUC_A),
        "estado_pedido": "CERRADO"}
    _, args, _ = espia.ultima("cerrar_tienda")
    assert args == (CORRIDA, fx.SUC_A, uuid.UUID(USUARIO))
    assert sesion.committed is True


@pytest.mark.parametrize("codigo", [
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_CERRAR_NO_BORRADOR,
    codigos.E_CORRIDA_SIN_PEDIDO,
])
def test_a_refused_single_close_is_a_coded_409(espia, codigo):
    espia.error = ({"cerrar_tienda"}, _rechazo(codigo))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/cerrar")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == codigo
    assert sesion.rolled_back is True


def test_a_single_close_of_an_unknown_tienda_is_a_404(espia):
    espia.error = ({"cerrar_tienda"}, LookupError("La tienda no está"))
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{TIENDA}/cerrar")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "La tienda no está"


def test_reopening_passes_the_motivo_untouched_to_the_service(espia):
    espia.tienda.estado_pedido = "BORRADOR"
    cliente, sesion = _cliente()

    respuesta = cliente.post(
        f"{TIENDA}/reabrir", json={"motivo": "  Corrección  "})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_pedido"] == "BORRADOR"
    _, args, _ = espia.ultima("reabrir")
    assert args == (
        CORRIDA, fx.SUC_A, uuid.UUID(USUARIO), "  Corrección  ")
    assert sesion.committed is True


@pytest.mark.parametrize("cuerpo", [None, {}, {"motivo": None},
                                    {"motivo": ""}, {"motivo": 5}])
def test_a_missing_or_blank_motivo_reaches_the_service_not_a_generic_422(
        espia, cuerpo):
    espia.error = ({"reabrir"}, _rechazo(
        codigos.E_CORRIDA_REABRIR_MOTIVO, "falta el motivo"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{TIENDA}/reabrir", json=cuerpo)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == {
        "code": "E-CORRIDA-046", "message": "falta el motivo"}
    assert espia.ultima("reabrir")[1][3] == (
        None if cuerpo is None else cuerpo.get("motivo"))
    assert sesion.rolled_back is True


def test_a_reopen_body_with_extra_fields_is_a_422(espia):
    cliente, _ = _cliente()

    respuesta = cliente.post(
        f"{TIENDA}/reabrir", json={"motivo": "x", "forzar": True})

    assert respuesta.status_code == 422 and espia.llamadas == []


@pytest.mark.parametrize("codigo", [
    codigos.E_CORRIDA_REABRIR_BORRADOR,
    codigos.E_CORRIDA_REABRIR_ENVIADO,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SIN_PEDIDO,
])
def test_a_refused_reopen_is_a_coded_409(espia, codigo):
    espia.error = ({"reabrir"}, _rechazo(codigo))
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{TIENDA}/reabrir", json={"motivo": "x"})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == codigo


def test_reopening_an_unknown_tienda_is_a_404(espia):
    espia.error = ({"reabrir"}, LookupError("no existe"))
    cliente, _ = _cliente()

    assert cliente.post(
        f"{TIENDA}/reabrir", json={"motivo": "x"}).status_code == 404


# --- GET .../sucursales/{sid} y /eventos ------------------------------------


def test_the_tienda_header_is_served_with_its_totals_and_actions(espia):
    cliente, _ = _cliente("ADMIN")

    respuesta = cliente.get(TIENDA)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["corrida_codigo"] == "PED-2026-S39-001"
    assert (cuerpo["nombre"], cuerpo["sic"]) == ("UNO", "SIC-1")
    assert cuerpo["estado_pedido"] == "BORRADOR"
    assert cuerpo["totales"]["unidades_a_pedir"] == "1010.00"
    assert cuerpo["acciones"] == {
        "cerrar": True, "reabrir": False, "editar": True}
    assert espia.ultima("cabecera")[1] == (CORRIDA, fx.SUC_A, None)


def test_the_header_of_an_unknown_tienda_is_a_404(espia):
    espia.cabecera = None
    cliente, _ = _cliente()

    assert cliente.get(TIENDA).status_code == 404


def test_the_events_come_with_who_and_why(espia):
    espia.eventos = [
        fx.evento_pedido(),
        fx.evento_pedido(
            id=2, evento="REABIERTO", motivo="Corrección", usuario=None,
            usuario_id=None)]
    cliente, _ = _cliente()

    respuesta = cliente.get(f"{TIENDA}/eventos")

    assert respuesta.status_code == 200, respuesta.text
    eventos = respuesta.json()
    assert [e["evento"] for e in eventos] == ["CERRADO", "REABIERTO"]
    assert eventos[0]["usuario"] == "Maria"
    assert eventos[1]["motivo"] == "Corrección"
    assert eventos[1]["usuario_id"] is None


def test_the_events_of_an_unknown_tienda_are_a_404(espia):
    espia.eventos = None
    cliente, _ = _cliente()

    assert cliente.get(f"{TIENDA}/eventos").status_code == 404


# --- La lista y el detalle --------------------------------------------------


@pytest.mark.parametrize("filtro", ["abiertos", "por_enviar", "enviados"])
def test_the_list_passes_the_pedidos_filter(espia, filtro):
    cliente, _ = _cliente()

    respuesta = cliente.get(BASE, params={"pedidos": filtro})

    assert respuesta.status_code == 200, respuesta.text
    assert espia.ultima("listar")[2]["pedidos"] == filtro


def test_the_list_without_the_filter_asks_for_none(espia):
    cliente, _ = _cliente()

    cliente.get(BASE)

    assert espia.ultima("listar")[2]["pedidos"] is None


def test_an_unknown_pedidos_filter_is_a_422(espia):
    cliente, _ = _cliente()

    assert cliente.get(
        BASE, params={"pedidos": "todos"}).status_code == 422
    assert espia.llamadas == []


def test_the_list_item_exposes_the_pedido_summary(espia):
    espia.lista = ([fx.item_lista(pedidos={
        "total": 47, "borrador": 34, "cerrados": 10, "enviados": 3,
        "sin_pedido": None})], 1)
    cliente, _ = _cliente()

    item = cliente.get(BASE).json()["items"][0]

    assert item["pedidos"] == {
        "total": 47, "borrador": 34, "cerrados": 10, "enviados": 3,
        "sin_pedido": None}


def test_the_detail_exposes_the_pedido_of_each_sucursal(espia):
    espia.detalle = fx.detalle(
        pedidos={"total": 1, "borrador": 0, "cerrados": 1, "enviados": 0,
                 "sin_pedido": 0},
        sucursales=[fx.sucursal_estado(
            estado_pedido="CERRADO", unidades_a_pedir="15.00",
            valor_a_pedir="1250.00",
            ultimo_evento={"evento": "CERRADO", "usuario": "Maria",
                           "creado_en": fx.CREADA},
            acciones={"cerrar": False, "reabrir": True, "editar": False})])
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{CORRIDA}").json()

    assert cuerpo["pedidos"]["cerrados"] == 1
    uno = cuerpo["sucursales"][0]
    assert uno["estado_pedido"] == "CERRADO"
    assert uno["unidades_a_pedir"] == "15.00"
    assert uno["ultimo_evento"]["usuario"] == "Maria"
    assert uno["acciones"]["reabrir"] is True


# --- Escenarios: sólo ADMIN (E-CORRIDA-062, DM-04) --------------------------


def test_compras_cannot_launch_a_scenario_062(espia):
    cliente, sesion = _cliente("COMPRAS")

    respuesta = cliente.post(BASE, json={
        "fecha_corte": "2026-09-21",
        "overrides": {"consolidar_sustituidas": True}})

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-062"
    assert espia.llamadas == [] and espia.encolados == []
    assert sesion.committed is False


def test_admin_can_launch_a_scenario(espia):
    cliente, _ = _cliente("ADMIN")

    respuesta = cliente.post(BASE, json={
        "fecha_corte": "2026-09-21",
        "overrides": {"consolidar_sustituidas": True}})

    assert respuesta.status_code == 202, respuesta.text
    assert espia.ultima("crear")[2]["overrides"] == {
        "consolidar_sustituidas": True}


@pytest.mark.parametrize("overrides", [None, {}])
def test_compras_with_no_overrides_launches_a_real_corrida(
        espia, overrides):
    cliente, _ = _cliente("COMPRAS")

    respuesta = cliente.post(BASE, json={
        "fecha_corte": "2026-09-21", "overrides": overrides})

    assert respuesta.status_code == 202, respuesta.text
    assert espia.encolados == [CORRIDA]


# --- Superficie -------------------------------------------------------------


def test_the_pedido_router_exposes_exactly_the_planned_operations():
    rutas = {
        (metodo, ruta.path)
        for ruta in corridas_pedido.router.routes for metodo in ruta.methods}

    assert rutas == {
        ("PATCH", "/corridas/{corrida_id}/lineas/{linea_id}"),
        ("GET", "/corridas/{corrida_id}/lineas/{linea_id}/historial"),
        ("POST", "/corridas/{corrida_id}/cerrar"),
        ("GET", "/corridas/{corrida_id}/sucursales/{sucursal_id}"),
        ("GET", "/corridas/{corrida_id}/sucursales/{sucursal_id}/eventos"),
        ("POST", "/corridas/{corrida_id}/sucursales/{sucursal_id}/cerrar"),
        ("POST", "/corridas/{corrida_id}/sucursales/{sucursal_id}/reabrir"),
    }
