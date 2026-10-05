"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3, spec
ED-01..ED-27): edición de líneas, historial y lecturas.

Tres capas sin base viva. La API (`PATCH /lineas/{id}`, `GET .../historial`
y los filtros de `GET /lineas`) se prueba con los dobles de
`fixtures/corridas_api.py`: qué se le pide al servicio, cómo se traducen los
errores codificados y cómo se serializa lo que vuelve. Las consultas y las
proyecciones puras se prueban con el SQL literal y con filas de juguete. El
comportamiento transaccional del servicio (bloqueos, historial atómico,
carreras) corre contra Postgres real en
`pg_real/test_pedido_edicion_pg.py`.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.api import corridas as api
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import codigos
from app.motored.services.corridas import consultas as cq
from app.motored.services.corridas import proyecciones as pr
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.corridas.edicion import ResultadoEdicion
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)
from tests.motored.fixtures import corridas_api as fx
from tests.motored.test_corrida_consultas import _corrida, _suc

BASE = "/api/motored/corridas"
USUARIO = str(uuid.UUID(int=900))
LINEA_URL = f"{BASE}/{fx.CORRIDA_ID}/lineas/7"
D = Decimal
EDICION = pr.UltimaEdicion(
    usuario="Maria", creado_en=fx.CREADA, motivo="MANUAL")


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "edicion-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "edicion-asc360")
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


def _sql(sentencia) -> str:
    # `paramstyle="named"`: con el estilo por defecto el literal duplica `%`.
    return str(sentencia.compile(
        dialect=postgresql.dialect(paramstyle="named"),
        compile_kwargs={"literal_binds": True}))


# --- PATCH /lineas/{id} -----------------------------------------------------


def test_an_edit_answers_the_line_with_value_edit_marks_and_totals(espia):
    espia.editada = fx.resultado_edicion(ultima_edicion=EDICION)
    cliente, _ = _cliente()

    respuesta = cliente.patch(LINEA_URL, json={"pedido_final": 60})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    linea = cuerpo["linea"]
    assert linea["id"] == 7
    assert (linea["pedido_sugerido"], linea["pedido_final"]) == (
        "50.00", "60.00")
    assert linea["valor_pedido"] == "27645.00"
    assert linea["valor_sugerido"] == "23037.50"
    assert linea["editada"] is True
    assert linea["editado_por"] == "Maria"
    assert linea["motivo_edicion"] == "MANUAL"
    assert cuerpo["totales_tienda"] == {
        "unidades_a_pedir": "1010.00", "valor_a_pedir": "6000000.00",
        "unidades_sugerido": "1000.00", "valor_sugerido": "5000000.00"}


def test_the_edit_reaches_the_service_with_the_raw_payload_and_the_user(
        espia):
    cliente, sesion = _cliente()

    cliente.patch(LINEA_URL, json={"pedido_final": 60, "esperado": "50.00"})

    _, args, _ = espia.ultima("editar")
    assert args == (
        fx.CORRIDA_ID, 7, 60, D("50.00"), uuid.UUID(USUARIO))
    assert sesion.committed is True


@pytest.mark.parametrize("bruto", ["abc", -1, 2.5, None, 10_000_000])
def test_the_quantity_is_forwarded_unvalidated_so_the_service_codes_it(
        espia, bruto):
    cliente, _ = _cliente()

    cliente.patch(LINEA_URL, json={"pedido_final": bruto})

    assert espia.ultima("editar")[1][2] == bruto


def test_a_missing_quantity_reaches_the_service_as_none(espia):
    cliente, _ = _cliente()

    cliente.patch(LINEA_URL, json={})

    assert espia.ultima("editar")[1][2] is None


def test_an_unknown_body_field_is_rejected_before_the_service(espia):
    cliente, _ = _cliente()

    respuesta = cliente.patch(
        LINEA_URL, json={"pedido_final": 5, "ajuste": 3})

    assert respuesta.status_code == 422
    assert espia.llamadas == []


