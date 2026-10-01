"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-9, spec "API
under /api/motored/corridas"): contrato HTTP de `/corridas`.

Las consultas y el servicio se reemplazan por un doble que graba sus
argumentos (`tests/motored/fixtures/corridas_api.py`): acá se prueba qué
responde cada endpoint, cómo traduce los errores codificados, que crear nunca
calcula en línea y que ninguna ruta edita `pedido_final` ni Z. El RBAC y el
alcance por sucursal están en `test_corridas_rbac.py`; las consultas reales,
en `test_corrida_consultas.py` y en `pg_real/test_corridas_api_pg.py`.
"""
import datetime
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
USUARIO = str(uuid.UUID(int=900))


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "corridas-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "corridas-asc360")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def espia(monkeypatch):
    doble = fx.instalar(monkeypatch)

    async def calcular(*args, **kwargs):
        raise AssertionError("crear nunca calcula en línea")

    monkeypatch.setattr(api.servicio, "calcular_corrida", calcular,
                        raising=False)
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(doble))
    return doble


def _cliente(rol="ADMIN"):
    sesion = FakeAsyncSession(execute_queue=[[]] * 8)
    override_motored_user(MotoredUser(user_id=USUARIO, role=rol))
    override_motored_db(sesion)
    return TestClient(app), sesion


CUERPO = {"fecha_corte": "2026-09-21"}


# --- POST /corridas ---------------------------------------------------------


def test_creating_a_corrida_answers_202_with_its_identity(espia):
    cliente, _ = _cliente()

    respuesta = cliente.post(BASE, json=CUERPO)

    assert respuesta.status_code == 202, respuesta.text
    assert respuesta.json() == {
        "id": str(fx.CORRIDA_ID), "codigo": "PED-2026-S39-001",
        "estado": "PENDIENTE", "es_escenario": False}


def test_the_request_is_forwarded_to_the_service(espia):
    cliente, _ = _cliente("COMPRAS")
    cuerpo = {
        "fecha_corte": "2026-09-21",
        "sucursal_ids": [str(fx.SUC_A), str(fx.SUC_B)],
        "overrides": {"consolidar_sustituidas": True},
        "nota": "  corrida de prueba  "}

    cliente.post(BASE, json=cuerpo)

    _, _, kw = espia.ultima("crear")
    assert kw["fecha_corte"] == datetime.date(2026, 9, 21)
    assert kw["sucursal_ids"] == [fx.SUC_A, fx.SUC_B]
    assert kw["overrides"] == {"consolidar_sustituidas": True}
    assert kw["nota"] == "corrida de prueba"
    assert str(kw["usuario_id"]) == USUARIO


def test_omitted_scope_and_overrides_reach_the_service_as_none(espia):
    cliente, _ = _cliente()

    cliente.post(BASE, json=CUERPO)

    _, _, kw = espia.ultima("crear")
    assert kw["sucursal_ids"] is None and kw["overrides"] is None
    assert kw["nota"] is None


def test_a_blank_nota_is_dropped(espia):
    cliente, _ = _cliente()

    cliente.post(BASE, json={**CUERPO, "nota": "   "})

    assert espia.ultima("crear")[2]["nota"] is None


def test_the_corrida_is_committed_before_it_is_enqueued(espia):
    cliente, sesion = _cliente()
    visto = []

    class Runner:
        async def enqueue(self, corrida_id):
            visto.append((corrida_id, sesion.committed))

    app.dependency_overrides[api.get_corrida_runner] = lambda: Runner()

    cliente.post(BASE, json=CUERPO)

    assert visto == [(fx.CORRIDA_ID, True)]


def test_a_scenario_corrida_reports_it(espia):
    espia.creada.es_escenario = True
    espia.creada.codigo = "ESC-2026-S39-001"
    cliente, _ = _cliente()

    cuerpo = cliente.post(BASE, json=CUERPO).json()

    assert cuerpo["es_escenario"] is True
    assert cuerpo["codigo"] == "ESC-2026-S39-001"


def test_a_runner_failure_does_not_lose_the_committed_corrida(espia):
    app.dependency_overrides[api.get_corrida_runner] = (
        lambda: fx.RunnerDoble(espia, falla=True))
    cliente, sesion = _cliente()

    respuesta = cliente.post(BASE, json=CUERPO)

    assert respuesta.status_code == 202
    assert sesion.committed is True


@pytest.mark.parametrize("codigo", [
    codigos.E_CORRIDA_CORTE_FUTURO,
    codigos.E_CORRIDA_VENTAS_SIN_CUBRIR,
    codigos.E_CORRIDA_INVENTARIO_AUSENTE,
    codigos.E_CORRIDA_INVENTARIO_VIEJO,
    codigos.E_CORRIDA_BACKORDER_AUSENTE,
    codigos.E_CORRIDA_BACKORDER_VIEJO,
    codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA,
    codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO,
    codigos.E_CORRIDA_MAESTRO_REFERENCIAS_AUSENTE,
    codigos.E_CORRIDA_OVERRIDE_INVALIDO,
    codigos.E_CORRIDA_SUCURSAL_INVALIDA,
])
def test_a_creation_error_is_a_coded_422(espia, codigo):
    espia.error = ({"crear"}, ErrorCorrida(codigo, "mensaje en español"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(BASE, json=CUERPO)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "mensaje en español"}
    assert sesion.committed is False and sesion.rolled_back is True
    assert espia.encolados == []


def test_a_staleness_rejection_carries_the_age_block_per_type(espia):
    detalle = {"antiguedad": {"inventario": {
        "carga_id": None, "fecha_usada": "2026-09-01", "antiguedad_dias": 20,
        "limite_dias": 7, "fuente_limite": "DEFAULT"}}, "errores": []}
    espia.error = ({"crear"}, ErrorCorrida(
        codigos.E_CORRIDA_INVENTARIO_VIEJO, "datos viejos", detalle))
    cliente, _ = _cliente()

    cuerpo = cliente.post(BASE, json=CUERPO).json()["detail"]

    assert cuerpo["code"] == "E-CORRIDA-003"
    assert cuerpo["detalle"]["antiguedad"]["inventario"][
        "antiguedad_dias"] == 20


@pytest.mark.parametrize("cuerpo", [
    {},
    {"fecha_corte": "no-es-fecha"},
    {"fecha_corte": "2026-13-45"},
    {"fecha_corte": "2026-09-21", "sucursal_ids": []},
    {"fecha_corte": "2026-09-21", "sucursal_ids": ["no-uuid"]},
    {"fecha_corte": "2026-09-21", "pedido_final": 10},
    {"fecha_corte": "2026-09-21", "nota": "x" * 501},
])
def test_an_invalid_body_is_rejected_before_any_work(espia, cuerpo):
    cliente, sesion = _cliente()

    respuesta = cliente.post(BASE, json=cuerpo)

    assert respuesta.status_code == 422
    assert espia.llamadas == [] and espia.encolados == []
    assert sesion.committed is False


# --- GET /corridas ----------------------------------------------------------


def test_the_list_returns_a_page(espia):
    espia.lista = ([fx.item_lista(), fx.item_lista(
        id=uuid.UUID(int=502), codigo="ESC-2026-S39-001",
        es_escenario=True)], 7)
    cliente, _ = _cliente()

    cuerpo = cliente.get(BASE).json()

    assert cuerpo["total"] == 7 and cuerpo["limite"] == 50
    assert cuerpo["offset"] == 0
    assert [i["codigo"] for i in cuerpo["items"]] == [
        "PED-2026-S39-001", "ESC-2026-S39-001"]
    assert cuerpo["items"][0]["fecha_corte"] == "2026-09-21"


def test_the_list_filters_are_forwarded(espia):
    cliente, _ = _cliente()

    cliente.get(BASE, params={
        "proveedor_id": str(fx.PROVEEDOR_ID), "estado": "CERRADA",
        "desde": "2026-09-01", "hasta": "2026-09-30", "escenario": "true",
        "limite": 20, "offset": 40})

    _, _, kw = espia.ultima("listar")
    assert kw == {
        "alcance": None, "proveedor_id": fx.PROVEEDOR_ID,
        "estado": "CERRADA", "desde": datetime.date(2026, 9, 1),
        "hasta": datetime.date(2026, 9, 30), "escenario": True,
        "limite": 20, "offset": 40}


def test_the_list_defaults_do_not_filter(espia):
    cliente, _ = _cliente()

    cliente.get(BASE)

    _, _, kw = espia.ultima("listar")
    assert kw["proveedor_id"] is None and kw["estado"] is None
    assert kw["escenario"] is None and (kw["limite"], kw["offset"]) == (50, 0)


@pytest.mark.parametrize("params", [
    {"limite": 201}, {"limite": 0}, {"offset": -1},
    {"estado": "INVENTADO"}, {"desde": "ayer"},
    {"proveedor_id": "no-uuid"},
])
def test_invalid_list_params_are_rejected(espia, params):
    cliente, _ = _cliente()

    assert cliente.get(BASE, params=params).status_code == 422
    assert espia.llamadas == []


# --- GET /corridas/{id} -----------------------------------------------------


def test_the_detail_shows_the_age_of_every_input_at_the_top_level(espia):
    espia.detalle = fx.detalle(antiguedad={
        tipo: {"carga_id": str(uuid.uuid4()), "fecha_usada": "2026-09-19",
               "antiguedad_dias": dias, "limite_dias": 7,
               "fuente_limite": "DEFAULT"}
        for tipo, dias in (
            ("inventario", 2), ("backorder", 3), ("facturas", 1),
            ("ingresos", 1))})
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{fx.CORRIDA_ID}").json()

    assert set(cuerpo["antiguedad"]) == {
        "inventario", "backorder", "facturas", "ingresos"}
    assert cuerpo["antiguedad"]["backorder"]["antiguedad_dias"] == 3
    assert cuerpo["antiguedad"]["backorder"]["limite_dias"] == 7


def test_the_detail_groups_the_used_cargas_by_type(espia):
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{fx.CORRIDA_ID}").json()

    (venta,) = cuerpo["cargas_usadas"]["VENTAS"]
    assert venta["nombre_archivo"] == "ventas.xlsx"
    assert venta["periodo_hasta"] == "2026-09-14"


def test_the_detail_carries_status_warnings_and_resumen(espia):
    espia.detalle = fx.detalle(
        sucursales=[
            fx.sucursal_estado(),
            fx.sucursal_estado(
                fx.SUC_B, "DOS", orden=2, estado="OMITIDA",
                codigo="A-CORRIDA-102", lineas=0)],
        advertencias=[{
            "sucursal_id": fx.SUC_B, "sucursal": "DOS",
            "codigo": "A-CORRIDA-102", "mensaje": "abrió hace poco"}],
        resumen=[{
            "sucursal_id": fx.SUC_A, "clase": "AF",
            "unidades": "50.00", "referencias": 1, "valor": "23037.50",
            "porcentaje_peso": "1.000000"}],
        resumen_por_clase=[{
            "sucursal_id": None, "clase": "AF", "unidades": "50.00",
            "referencias": 1, "valor": "23037.50",
            "porcentaje_peso": "1.000000"}],
        totales={"unidades": "50.00", "referencias": 1,
                 "valor": "23037.50"})
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{fx.CORRIDA_ID}").json()

    assert [s["estado"] for s in cuerpo["sucursales"]] == ["OK", "OMITIDA"]
    assert cuerpo["advertencias"][0]["codigo"] == "A-CORRIDA-102"
    assert cuerpo["resumen"][0]["valor"] == "23037.50"
    assert cuerpo["resumen_por_clase"][0]["sucursal_id"] is None
    assert cuerpo["totales"] == {
        "unidades": "50.00", "referencias": 1, "valor": "23037.50"}


def test_an_unknown_corrida_is_a_404(espia):
    espia.detalle = None
    cliente, _ = _cliente()

    assert cliente.get(f"{BASE}/{uuid.uuid4()}").status_code == 404


def test_a_malformed_corrida_id_is_a_422(espia):
    cliente, _ = _cliente()

    assert cliente.get(f"{BASE}/no-es-uuid").status_code == 422
    assert espia.llamadas == []


# --- GET /corridas/{id}/progreso --------------------------------------------


def test_the_progress_payload(espia):
    espia.progreso = fx.progreso(
        errores=[{"sucursal_id": fx.SUC_B, "sucursal": "DOS",
                  "codigo": "E-CORRIDA-021", "mensaje": "sin SIC"}],
        advertencias=[{"sucursal_id": None, "sucursal": None,
                       "codigo": "A-CORRIDA-101", "mensaje": "sin perdida"}])
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{fx.CORRIDA_ID}/progreso").json()

    assert set(cuerpo) == {
        "estado", "total", "procesadas", "ok", "omitidas", "fallidas",
        "actual", "latido_en", "intentos", "errores", "advertencias"}
    assert cuerpo["actual"] == "Sucursal 2 de 2 — DOS"
    assert cuerpo["errores"][0]["codigo"] == "E-CORRIDA-021"
    assert cuerpo["advertencias"][0]["sucursal_id"] is None


def test_the_progress_of_an_unknown_corrida_is_a_404(espia):
    espia.progreso = None
    cliente, _ = _cliente()

    assert cliente.get(
        f"{BASE}/{uuid.uuid4()}/progreso").status_code == 404


# --- GET /corridas/{id}/lineas ----------------------------------------------


def test_the_lines_come_paginated_with_exact_decimals(espia):
    espia.lineas = ([fx.linea(), fx.linea(codigo="OTRA-1")], 120)
    cliente, _ = _cliente()

    cuerpo = cliente.get(f"{BASE}/{fx.CORRIDA_ID}/lineas").json()

    assert cuerpo["total"] == 120 and cuerpo["offset"] == 0
    assert cuerpo["limite"] == 500
    assert [i["codigo_referencia"] for i in cuerpo["items"]] == [
        "94109-12000S", "OTRA-1"]
    assert cuerpo["items"][0]["pedido_sugerido"] == "50.00"
    assert cuerpo["items"][0]["pedido_final"] == "50.00"


def test_the_line_filters_are_forwarded(espia):
    cliente, _ = _cliente()

    cliente.get(f"{BASE}/{fx.CORRIDA_ID}/lineas", params={
        "sucursal_id": str(fx.SUC_A), "incluir_excluidas": "true",
        "clase": "AF", "estado_quiebre": "QUIEBRE_TOTAL",
        "limite": 2000, "offset": 10})

    _, args, kw = espia.ultima("lineas")
    assert args == (fx.CORRIDA_ID, None)
    assert kw == {
        "sucursal_id": fx.SUC_A, "incluir_excluidas": True, "clase": "AF",
        "estado_quiebre": "QUIEBRE_TOTAL", "limite": 2000, "offset": 10,
        "q": None, "solo_editadas": False, "solo_fuera_empaque": False}


def test_excluded_lines_are_left_out_by_default(espia):
    cliente, _ = _cliente()

    cliente.get(f"{BASE}/{fx.CORRIDA_ID}/lineas")

    kw = espia.ultima("lineas")[2]
    assert kw["incluir_excluidas"] is False
    assert kw["sucursal_id"] is None and kw["clase"] is None


@pytest.mark.parametrize("params", [
    {"limite": 2001}, {"limite": 0}, {"offset": -5},
    {"sucursal_id": "no-uuid"},
])
def test_invalid_line_params_are_rejected(espia, params):
    cliente, _ = _cliente()

    assert cliente.get(
        f"{BASE}/{fx.CORRIDA_ID}/lineas", params=params).status_code == 422
    assert espia.llamadas == []


def test_the_lines_of_an_unknown_corrida_are_a_404(espia):
    espia.lineas = None
    cliente, _ = _cliente()

    assert cliente.get(
        f"{BASE}/{uuid.uuid4()}/lineas").status_code == 404


# --- POST /cerrar y /anular -------------------------------------------------


def test_closing_a_corrida(espia):
    cliente, sesion = _cliente("COMPRAS")

    respuesta = cliente.post(f"{BASE}/{fx.CORRIDA_ID}/cerrar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "CERRADA"
    _, args, _ = espia.ultima("cerrar")
    assert args == (fx.CORRIDA_ID, uuid.UUID(USUARIO))
    assert sesion.committed is True


@pytest.mark.parametrize("codigo", [
    codigos.E_CORRIDA_ESTADO_NO_ADMITE,
    codigos.E_CORRIDA_INVALIDADA,
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
    codigos.E_CORRIDA_SUCURSAL_FALLIDA,
])
def test_a_refused_close_is_a_coded_409(espia, codigo):
    espia.error = ({"cerrar"}, ErrorCorrida(codigo, "no se puede cerrar"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(f"{BASE}/{fx.CORRIDA_ID}/cerrar")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "no se puede cerrar"}
    assert sesion.committed is False and sesion.rolled_back is True


def test_closing_an_unknown_corrida_is_a_404(espia):
    espia.error = ({"cerrar"}, LookupError("no existe"))
    cliente, _ = _cliente()

    assert cliente.post(
        f"{BASE}/{uuid.uuid4()}/cerrar").status_code == 404


def test_annulling_a_corrida_keeps_the_reason(espia):
    cliente, sesion = _cliente()

    respuesta = cliente.post(
        f"{BASE}/{fx.CORRIDA_ID}/anular", json={"motivo": "  datos viejos "})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "ANULADA"
    _, args, _ = espia.ultima("anular")
    assert args == (fx.CORRIDA_ID, uuid.UUID(USUARIO), "datos viejos")
    assert sesion.committed is True


@pytest.mark.parametrize("cuerpo", [
    None, {}, {"motivo": ""}, {"motivo": "  "}, {"motivo": "x" * 501}])
def test_annulling_needs_a_reason(espia, cuerpo):
    cliente, _ = _cliente()

    respuesta = cliente.post(f"{BASE}/{fx.CORRIDA_ID}/anular", json=cuerpo)

    assert respuesta.status_code == 422
    assert espia.llamadas == []


def test_a_refused_annulment_is_a_coded_409(espia):
    espia.error = ({"anular"}, ErrorCorrida(
        codigos.E_CORRIDA_ESTADO_NO_ADMITE, "ya está cerrada"))
    cliente, sesion = _cliente()

    respuesta = cliente.post(
        f"{BASE}/{fx.CORRIDA_ID}/anular", json={"motivo": "porque sí"})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "E-CORRIDA-040"
    assert sesion.rolled_back is True


def test_annulling_an_unknown_corrida_is_a_404(espia):
    espia.error = ({"anular"}, LookupError("no existe"))
    cliente, _ = _cliente()

    assert cliente.post(
        f"{BASE}/{uuid.uuid4()}/anular",
        json={"motivo": "no existe"}).status_code == 404


# --- Superficie -------------------------------------------------------------


def test_the_router_exposes_exactly_the_planned_operations():
    rutas = {
        (metodo, ruta.path)
        for ruta in api.router.routes for metodo in ruta.methods}

    assert rutas == {
        ("POST", "/corridas"), ("GET", "/corridas"),
        ("GET", "/corridas/{corrida_id}"),
        ("GET", "/corridas/{corrida_id}/progreso"),
        ("GET", "/corridas/{corrida_id}/lineas"),
        ("POST", "/corridas/{corrida_id}/cerrar"),
        ("POST", "/corridas/{corrida_id}/anular"),
    }


def test_no_route_edits_the_order_quantity_or_the_adjustment():
    rutas = " ".join(ruta.path for ruta in api.router.routes)

    assert "pedido" not in rutas and "ajuste" not in rutas
    assert all(
        metodo in ("GET", "POST")
        for ruta in api.router.routes for metodo in ruta.methods)


def test_the_router_is_mounted_under_the_motored_prefix(espia):
    cliente, _ = _cliente()

    assert cliente.get(BASE).status_code == 200
