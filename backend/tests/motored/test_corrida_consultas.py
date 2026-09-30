"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-9, spec
"RBAC (T19)" y decisión #16): lecturas de la API de corridas.

Dos capas: las proyecciones (`proyecciones.py`, puras: cabecera recalculada
sobre las sucursales visibles, progreso, resumen por clase, recorte del
snapshot, bloque de antigüedades) y las consultas (`consultas.py`: qué SQL se
emite y cómo se restringe por alcance, con una sesión de juguete y el SQL
literal). Las mismas consultas contra Postgres real corren en
`pg_real/test_corridas_api_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.motored.models.corrida import Corrida
from app.motored.services.corridas import consultas as cq
from app.motored.services.corridas import proyecciones as pr
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx

SUC_A, SUC_B, SUC_C = fx.SUC_A, fx.SUC_B, uuid.UUID(int=603)
CORTE = datetime.date(2026, 9, 21)
D = Decimal


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _antiguedad():
    return {tipo: {
        "carga_id": str(uuid.UUID(int=n)), "fecha_usada": "2026-09-19",
        "antiguedad_dias": dias, "limite_dias": 7,
        "fuente_limite": "DEFAULT"}
        for n, (tipo, dias) in enumerate(
            (("inventario", 2), ("backorder", 3), ("facturas", 1),
             ("ingresos", 1)), start=1)}


def _corrida(**campos):
    base = dict(
        id=fx.CORRIDA_ID, codigo="PED-2026-S39-001",
        proveedor_id=fx.PROVEEDOR_ID, fecha_corte=CORTE, estado="BORRADOR",
        es_escenario=False, alcance="TODAS", invalidada=False,
        sucursales_total=3, sucursales_procesadas=3, intentos=1,
        parametros_en_fecha=CORTE, overrides=None, motivo_invalidacion=None,
        motivo_anulacion=None, created_at=fx.CREADA,
        parametros_snapshot={
            "parametros": {"dias_entre_pedidos": {"valor": "30"}},
            "dias_entre_pedidos_por_sucursal": {
                str(SUC_A): {"valor": "30"}, str(SUC_B): {"valor": "7"},
                str(SUC_C): {"valor": "15"}},
            "limites_antiguedad": {"facturas": {"dias": 7}}},
        seleccion_datos={
            "antiguedad": _antiguedad(),
            "cortes": {"inventario": "2026-09-19",
                       "backorder": "2026-09-18"},
            "mes_en_curso": {"modo_efectivo": "EXCLUIDO"},
            "advertencias": [{"codigo": "A-CORRIDA-101",
                              "mensaje": "sin demanda perdida"}]},
        log=[{"evento": "CREADA", "nota": "corrida de prueba"},
             {"evento": "FINALIZADA", "estado": "BORRADOR"}],
        latido_en=None, iniciado_en=None, terminado_en=None,
        cerrada_en=None, anulada_en=None)
    return Corrida(**{**base, **campos})


def _suc(sucursal_id, nombre, orden, estado="OK", **campos):
    base = dict(
        corrida_id=fx.CORRIDA_ID, sucursal_id=sucursal_id, orden=orden,
        estado=estado, codigo=None, mensaje=None, lineas=2, excluidas=0,
        unidades=D("10.00"), valor=D("100.00"), fecha_apertura=None,
        divisor=21, dias_empaque=D("3"), dias_transito=D("2"),
        dias_seguridad=D("2.5"), dias_entre_pedidos=D("30"), intentos=1,
        parametros={"nombre": nombre, "advertencias": []},
        nombre=nombre)
    return SimpleNamespace(**{**base, **campos})


def _res(sucursal_id, clase, unidades, refs, valor, peso="0"):
    return SimpleNamespace(
        corrida_id=fx.CORRIDA_ID, sucursal_id=sucursal_id, clase=clase,
        unidades=D(unidades), referencias=refs, valor=D(valor),
        porcentaje_peso=D(peso))


# --- nota ---------------------------------------------------------------


def test_the_nota_is_read_from_the_creation_event():
    assert pr.nota_de([{"evento": "CREADA", "nota": "hola"}]) == "hola"


def test_a_log_without_nota_or_without_log_has_no_nota():
    assert pr.nota_de([{"evento": "CREADA"}]) is None
    assert pr.nota_de(None) is None
    assert pr.nota_de([]) is None


# --- recorte del snapshot -----------------------------------------------


def test_an_unrestricted_snapshot_is_complete():
    snapshot = _corrida().parametros_snapshot

    assert pr.recortar_snapshot(snapshot, None) == snapshot


def test_a_scoped_snapshot_keeps_only_the_own_sucursal_values():
    snapshot = _corrida().parametros_snapshot

    recortado = pr.recortar_snapshot(snapshot, frozenset({SUC_B}))

    assert recortado["dias_entre_pedidos_por_sucursal"] == {
        str(SUC_B): {"valor": "7"}}
    assert recortado["parametros"] == snapshot["parametros"]
    assert recortado["limites_antiguedad"] == snapshot["limites_antiguedad"]
    assert len(snapshot["dias_entre_pedidos_por_sucursal"]) == 3


def test_a_missing_snapshot_stays_empty():
    assert pr.recortar_snapshot(None, frozenset({SUC_A})) == {}


# --- resumen por clase --------------------------------------------------


def test_the_resumen_adds_up_each_class_across_sucursales():
    filas = [
        _res(SUC_A, "AF", "50", 1, "1000"),
        _res(SUC_B, "AF", "30", 2, "600.50"),
        _res(SUC_A, "BM", "20", 1, "400"),
        _res(SUC_A, "TOTAL", "70", 2, "1400"),
        _res(SUC_B, "TOTAL", "30", 2, "600.50"),
    ]

    por_clase = pr.resumen_por_clase(filas)

    assert [(c["clase"], c["unidades"], c["referencias"], c["valor"])
            for c in por_clase] == [
        ("AF", D("80"), 3, D("1600.50")),
        ("BM", D("20"), 1, D("400")),
        ("TOTAL", D("100"), 4, D("2000.50"))]
    assert all(c["sucursal_id"] is None for c in por_clase)


def test_the_weights_are_recomputed_over_the_visible_units():
    filas = [
        _res(SUC_A, "AF", "75", 1, "10"),
        _res(SUC_A, "BM", "25", 1, "10"),
        _res(SUC_A, "TOTAL", "100", 2, "20")]

    pesos = {c["clase"]: c["porcentaje_peso"]
             for c in pr.resumen_por_clase(filas)}

    assert pesos == {
        "AF": D("0.750000"), "BM": D("0.250000"), "TOTAL": D("1.000000")}


def test_the_weights_are_zero_when_there_are_no_units():
    filas = [_res(SUC_A, "AF", "0", 0, "0"), _res(SUC_A, "TOTAL", "0", 0, "0")]

    pesos = [c["porcentaje_peso"] for c in pr.resumen_por_clase(filas)]

    assert pesos == [D("0"), D("0")]


def test_the_classes_follow_the_excel_order_and_total_comes_last():
    filas = [_res(SUC_A, c, "1", 1, "1") for c in (
        "TOTAL", "DS", "CF", "AM", "AF", "BS", "DF")]

    clases = [c["clase"] for c in pr.resumen_por_clase(filas)]

    assert clases == ["AF", "AM", "BS", "CF", "DF", "DS", "TOTAL"]


def test_the_totals_are_the_aggregated_total_row():
    filas = [_res(SUC_A, "TOTAL", "70", 2, "1400"),
             _res(SUC_B, "TOTAL", "30", 1, "600")]

    assert pr.totales(pr.resumen_por_clase(filas)) == {
        "unidades": D("100"), "referencias": 3, "valor": D("2000")}


def test_totals_without_any_resumen_are_zero():
    assert pr.totales([]) == {
        "unidades": D("0"), "referencias": 0, "valor": D("0")}


# --- cabecera y detalle -------------------------------------------------


def _detalle(alcance=None, sucursales=None, resumen=(), cargas=(),
             corrida=None):
    sucursales = sucursales if sucursales is not None else [
        _suc(SUC_A, "UNO", 1), _suc(SUC_B, "DOS", 2), _suc(SUC_C, "TRES", 3)]
    return pr.armar_detalle(
        corrida or _corrida(), sucursales, list(resumen), list(cargas),
        alcance)


def test_the_detail_exposes_the_age_of_each_input_at_the_top_level():
    detalle = _detalle()

    assert set(detalle["antiguedad"]) == {
        "inventario", "backorder", "facturas", "ingresos"}
    assert detalle["antiguedad"]["backorder"] == {
        "carga_id": str(uuid.UUID(int=2)), "fecha_usada": "2026-09-19",
        "antiguedad_dias": 3, "limite_dias": 7, "fuente_limite": "DEFAULT"}
    assert detalle["mes_en_curso"] == {"modo_efectivo": "EXCLUIDO"}


def test_the_header_fields_and_the_nota_are_carried():
    detalle = _detalle()

    assert detalle["codigo"] == "PED-2026-S39-001"
    assert detalle["nota"] == "corrida de prueba"
    assert detalle["estado"] == "BORRADOR" and detalle["intentos"] == 1


def test_the_header_counts_are_recomputed_over_the_visible_sucursales():
    sucursales = [_suc(SUC_A, "UNO", 1)]

    detalle = _detalle(frozenset({SUC_A}), sucursales)

    assert detalle["sucursales_total"] == 1
    assert detalle["sucursales_procesadas"] == 1


def test_a_pending_sucursal_is_not_counted_as_processed():
    sucursales = [_suc(SUC_A, "UNO", 1), _suc(SUC_B, "DOS", 2, "PENDIENTE")]

    detalle = _detalle(None, sucursales)

    assert (detalle["sucursales_total"], detalle[
        "sucursales_procesadas"]) == (2, 1)


def test_the_used_cargas_are_grouped_by_tipo():
    cargas = [
        SimpleNamespace(
            tipo="VENTAS", id=uuid.UUID(int=9), nombre_archivo="v.xlsx",
            estado="APLICADO", periodo_desde=datetime.date(2026, 3, 1),
            periodo_hasta=datetime.date(2026, 9, 14)),
        SimpleNamespace(
            tipo="DEMANDA_PERDIDA", id=uuid.UUID(int=10),
            nombre_archivo="p.xlsx", estado="ANULADO",
            periodo_desde=None, periodo_hasta=None)]

    usadas = _detalle(cargas=cargas)["cargas_usadas"]

    assert set(usadas) == {"VENTAS", "DEMANDA_PERDIDA"}
    assert usadas["VENTAS"][0] == {
        "carga_id": uuid.UUID(int=9), "nombre_archivo": "v.xlsx",
        "estado": "APLICADO", "periodo_desde": datetime.date(2026, 3, 1),
        "periodo_hasta": datetime.date(2026, 9, 14)}
    assert usadas["DEMANDA_PERDIDA"][0]["estado"] == "ANULADO"


def test_each_sucursal_status_row_is_shaped():
    detalle = _detalle(sucursales=[_suc(
        SUC_A, "UNO", 1, "FALLIDA", codigo="E-CORRIDA-021",
        mensaje="sin SIC", lineas=0, unidades=None, valor=None)])

    (fila,) = detalle["sucursales"]

    assert fila["sucursal_id"] == SUC_A and fila["nombre"] == "UNO"
    assert (fila["estado"], fila["codigo"]) == ("FALLIDA", "E-CORRIDA-021")
    assert fila["unidades"] is None and fila["lineas"] == 0


def test_the_warnings_join_the_corrida_ones_and_each_sucursal_ones():
    sucursales = [
        _suc(SUC_A, "UNO", 1),
        _suc(SUC_B, "DOS", 2, "OMITIDA", parametros={
            "nombre": "DOS", "advertencias": [{
                "codigo": "A-CORRIDA-102", "mensaje": "abrió hace poco"}]})]

    avisos = _detalle(sucursales=sucursales)["advertencias"]

    assert [(a["sucursal_id"], a["codigo"]) for a in avisos] == [
        (None, "A-CORRIDA-101"), (SUC_B, "A-CORRIDA-102")]
    assert avisos[1]["sucursal"] == "DOS"


def test_a_scoped_detail_hides_the_snapshot_of_other_sucursales():
    detalle = _detalle(frozenset({SUC_A}), [_suc(SUC_A, "UNO", 1)])

    assert list(
        detalle["parametros"]["dias_entre_pedidos_por_sucursal"]
    ) == [str(SUC_A)]


def test_the_detail_resumen_has_a_row_per_sucursal_and_the_aggregate():
    filas = [_res(SUC_B, "AF", "5", 1, "5"), _res(SUC_A, "AF", "7", 1, "7")]

    detalle = _detalle(resumen=filas)

    assert [r["sucursal_id"] for r in detalle["resumen"]] == [SUC_A, SUC_B]
    assert detalle["resumen_por_clase"][0]["unidades"] == D("12")


# --- progreso -----------------------------------------------------------


def _progreso(estado="CALCULANDO", alcance=None, sucursales=None, **campos):
    sucursales = sucursales if sucursales is not None else [
        _suc(SUC_A, "UNO", 1), _suc(SUC_B, "DOS", 2, "PENDIENTE"),
        _suc(SUC_C, "TRES", 3, "PENDIENTE")]
    return pr.armar_progreso(
        _corrida(estado=estado, **campos), sucursales, alcance)


def test_the_progress_counts_each_state():
    sucursales = [
        _suc(SUC_A, "UNO", 1), _suc(SUC_B, "DOS", 2, "OMITIDA"),
        _suc(SUC_C, "TRES", 3, "FALLIDA", codigo="E-CORRIDA-021",
             mensaje="sin SIC"),
        _suc(uuid.UUID(int=604), "CUATRO", 4, "PENDIENTE")]

    cuerpo = _progreso(sucursales=sucursales)

    assert (cuerpo["total"], cuerpo["procesadas"]) == (4, 3)
    assert (cuerpo["ok"], cuerpo["omitidas"], cuerpo["fallidas"]) == (1, 1, 1)


def test_the_current_sucursal_is_the_first_pending_by_order():
    cuerpo = _progreso()

    assert cuerpo["actual"] == "Sucursal 2 de 3 — DOS"


def test_there_is_no_current_sucursal_once_the_corrida_is_done():
    assert _progreso(estado="BORRADOR")["actual"] is None


def test_there_is_no_current_sucursal_when_nothing_is_pending():
    sucursales = [_suc(SUC_A, "UNO", 1)]

    assert _progreso(sucursales=sucursales)["actual"] is None


def test_a_scoped_progress_never_names_a_sucursal_even_if_one_is_pending():
    sucursales = [_suc(SUC_A, "UNO", 1), _suc(SUC_B, "DOS", 2, "PENDIENTE")]

    cuerpo = _progreso(
        alcance=frozenset({SUC_A, SUC_B}), sucursales=sucursales)

    assert cuerpo["actual"] is None and cuerpo["total"] == 2
    assert _progreso(sucursales=sucursales)["actual"] is not None


def test_failed_sucursales_are_listed_as_errors():
    sucursales = [_suc(
        SUC_A, "UNO", 1, "FALLIDA", codigo="E-CORRIDA-021",
        mensaje="La sucursal UNO no tiene SIC.")]

    (error,) = _progreso("BORRADOR", sucursales=sucursales)["errores"]

    assert error == {
        "sucursal_id": SUC_A, "sucursal": "UNO",
        "codigo": "E-CORRIDA-021", "mensaje": "La sucursal UNO no tiene SIC."}


def test_a_fallida_corrida_reports_its_terminal_code_as_an_error():
    log = [{"evento": "CREADA"}, {
        "evento": "FINALIZADA", "estado": "FALLIDA",
        "codigo": "E-CORRIDA-030"}]

    errores = _progreso("FALLIDA", sucursales=[], log=log)["errores"]

    assert errores == [{
        "sucursal_id": None, "sucursal": None, "codigo": "E-CORRIDA-030",
        "mensaje": "Ninguna sucursal se pudo calcular."}]


def test_the_sweep_code_of_an_exhausted_corrida_is_reported_too():
    log = [{"evento": "CREADA"}, {
        "evento": "BARRIDA", "codigo": "E-CORRIDA-031"}]

    (error,) = _progreso("FALLIDA", sucursales=[], log=log)["errores"]

    assert error["codigo"] == "E-CORRIDA-031"


def test_a_corrida_that_is_not_failed_has_no_terminal_error():
    log = [{"evento": "BARRIDA", "codigo": "E-CORRIDA-031"}]

    assert _progreso("CALCULANDO", sucursales=[], log=log)["errores"] == []


def test_the_progress_warnings_come_from_the_corrida_and_its_sucursales():
    sucursales = [_suc(SUC_A, "UNO", 1, parametros={
        "nombre": "UNO", "advertencias": [{
            "codigo": "A-CORRIDA-104", "mensaje": "sin precio"}]})]

    avisos = _progreso("BORRADOR", sucursales=sucursales)["advertencias"]

    assert [(a["sucursal_id"], a["codigo"]) for a in avisos] == [
        (None, "A-CORRIDA-101"), (SUC_A, "A-CORRIDA-104")]


def test_the_progress_carries_heartbeat_and_attempts():
    momento = datetime.datetime(2026, 9, 21, 12, tzinfo=datetime.timezone.utc)

    cuerpo = _progreso(latido_en=momento, intentos=2)

    assert cuerpo["latido_en"] == momento and cuerpo["intentos"] == 2
    assert cuerpo["estado"] == "CALCULANDO"


# --- consultas: listar --------------------------------------------------


def _fila_lista(**campos):
    base = {k: v for k, v in fx.item_lista().items()}
    base["sucursales_total"] = 2
    base["sucursales_procesadas"] = 2
    return SimpleNamespace(**{**base, **campos})


async def _listar(db, **campos):
    base = dict(
        alcance=None, proveedor_id=None, estado=None, desde=None,
        hasta=None, escenario=None, limite=50, offset=0)
    return await cq.listar(db, **{**base, **campos})


async def test_the_list_returns_the_items_and_the_total():
    db = FakeAsyncSession(execute_queue=[[7], [_fila_lista(nota="n")]])

    items, total = await _listar(db)

    assert total == 7
    assert items[0]["codigo"] == "PED-2026-S39-001"
    assert items[0]["nota"] == "n" and items[0]["sucursales_total"] == 2


async def test_the_list_orders_newest_first_and_pages():
    db = FakeAsyncSession(execute_queue=[[0], []])

    await _listar(db, limite=20, offset=40)

    sql = _sql(db.executed_statements[1])
    assert "ORDER BY corrida.created_at DESC" in sql
    assert "LIMIT 20 OFFSET 40" in sql


async def test_the_list_filters_become_where_clauses():
    db = FakeAsyncSession(execute_queue=[[0], []])

    await _listar(
        db, proveedor_id=fx.PROVEEDOR_ID, estado="CERRADA",
        desde=datetime.date(2026, 9, 1), hasta=datetime.date(2026, 9, 30),
        escenario=True)

    for sql in (_sql(s) for s in db.executed_statements):
        assert f"corrida.proveedor_id = '{fx.PROVEEDOR_ID}'" in sql
        assert "corrida.estado = 'CERRADA'" in sql
        assert "corrida.fecha_corte >= '2026-09-01'" in sql
        assert "corrida.fecha_corte <= '2026-09-30'" in sql
        assert "corrida.es_escenario IS true" in sql


async def test_an_unrestricted_list_has_no_sucursal_clause_in_its_where():
    db = FakeAsyncSession(execute_queue=[[0], []])

    await _listar(db)

    assert "EXISTS" not in _sql(db.executed_statements[0])


async def test_a_scoped_list_only_shows_corridas_with_an_own_sucursal():
    db = FakeAsyncSession(execute_queue=[[0], []])

    await _listar(db, alcance=frozenset({SUC_A}))

    for sql in (_sql(s) for s in db.executed_statements):
        assert "EXISTS" in sql
        assert f"corrida_sucursal.sucursal_id IN ('{SUC_A}')" in sql


async def test_a_scoped_list_counts_only_the_own_sucursales():
    db = FakeAsyncSession(execute_queue=[[0], []])

    await _listar(db, alcance=frozenset({SUC_A}))

    consulta = _sql(db.executed_statements[1])
    assert consulta.count(f"corrida_sucursal.sucursal_id IN ('{SUC_A}')") >= 3


# --- consultas: detalle y progreso --------------------------------------


async def test_the_detail_reads_the_corrida_sucursales_resumen_and_cargas():
    carga = SimpleNamespace(
        tipo="VENTAS", id=uuid.UUID(int=9), nombre_archivo="v.xlsx",
        estado="APLICADO", periodo_desde=None, periodo_hasta=None)
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(SUC_A, "UNO", 1)],
        [_res(SUC_A, "TOTAL", "10", 2, "100")], [carga]])

    detalle = await cq.detalle(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 4
    assert detalle["codigo"] == "PED-2026-S39-001"
    assert detalle["sucursales"][0]["nombre"] == "UNO"
    assert detalle["totales"]["unidades"] == D("10")
    assert detalle["cargas_usadas"]["VENTAS"][0]["nombre_archivo"] == "v.xlsx"


async def test_an_unknown_corrida_has_no_detail_and_no_more_queries():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await cq.detalle(db, fx.CORRIDA_ID, None) is None
    assert len(db.executed_statements) == 1


async def test_a_scoped_detail_restricts_sucursales_and_resumen():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(SUC_A, "UNO", 1)], [], []])

    await cq.detalle(db, fx.CORRIDA_ID, frozenset({SUC_A}))

    corrida, sucursales, resumen, cargas = (
        _sql(s) for s in db.executed_statements)
    assert "EXISTS" in corrida
    assert f"corrida_sucursal.sucursal_id IN ('{SUC_A}')" in sucursales
    assert f"corrida_resumen.sucursal_id IN ('{SUC_A}')" in resumen
    assert "IN ('" not in cargas


async def test_an_unrestricted_detail_adds_no_scope_to_any_query():
    db = FakeAsyncSession(execute_queue=[
        [_corrida()], [_suc(SUC_A, "UNO", 1)], [], []])

    await cq.detalle(db, fx.CORRIDA_ID, None)

    assert "EXISTS" not in "".join(_sql(s) for s in db.executed_statements)


async def test_the_progress_reads_the_corrida_and_its_sucursales():
    db = FakeAsyncSession(execute_queue=[
        [_corrida(estado="CALCULANDO")],
        [_suc(SUC_A, "UNO", 1), _suc(SUC_B, "DOS", 2, "PENDIENTE")]])

    cuerpo = await cq.progreso(db, fx.CORRIDA_ID, None)

    assert len(db.executed_statements) == 2
    assert cuerpo["actual"] == "Sucursal 2 de 2 — DOS"


async def test_the_progress_of_an_invisible_corrida_is_none():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await cq.progreso(db, fx.CORRIDA_ID, frozenset({SUC_A})) is None


# --- consultas: líneas --------------------------------------------------


async def _lineas(db, **campos):
    base = dict(
        sucursal_id=None, incluir_excluidas=False, clase=None,
        estado_quiebre=None, limite=500, offset=0)
    return await cq.lineas(
        db, fx.CORRIDA_ID, campos.pop("alcance", None), **{**base, **campos})


async def test_the_lines_are_a_page_and_a_total():
    db = FakeAsyncSession(execute_queue=[
        [fx.CORRIDA_ID], [120], [fx.linea(), fx.linea(codigo="B")]])

    filas, total = await _lineas(db)

    assert total == 120 and [f.codigo_referencia for f in filas] == [
        "94109-12000S", "B"]


async def test_excluded_lines_are_hidden_unless_asked_for():
    db = FakeAsyncSession(execute_queue=[[fx.CORRIDA_ID], [0], []])
    await _lineas(db)
    oculto = _sql(db.executed_statements[2])

    db = FakeAsyncSession(execute_queue=[[fx.CORRIDA_ID], [0], []])
    await _lineas(db, incluir_excluidas=True)
    visible = _sql(db.executed_statements[2])

    assert "corrida_linea.motivo_exclusion IS NULL" in oculto
    assert "motivo_exclusion IS NULL" not in visible


async def test_the_line_filters_become_where_clauses_on_both_queries():
    db = FakeAsyncSession(execute_queue=[[fx.CORRIDA_ID], [0], []])

    await _lineas(
        db, sucursal_id=SUC_A, clase="AF", estado_quiebre="QUIEBRE_TOTAL")

    for sql in (_sql(s) for s in db.executed_statements[1:]):
        assert f"corrida_linea.sucursal_id = '{SUC_A}'" in sql
        assert "corrida_linea.clase = 'AF'" in sql
        assert "corrida_linea.estado_quiebre = 'QUIEBRE_TOTAL'" in sql


async def test_the_lines_follow_the_abc_order_and_page():
    db = FakeAsyncSession(execute_queue=[[fx.CORRIDA_ID], [0], []])

    await _lineas(db, limite=2000, offset=30)

    sql = _sql(db.executed_statements[2])
    assert "ORDER BY corrida_linea.sucursal_id, " in sql
    assert "corrida_linea.orden_abc ASC NULLS LAST" in sql
    assert "corrida_linea.codigo_referencia" in sql
    assert "LIMIT 2000 OFFSET 30" in sql


async def test_a_scoped_line_query_is_restricted_to_the_own_sucursales():
    db = FakeAsyncSession(execute_queue=[[fx.CORRIDA_ID], [0], []])

    await _lineas(db, alcance=frozenset({SUC_A, SUC_B}))

    for sql in (_sql(s) for s in db.executed_statements[1:]):
        assert "corrida_linea.sucursal_id IN (" in sql
        assert str(SUC_A) in sql and str(SUC_B) in sql


async def test_the_lines_of_an_invisible_corrida_are_none_and_end_there():
    db = FakeAsyncSession(execute_queue=[[]])

    assert await _lineas(db, alcance=frozenset({SUC_C})) is None
    assert len(db.executed_statements) == 1