def test_the_pack_warning_follows_the_stored_quantity(espia):
    espia.editada = fx.resultado_edicion(linea=fx.linea(
        id=7, pedido_final=D("30.00"), unidad_empaque=12))
    cliente, _ = _cliente()

    linea = cliente.patch(
        LINEA_URL, json={"pedido_final": 30}).json()["linea"]

    assert linea["fuera_de_empaque"] is True


def test_a_never_edited_line_has_no_edit_marks(espia):
    espia.editada = fx.resultado_edicion(linea=fx.linea(
        id=7, pedido_final=D("50.00"), pedido_sugerido=D("50.00")))
    cliente, _ = _cliente()

    linea = cliente.patch(
        LINEA_URL, json={"pedido_final": 50}).json()["linea"]

    assert linea["editada"] is False
    assert linea["editado_por"] is None and linea["editado_en"] is None
    assert linea["fuera_de_empaque"] is False


@pytest.mark.parametrize("codigo,estado", [
    (codigos.E_CORRIDA_ESTADO_NO_ADMITE, 409),
    (codigos.E_CORRIDA_INVALIDADA, 409),
    (codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA, 409),
    (codigos.E_CORRIDA_PEDIDO_NO_BORRADOR, 409),
    (codigos.E_CORRIDA_LINEA_EXCLUIDA, 409),
    (codigos.E_CORRIDA_EDICION_DESACTUALIZADA, 409),
    (codigos.E_CORRIDA_CANTIDAD_INVALIDA, 422),
])
def test_a_coded_rule_error_keeps_its_status_and_rolls_back(
        espia, codigo, estado):
    espia.error = ({"editar"}, ErrorCorrida(codigo, "mensaje en español"))
    cliente, sesion = _cliente()

    respuesta = cliente.patch(LINEA_URL, json={"pedido_final": 60})

    assert respuesta.status_code == estado
    assert respuesta.json()["detail"] == {
        "code": codigo, "message": "mensaje en español"}
    assert sesion.rolled_back is True and sesion.committed is False


def test_an_unknown_corrida_or_line_is_a_404_with_its_message(espia):
    espia.error = ({"editar"}, LookupError("Línea no encontrada."))
    cliente, sesion = _cliente()

    respuesta = cliente.patch(LINEA_URL, json={"pedido_final": 60})

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Línea no encontrada."
    assert sesion.rolled_back is True


def test_a_non_numeric_line_id_is_a_422(espia):
    cliente, _ = _cliente()

    respuesta = cliente.patch(
        f"{BASE}/{fx.CORRIDA_ID}/lineas/abc", json={"pedido_final": 1})

    assert respuesta.status_code == 422 and espia.llamadas == []


# --- GET /lineas/{id}/historial ---------------------------------------------


def test_the_history_lists_the_rows_oldest_first_with_the_user_name(espia):
    espia.historial = [
        fx.historial_fila(id=1, valor_anterior=D("50.00"),
                          valor_nuevo=D("60.00")),
        fx.historial_fila(id=2, valor_anterior=D("60.00"),
                          valor_nuevo=D("55.00"), usuario="Pedro")]
    cliente, _ = _cliente()

    respuesta = cliente.get(f"{LINEA_URL}/historial")

    assert respuesta.status_code == 200, respuesta.text
    filas = respuesta.json()
    assert [f["id"] for f in filas] == [1, 2]
    assert filas[1]["valor_anterior"] == "60.00"
    assert filas[1]["valor_nuevo"] == "55.00"
    assert (filas[1]["usuario"], filas[1]["motivo"]) == ("Pedro", "MANUAL")
    assert espia.ultima("historial")[1] == (fx.CORRIDA_ID, 7)


def test_a_line_that_was_never_edited_has_an_empty_history(espia):
    espia.historial = []
    cliente, _ = _cliente()

    assert cliente.get(f"{LINEA_URL}/historial").json() == []


