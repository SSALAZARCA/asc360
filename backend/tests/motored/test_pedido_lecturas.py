"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3a, ADR-1, ADR-3,
spec CI-01, CI-03, DM-03): lo que la lista y el detalle de la corrida dicen
del pedido de cada tienda.

Dos capas, como `test_corrida_consultas.py`: las proyecciones puras (acciones
permitidas, resumen "3 de 47 enviadas", cifras a pedir y último evento de
cada tienda) y las consultas con una sesión de juguete y el SQL literal (el
resumen de la lista, el filtro `pedidos`, la cabecera de una tienda y su línea
de tiempo). Las mismas consultas contra Postgres real corren en
`pg_real/test_pedido_tienda_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import consultas as cq
from app.motored.services.corridas import lecturas_pedido as lp
from app.motored.services.corridas import proyecciones as pr
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx
from tests.motored.test_corrida_consultas import (
    SUC_C,
    _corrida,
    _fila_lista,
    _res,
    _suc,
)

SUC_A, SUC_B = fx.SUC_A, fx.SUC_B
D = Decimal
AHORA = datetime.datetime(2026, 9, 22, 9, 30)


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _pedir(sucursal_id, clase, unidades, valor="0"):
    """Una fila de `consultas._a_pedir`: lo agrupado por sucursal y clase."""
    return SimpleNamespace(
        sucursal_id=sucursal_id, clase=clase, unidades=D(unidades),
        referencias=1, valor=D(valor))


# --- Acciones permitidas ----------------------------------------------------


def _acciones(estado_pedido, **corrida):
    return pr.acciones_de(_corrida(**corrida), estado_pedido)


NADA = {"cerrar": False, "reabrir": False, "editar": False,
        "enviar": False, "corregir_envio": False, "exportar": False}


def test_a_borrador_pedido_can_be_edited_and_closed_but_not_reopened():
    assert _acciones("BORRADOR") == {
        **NADA, "cerrar": True, "editar": True}


def test_a_closed_pedido_can_be_reopened_or_sent():
    assert _acciones("CERRADO") == {
        **NADA, "reabrir": True, "enviar": True, "exportar": True}


def test_a_sent_pedido_can_only_have_its_number_corrected():
    assert _acciones("ENVIADO") == {
        **NADA, "corregir_envio": True, "exportar": True}


def test_a_tienda_without_pedido_has_no_action():
    assert _acciones(None) == NADA


def test_a_scenario_never_offers_a_pedido_action():
    for estado_pedido in ("BORRADOR", "CERRADO", "ENVIADO"):
        assert _acciones(estado_pedido, es_escenario=True) == NADA


def test_an_invalidated_corrida_can_only_reopen_or_correct_a_number():
    assert _acciones("BORRADOR", invalidada=True) == NADA
    assert _acciones("CERRADO", invalidada=True) == {
        **NADA, "reabrir": True}
    assert _acciones("ENVIADO", invalidada=True)["corregir_envio"] is True


def test_a_corrida_not_calculated_offers_nothing():
    for estado in ("PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"):
        assert not any(_acciones("BORRADOR", estado=estado).values()), estado


def test_a_legacy_cerrada_corrida_still_offers_the_actions():
    legado = _acciones("CERRADO", estado="CERRADA")
    assert legado["reabrir"] is True and legado["enviar"] is True


# --- Resumen de estados -----------------------------------------------------


def test_the_summary_counts_each_state_and_the_pedidos_with_nothing_to_order():
    sucursales = [
        _suc(SUC_A, "UNO", 1, estado_pedido="ENVIADO"),
        _suc(SUC_B, "DOS", 2, estado_pedido="CERRADO"),
        _suc(SUC_C, "TRES", 3, estado_pedido="BORRADOR"),
        _suc(uuid.UUID(int=604), "CUATRO", 4, "FALLIDA",
             estado_pedido=None),
    ]
    unidades = {SUC_A: D("5"), SUC_B: D("0"), SUC_C: D("9")}

    resumen = pr.resumen_de_pedidos(sucursales, unidades)

    assert resumen == {
        "total": 3, "borrador": 1, "cerrados": 1, "enviados": 1,
        "sin_pedido": 1}


def test_a_tienda_without_lines_counts_as_nothing_to_order():
    resumen = pr.resumen_de_pedidos(
        [_suc(SUC_A, "UNO", 1, estado_pedido="BORRADOR")], {})

    assert resumen["sin_pedido"] == 1 and resumen["total"] == 1


def test_a_list_summary_has_no_nothing_to_order_count():
    assert pr.resumen_de_lista(
        {"total": 47, "borrador": 34, "cerrados": 10, "enviados": 3}
    ) == {"total": 47, "borrador": 34, "cerrados": 10, "enviados": 3,
          "sin_pedido": None}
    assert pr.resumen_de_lista(None) == {
        "total": 0, "borrador": 0, "cerrados": 0, "enviados": 0,
        "sin_pedido": None}


# --- Detalle: el pedido de cada tienda --------------------------------------


def _detalle_pedido(corrida=None, eventos=None):
    sucursales = [
        _suc(SUC_A, "UNO", 1, estado_pedido="CERRADO"),
        _suc(SUC_B, "DOS", 2, estado_pedido="BORRADOR"),
        _suc(SUC_C, "TRES", 3, "FALLIDA", estado_pedido=None)]
    filas = [
        _pedir(SUC_A, "AF", "10", "1000"), _pedir(SUC_A, "BM", "5", "250"),
        _pedir(SUC_B, "AF", "7", "700")]
    return pr.armar_detalle(
        corrida or _corrida(), sucursales,
        [_res(SUC_A, "TOTAL", "10", 1, "100")], [], None, filas, eventos)


def test_each_sucursal_carries_its_pedido_state_and_what_to_order():
    detalle = _detalle_pedido()

    uno, dos, tres = detalle["sucursales"]

    assert (uno["estado_pedido"], uno["unidades_a_pedir"],
            uno["valor_a_pedir"]) == ("CERRADO", D("15"), D("1250"))
    assert (dos["estado_pedido"], dos["unidades_a_pedir"]) == (
        "BORRADOR", D("7"))
    assert (tres["estado_pedido"], tres["unidades_a_pedir"],
            tres["valor_a_pedir"]) == (None, D("0"), D("0"))


def test_the_actions_follow_each_tienda_state():
    uno, dos, tres = _detalle_pedido()["sucursales"]

    assert uno["acciones"] == {
        **NADA, "reabrir": True, "enviar": True, "exportar": True}
    assert dos["acciones"] == {**NADA, "cerrar": True, "editar": True}
    assert not any(tres["acciones"].values())


def test_the_detail_summary_counts_the_ok_tiendas_ci_03():
    pedidos = _detalle_pedido()["pedidos"]

    assert pedidos == {
        "total": 2, "borrador": 1, "cerrados": 1, "enviados": 0,
        "sin_pedido": 0}


def test_the_last_event_of_each_tienda_is_attached():
    eventos = {SUC_A: pr.UltimoEvento("CERRADO", "Maria", AHORA)}

    uno, dos, _ = _detalle_pedido(eventos=eventos)["sucursales"]

    assert uno["ultimo_evento"] == {
        "evento": "CERRADO", "usuario": "Maria", "creado_en": AHORA}
    assert dos["ultimo_evento"] is None


def test_the_detail_without_events_or_pedido_rows_still_builds():
    detalle = pr.armar_detalle(
        _corrida(), [_suc(SUC_A, "UNO", 1, estado_pedido="BORRADOR")],
        [], [], None)

    assert detalle["pedidos"]["sin_pedido"] == 1
    assert detalle["sucursales"][0]["unidades_a_pedir"] == D("0")


# --- Lista: resumen y filtro ------------------------------------------------


async def test_the_list_adds_the_pedido_summary_of_each_corrida():
    db = FakeAsyncSession(execute_queue=[
        [1], [_fila_lista()],
        [(fx.CORRIDA_ID, "BORRADOR", 1), (fx.CORRIDA_ID, "ENVIADO", 1)]])

    items, _ = await cq.listar(
        db, alcance=None, proveedor_id=None, estado=None, desde=None,
        hasta=None, escenario=None, limite=50, offset=0)

    assert items[0]["pedidos"] == {
        "total": 2, "borrador": 1, "cerrados": 0, "enviados": 1,
        "sin_pedido": None}
    assert "FROM corrida_sucursal" in _sql(db.executed_statements[2])


async def test_an_empty_list_page_asks_for_no_summary():
    db = FakeAsyncSession(execute_queue=[[0], []])

    await cq.listar(
        db, alcance=None, proveedor_id=None, estado=None, desde=None,
        hasta=None, escenario=None, limite=50, offset=0)

    assert len(db.executed_statements) == 2


async def _filtrar(pedidos):
    db = FakeAsyncSession(execute_queue=[[0], []])
    await cq.listar(
        db, alcance=None, proveedor_id=None, estado=None, desde=None,
        hasta=None, escenario=None, limite=50, offset=0, pedidos=pedidos)
    return [_sql(s) for s in db.executed_statements]


async def test_the_open_filter_wants_a_borrador_tienda():
    for sql in await _filtrar("abiertos"):
        assert "corrida_sucursal.estado_pedido = 'BORRADOR'" in sql
        assert "NOT" not in sql


async def test_the_to_send_filter_wants_a_cerrado_tienda():
    for sql in await _filtrar("por_enviar"):
        assert "corrida_sucursal.estado_pedido = 'CERRADO'" in sql


async def test_the_sent_filter_wants_one_sent_and_nobody_pending():
    for sql in await _filtrar("enviados"):
        assert "corrida_sucursal.estado_pedido = 'ENVIADO'" in sql
        assert "NOT (EXISTS" in sql
        assert (
            "corrida_sucursal.estado_pedido IN ('BORRADOR', 'CERRADO')"
            in sql)


async def test_no_pedido_filter_adds_no_exists():
    for sql in await _filtrar(None):
        assert "EXISTS" not in sql


# --- Detalle: las consultas -------------------------------------------------


async def test_the_detail_reads_the_last_event_of_each_tienda():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(SUC_A, "UNO", 1, estado_pedido="CERRADO")],
        [], [], [_pedir(SUC_A, "AF", "10", "1000")],
        [(SUC_A, "CERRADO", "Maria", AHORA)]])

    detalle = await cq.detalle(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 6
    assert detalle["sucursales"][0]["ultimo_evento"] == {
        "evento": "CERRADO", "usuario": "Maria", "creado_en": AHORA}
    sql = _sql(db.executed_statements[5])
    assert "DISTINCT ON (pedido_evento.sucursal_id)" in sql
    assert "ORDER BY pedido_evento.sucursal_id, pedido_evento.creado_en DESC" \
        in sql


async def test_the_sucursal_query_reads_the_pedido_state():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(SUC_A, "UNO", 1)], [], [], [], []])

    await cq.detalle(db, fx.CORRIDA_ID, None)

    assert "corrida_sucursal.estado_pedido" in _sql(
        db.executed_statements[1])


async def test_a_scoped_detail_scopes_the_events_too():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(SUC_A, "UNO", 1)], [], [], [], []])

    await cq.detalle(db, fx.CORRIDA_ID, frozenset({SUC_A}))

    assert f"pedido_evento.sucursal_id IN ('{SUC_A}')" in _sql(
        db.executed_statements[5])


# --- Cabecera de una tienda -------------------------------------------------


def _fila_cabecera(**campos):
    tienda = _suc(SUC_A, "UNO", 1, estado_pedido="CERRADO", **campos)
    return (_corrida(), tienda, "UNO", "SIC-1")


TOTALES = (D("1010"), D("6000000"), D("1000"), D("5000000"))


async def test_the_tienda_header_joins_corrida_tienda_and_totals():
    db = FakeAsyncSession(execute_queue=[
        [_fila_cabecera()], [TOTALES],
        [(SUC_A, "CERRADO", "Maria", AHORA)]])

    cuerpo = await lp.cabecera_tienda(db, fx.CORRIDA_ID, SUC_A, None)

    assert cuerpo["corrida_codigo"] == "PED-2026-S39-001"
    assert (cuerpo["sucursal_id"], cuerpo["nombre"], cuerpo["sic"]) == (
        SUC_A, "UNO", "SIC-1")
    assert cuerpo["estado_pedido"] == "CERRADO"
    assert cuerpo["totales"] == {
        "unidades_a_pedir": D("1010"), "valor_a_pedir": D("6000000"),
        "unidades_sugerido": D("1000"), "valor_sugerido": D("5000000")}
    assert cuerpo["ultimo_evento"]["usuario"] == "Maria"
    assert cuerpo["acciones"]["reabrir"] is True
    assert cuerpo["fecha_corte"] == datetime.date(2026, 9, 21)
    assert cuerpo["corrida_estado"] == "BORRADOR"


async def test_a_header_without_events_has_no_last_event():
    db = FakeAsyncSession(execute_queue=[
        [_fila_cabecera()], [TOTALES], []])

    cuerpo = await lp.cabecera_tienda(db, fx.CORRIDA_ID, SUC_A, None)

    assert cuerpo["ultimo_evento"] is None


async def test_an_unknown_tienda_has_no_header_and_no_more_queries():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await lp.cabecera_tienda(db, fx.CORRIDA_ID, SUC_A, None) is None
    assert len(db.executed_statements) == 1


async def test_a_scoped_header_filters_the_tienda_by_scope():
    db = FakeAsyncSession(execute_queue=[[]])

    await lp.cabecera_tienda(db, fx.CORRIDA_ID, SUC_B, frozenset({SUC_A}))

    assert f"corrida_sucursal.sucursal_id IN ('{SUC_A}')" in _sql(
        db.executed_statements[0])


# --- Línea de tiempo --------------------------------------------------------


async def test_the_events_come_oldest_first_with_who_and_why():
    ahora = AHORA
    db = FakeAsyncSession(execute_queue=[
        [SUC_A],
        [(1, "CERRADO", None, None, uuid.UUID(int=900), "Maria", ahora),
         (2, "REABIERTO", "Corrección", None, uuid.UUID(int=901), "Pedro",
          ahora),
         (3, "CERRADO", None, {"migrado_f3": True}, None, None, ahora)]])

    eventos = await lp.eventos_tienda(db, fx.CORRIDA_ID, SUC_A, None)

    assert [e["evento"] for e in eventos] == [
        "CERRADO", "REABIERTO", "CERRADO"]
    assert eventos[1]["motivo"] == "Corrección"
    assert eventos[1]["usuario"] == "Pedro"
    assert eventos[2]["usuario_id"] is None and eventos[2]["usuario"] is None
    assert eventos[2]["detalle"] == {"migrado_f3": True}
    sql = _sql(db.executed_statements[1])
    assert "ORDER BY pedido_evento.creado_en ASC, pedido_evento.id ASC" in sql
    assert "LEFT OUTER JOIN usuario" in sql


async def test_the_events_of_an_unknown_tienda_are_none():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await lp.eventos_tienda(
        db, fx.CORRIDA_ID, SUC_B, None) is None
    assert len(db.executed_statements) == 1