def test_the_history_of_an_unknown_line_is_a_404(espia):
    espia.historial = None
    cliente, _ = _cliente()

    assert cliente.get(f"{LINEA_URL}/historial").status_code == 404


# --- GET /lineas: filtros y marcas de edición --------------------------------


def test_the_new_line_filters_reach_the_query_layer(espia):
    cliente, _ = _cliente()

    cliente.get(f"{BASE}/{fx.CORRIDA_ID}/lineas", params={
        "q": "filtro", "solo_editadas": "true",
        "solo_fuera_empaque": "true"})

    kw = espia.ultima("lineas")[2]
    assert kw["q"] == "filtro"
    assert kw["solo_editadas"] is True and kw["solo_fuera_empaque"] is True


def test_the_line_filters_default_to_off(espia):
    cliente, _ = _cliente()

    cliente.get(f"{BASE}/{fx.CORRIDA_ID}/lineas")

    kw = espia.ultima("lineas")[2]
    assert kw["q"] is None
    assert kw["solo_editadas"] is False and kw["solo_fuera_empaque"] is False


def test_a_blank_search_is_dropped(espia):
    cliente, _ = _cliente()

    cliente.get(f"{BASE}/{fx.CORRIDA_ID}/lineas", params={"q": "   "})

    assert espia.ultima("lineas")[2]["q"] is None


def test_each_listed_line_carries_its_id_edit_marks_and_pack_flag(espia):
    espia.lineas = ([
        fx.linea(id=7, pedido_sugerido=D("50.00"), pedido_final=D("60.00"),
                 precio=D("460.75"), unidad_empaque=12),
        fx.linea(id=8, codigo="B", pedido_sugerido=D("12.00"),
                 pedido_final=D("12.00"), precio=D("10.00"),
                 unidad_empaque=12)], 2)
    espia.ediciones = {7: EDICION}
    cliente, _ = _cliente()

    items = cliente.get(
        f"{BASE}/{fx.CORRIDA_ID}/lineas").json()["items"]

    primera, segunda = items
    assert (primera["id"], primera["editada"], primera["editado_por"]) == (
        7, True, "Maria")
    assert primera["valor_sugerido"] == "23037.50"
    assert primera["fuera_de_empaque"] is False
    assert (segunda["id"], segunda["editada"], segunda["editado_por"]) == (
        8, False, None)
    assert segunda["valor_sugerido"] == "120.00"


# --- proyecciones puras ------------------------------------------------------


def test_extras_of_an_edited_line_with_pack_warning():
    linea = fx.linea(
        pedido_sugerido=D("50.00"), pedido_final=D("30.00"),
        precio=D("100.00"), unidad_empaque=12)

    extras = pr.extras_linea(linea, EDICION)

    assert extras == {
        "valor_sugerido": D("5000.00"), "fuera_de_empaque": True,
        "editada": True, "editado_por": "Maria",
        "editado_en": fx.CREADA, "motivo_edicion": "MANUAL"}


def test_editing_back_to_the_suggestion_clears_the_flag_but_keeps_the_who():
    linea = fx.linea(
        pedido_sugerido=D("50.00"), pedido_final=D("50.00"),
        precio=D("100.00"), unidad_empaque=1)

    extras = pr.extras_linea(linea, EDICION)

    assert extras["editada"] is False
    assert extras["editado_por"] == "Maria"


def test_extras_of_an_excluded_line_are_neutral():
    linea = fx.linea(
        pedido_sugerido=None, pedido_final=None, precio=None,
        motivo_exclusion="SUSTITUIDA")

    extras = pr.extras_linea(linea, None)

    assert extras["editada"] is False and extras["fuera_de_empaque"] is False
    assert str(extras["valor_sugerido"]) == "0.00"


def _fila_a_pedir(sucursal, clase, unidades, referencias, valor):
    return SimpleNamespace(
        sucursal_id=sucursal, clase=clase, unidades=D(unidades),
        referencias=referencias, valor=D(valor))


def _suc_orden(sucursal_id, orden):
    return SimpleNamespace(sucursal_id=sucursal_id, orden=orden)


def test_the_a_pedir_summary_adds_a_total_row_and_weights_sum_to_100():
    filas = [
        _fila_a_pedir(fx.SUC_A, "AF", "60", 2, "600"),
        _fila_a_pedir(fx.SUC_A, "CF", "40", 3, "400"),
        _fila_a_pedir(fx.SUC_B, "BM", "10", 1, "50")]
    sucursales = [
        _suc_orden(fx.SUC_A, 1), _suc_orden(fx.SUC_B, 2)]

    resumen, totales = pr.resumen_a_pedir(filas, sucursales)

    de_a = [f for f in resumen if f["sucursal_id"] == fx.SUC_A]
    assert [f["clase"] for f in de_a] == ["AF", "CF", "TOTAL"]
    total_a = de_a[-1]
    assert (total_a["unidades"], total_a["referencias"], total_a["valor"]) == (
        D("100"), 5, D("1000"))
    assert sum(f["porcentaje_peso"] for f in de_a[:-1]) == D("1")
    assert total_a["porcentaje_peso"] == D("1")
    assert totales == {
        "unidades": D("110"), "referencias": 6, "valor": D("1050")}


def test_a_sucursal_with_zero_units_has_zero_weights_not_a_division_error():
    filas = [_fila_a_pedir(fx.SUC_A, "AF", "0", 2, "0")]

    resumen, totales = pr.resumen_a_pedir(filas, [_suc_orden(fx.SUC_A, 1)])

    assert [f["porcentaje_peso"] for f in resumen] == [D("0"), D("0")]
    assert totales["unidades"] == D("0")


def test_no_a_pedir_rows_give_an_empty_summary_and_zero_totals():
    resumen, totales = pr.resumen_a_pedir([], [])

    assert resumen == []
    assert totales == {"unidades": D("0"), "referencias": 0, "valor": D("0")}


def test_the_detail_exposes_the_a_pedir_next_to_the_untouched_sugerido():
    filas = [_fila_a_pedir(fx.SUC_A, "AF", "60", 2, "600")]

    detalle = pr.armar_detalle(
        _corrida(), [_suc(fx.SUC_A, "UNO", 1)], [], [], None, filas)

    assert detalle["totales"]["unidades"] == D("0")
    assert detalle["totales_a_pedir"]["unidades"] == D("60")
    assert [f["clase"] for f in detalle["resumen_a_pedir"]] == [
        "AF", "TOTAL"]


# --- consultas: SQL ---------------------------------------------------------


async def _lineas(db, **campos):
    base = dict(
        sucursal_id=None, incluir_excluidas=False, clase=None,
        estado_quiebre=None, limite=500, offset=0)
    return await cq.lineas(
        db, fx.CORRIDA_ID, None, **{**base, **campos})


async def _sql_de_lineas(**campos):
    db = FakeAsyncSession(execute_queue=[[fx.CORRIDA_ID], [0], []])
    await _lineas(db, **campos)
    return [_sql(s) for s in db.executed_statements[1:]]


async def test_q_is_a_case_insensitive_substring_over_code_and_name():
    for sql in await _sql_de_lineas(q="filtro"):
        assert "corrida_linea.codigo_referencia ILIKE '%filtro%'" in sql
        assert "corrida_linea.nombre_parte ILIKE '%filtro%'" in sql


async def test_q_escapes_like_wildcards_so_they_match_literally():
    for sql in await _sql_de_lineas(q="100%_x"):
        assert "ILIKE '%100\\%\\_x%' ESCAPE '\\'" in sql


async def test_without_q_there_is_no_like_clause():
    for sql in await _sql_de_lineas():
        assert "ILIKE" not in sql


async def test_solo_editadas_requires_a_history_row_for_the_line():
    for sql in await _sql_de_lineas(solo_editadas=True):
        assert "EXISTS (SELECT" in sql
        assert "corrida_linea_historial.linea_id = corrida_linea.id" in sql


async def test_solo_fuera_empaque_filters_positive_non_multiples():
    for sql in await _sql_de_lineas(solo_fuera_empaque=True):
        assert "corrida_linea.pedido_final > 0" in sql
        assert "corrida_linea.unidad_empaque > 0" in sql
        assert (
            "corrida_linea.pedido_final % corrida_linea.unidad_empaque"
            in sql)


async def test_the_filters_combine_with_the_existing_ones():
    for sql in await _sql_de_lineas(
            q="a", clase="CF", solo_editadas=True, solo_fuera_empaque=True):
        assert "corrida_linea.clase = 'CF'" in sql
        assert "ILIKE" in sql and "corrida_linea_historial" in sql
        assert "unidad_empaque > 0" in sql


async def test_the_last_edit_of_each_line_is_one_distinct_on_query():
    fila = pr.UltimaEdicion("Maria", fx.CREADA, "MANUAL")
    db = FakeAsyncSession(execute_queue=[[
        (7, "Maria", fx.CREADA, "MANUAL")]])

    ediciones = await cq.ediciones_de(db, [7, 8])

    sql = _sql(db.executed_statements[0])
    assert "DISTINCT ON (corrida_linea_historial.linea_id)" in sql
    assert "JOIN usuario" in sql
    assert "corrida_linea_historial.linea_id IN (7, 8)" in sql
    assert "creado_en DESC" in sql
    assert ediciones == {7: fila}


async def test_no_lines_means_no_edit_query():
    db = FakeAsyncSession(execute_queue=[])

    assert await cq.ediciones_de(db, []) == {}
    assert db.executed_statements == []


async def test_the_history_is_read_oldest_first_with_the_user_name():
    fila = (1, 7, "pedido_final", D("50.00"), D("60.00"), "MANUAL", None,
            fx.USUARIO_EDITOR, "Maria", fx.CREADA)
    db = FakeAsyncSession(execute_queue=[[7], [fila]])

    filas = await cq.historial_linea(db, fx.CORRIDA_ID, 7)

    sql = _sql(db.executed_statements[1])
    assert "ORDER BY corrida_linea_historial.creado_en ASC" in sql
    assert filas[0]["usuario"] == "Maria"
    assert filas[0]["valor_nuevo"] == D("60.00")


async def test_the_history_of_a_line_outside_the_corrida_is_none():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await cq.historial_linea(db, fx.CORRIDA_ID, 99) is None
    assert len(db.executed_statements) == 1


async def test_the_detail_also_reads_a_pedir_grouped_by_sucursal_and_class():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(fx.SUC_A, "UNO", 1)], [], [],
        [_fila_a_pedir(fx.SUC_A, "AF", "60", 2, "600")], [], []])

    detalle = await cq.detalle(db, fx.CORRIDA_ID, None)

    sql = _sql(db.executed_statements[4])
    assert "GROUP BY corrida_linea.sucursal_id, corrida_linea.clase" in sql
    assert "corrida_linea.motivo_exclusion IS NULL" in sql
    assert detalle["totales_a_pedir"]["unidades"] == D("60")


def test_resultado_edicion_is_the_service_contract():
    assert ResultadoEdicion._fields == (
        "linea", "ultima_edicion", "totales_tienda")


def test_the_edit_codes_are_the_design_numbers():
    assert codigos.E_CORRIDA_PEDIDO_NO_BORRADOR == "E-CORRIDA-052"
    assert codigos.E_CORRIDA_CANTIDAD_INVALIDA == "E-CORRIDA-053"
    assert codigos.E_CORRIDA_LINEA_EXCLUIDA == "E-CORRIDA-054"
    assert codigos.E_CORRIDA_EDICION_DESACTUALIZADA == "E-CORRIDA-066"
