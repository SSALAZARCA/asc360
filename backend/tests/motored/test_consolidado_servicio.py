"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-8, decision
F4-9, spec CO-01..CO-11): la matriz consolidada de una corrida (filas =
referencias, columnas = tiendas, celdas = cantidad a pedir) de
`services/corridas/consolidado.py`.

Con la sesión de juguete (`FakeAsyncSession`, que graba el SQL) se prueba lo
que no depende de Postgres: CUÁNTAS consultas hace y en qué orden (la
corrida, las columnas, UNA página de referencias y sus celdas: nunca una
consulta por tienda o por referencia), cómo arma la respuesta (totales por
tienda y total general sobre TODA la corrida, la tienda fallida como columna
marcada y sin números, las celdas dispersas) y la forma del SQL (paginación
en SQL, agrupado, sin líneas excluidas, la búsqueda sólo en las filas). El
SQL contra datos reales y el volumen de 47 tiendas, en
`pg_real/test_consolidado_pg.py`.
"""
import uuid
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import consolidado
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx

CORRIDA = fx.CORRIDA_ID
A, B, C = fx.SUC_A, fx.SUC_B, uuid.UUID(int=603)
R1, R2, R3 = (uuid.UUID(int=n) for n in (801, 802, 803))
D = Decimal


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _corrida(estado="BORRADOR", escenario=False):
    return [(CORRIDA, "PED-2026-S39-001", estado, escenario)]


def _col(sucursal_id, nombre, *, estado="OK", pedido="BORRADOR",
         codigo=None, mensaje=None, unidades="0", valor="0"):
    """Una columna: sucursal, nombre, calculo, pedido, codigo, mensaje,
    unidades y valor (None en una tienda sin pedido)."""
    ok = estado == "OK"
    return (sucursal_id, nombre, estado, pedido if ok else None, codigo,
            mensaje, D(unidades) if ok else D("0"),
            D(valor) if ok else D("0"))


COLUMNAS = [
    _col(A, "Armenia", unidades="100", valor="1000.00"),
    _col(B, "Bogota", pedido="CERRADO", unidades="200", valor="2000.00"),
    _col(C, "Cali", estado="FALLIDA", codigo="E-CORRIDA-020",
         mensaje="sin empaque"),
]
PAGINA = [
    (R1, "00-A", "Filtro", D("12"), 3),
    (R2, "00-B", "Bujia", D("7"), 3),
    (R3, "00-C", None, D("5"), 3),
]
CELDAS = [
    (R1, A, D("5")), (R1, B, D("7")), (R2, A, D("7")), (R3, B, D("5"))]


async def _correr(cola, **kw):
    sesion = FakeAsyncSession(execute_queue=cola)
    kw.setdefault("limite", 100)
    kw.setdefault("offset", 0)
    cuerpo = await consolidado.consolidado(sesion, CORRIDA, **kw)
    return cuerpo, sesion


async def _feliz(**kw):
    return await _correr(
        [_corrida(), COLUMNAS, PAGINA, CELDAS], **kw)


# --- La respuesta -----------------------------------------------------------


async def test_an_unknown_corrida_is_none_after_one_query():
    cuerpo, sesion = await _correr([[]])

    assert cuerpo is None
    assert len(sesion.executed_statements) == 1


async def test_the_matrix_takes_four_queries_whatever_its_size_co_01():
    _, sesion = await _feliz()

    sql = [_sql(s) for s in sesion.executed_statements]
    assert len(sql) == 4
    assert "FROM corrida " in sql[0] or "FROM corrida\n" in sql[0]
    assert "corrida_sucursal" in sql[1]
    assert "GROUP BY corrida_linea.referencia_id" in sql[2]
    assert "corrida_linea.referencia_id IN" in sql[3]


async def test_the_header_names_the_corrida_and_marks_scenarios_co_10():
    cuerpo, _ = await _correr(
        [_corrida(escenario=True), COLUMNAS, PAGINA, CELDAS])

    assert cuerpo["corrida_id"] == CORRIDA
    assert cuerpo["codigo"] == "PED-2026-S39-001"
    assert cuerpo["estado"] == "BORRADOR"
    assert cuerpo["es_escenario"] is True


async def test_tienda_totals_cover_the_whole_corrida_co_01_co_03():
    cuerpo, _ = await _feliz()

    [armenia, bogota, _] = cuerpo["tiendas"]
    assert (armenia["nombre"], armenia["unidades"], armenia["valor"]) == (
        "Armenia", D("100"), D("1000.00"))
    assert (bogota["estado_pedido"], bogota["unidades"]) == (
        "CERRADO", D("200"))


async def test_the_grand_total_is_the_sum_of_the_tienda_totals_co_01():
    cuerpo, _ = await _feliz()

    assert cuerpo["totales"] == {
        "unidades": D("300"), "valor": D("3000.00")}


async def test_a_failed_tienda_is_a_flagged_column_without_numbers_co_06():
    cuerpo, _ = await _feliz()

    cali = cuerpo["tiendas"][2]
    assert cali["estado"] == "FALLIDA"
    assert cali["estado_pedido"] is None
    assert cali["codigo"] == "E-CORRIDA-020"
    assert cali["mensaje"] == "sin empaque"
    assert cali["unidades"] is None and cali["valor"] is None


async def test_a_failed_tienda_never_enters_the_row_queries_co_06():
    _, sesion = await _feliz()

    pagina, celdas = (_sql(s) for s in sesion.executed_statements[2:])
    for sql in (pagina, celdas):
        assert str(A) in sql and str(B) in sql
        assert str(C) not in sql


async def test_each_row_has_its_total_and_its_sparse_cells_co_02():
    cuerpo, _ = await _feliz()

    [fila1, fila2, fila3] = cuerpo["filas"]
    assert fila1["codigo"] == "00-A" and fila1["nombre"] == "Filtro"
    assert fila1["total"] == D("12")
    assert fila1["celdas"] == {str(A): D("5"), str(B): D("7")}
    assert fila2["celdas"] == {str(A): D("7")}
    assert fila3["nombre"] is None and fila3["celdas"] == {str(B): D("5")}


async def test_the_paging_fields_report_the_reference_count_co_03():
    cuerpo, _ = await _feliz(limite=3, offset=0)

    assert (cuerpo["total"], cuerpo["limite"], cuerpo["offset"]) == (3, 3, 0)


# --- Estados sin matriz -----------------------------------------------------


async def test_a_corrida_without_calculated_tiendas_is_an_empty_matrix_co_10():
    cuerpo, sesion = await _correr([_corrida("PENDIENTE"), []])

    assert cuerpo["tiendas"] == [] and cuerpo["filas"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["totales"] == {"unidades": D("0"), "valor": D("0")}
    assert len(sesion.executed_statements) == 2


async def test_only_failed_tiendas_read_no_lines_co_06():
    columnas = [_col(C, "Cali", estado="FALLIDA", codigo="X", mensaje="m")]

    cuerpo, sesion = await _correr([_corrida(), columnas])

    assert len(cuerpo["tiendas"]) == 1 and cuerpo["filas"] == []
    assert len(sesion.executed_statements) == 2


async def test_an_empty_page_reads_no_cells():
    cuerpo, sesion = await _correr([_corrida(), COLUMNAS, []])

    assert cuerpo["filas"] == [] and cuerpo["total"] == 0
    assert len(sesion.executed_statements) == 3


async def test_a_page_past_the_end_asks_for_the_real_count():
    cuerpo, sesion = await _correr(
        [_corrida(), COLUMNAS, [], [(250,)]], offset=300)

    assert cuerpo["filas"] == [] and cuerpo["total"] == 250
    sql = _sql(sesion.executed_statements[3])
    assert "count(*)" in sql and "HAVING" in sql
    assert "LIMIT" not in sql


# --- Forma del SQL ----------------------------------------------------------


async def test_the_reference_page_is_paged_in_sql_co_03():
    _, sesion = await _feliz(limite=50, offset=100)

    sql = _sql(sesion.executed_statements[2])
    assert "LIMIT 50 OFFSET 100" in sql
    assert "ORDER BY corrida_linea.codigo_referencia" in sql
    assert "HAVING sum(corrida_linea.pedido_final) > 0" in sql
    assert "count(*) OVER ()" in sql


async def test_every_query_leaves_excluded_lines_out_co_08():
    _, sesion = await _feliz()

    columnas, pagina, celdas = (
        _sql(s) for s in sesion.executed_statements[1:])
    for sql in (columnas, pagina, celdas):
        assert "corrida_linea.motivo_exclusion IS NULL" in sql


async def test_the_cells_query_asks_only_for_the_page_references_co_03():
    _, sesion = await _feliz()

    sql = _sql(sesion.executed_statements[3])
    for referencia in (R1, R2, R3):
        assert str(referencia) in sql
    assert "corrida_linea.pedido_final > 0" in sql


async def test_the_columns_are_ordered_by_tienda_name_and_never_paged():
    _, sesion = await _feliz()

    sql = _sql(sesion.executed_statements[1])
    assert "ORDER BY sucursal.nombre" in sql
    assert "LIMIT" not in sql
    assert "sum(corrida_linea.pedido_final)" in sql


async def test_the_search_filters_the_rows_but_never_the_totals_co_05():
    _, sesion = await _feliz(q="filtro_%")

    columnas, pagina, celdas = (
        _sql(s) for s in sesion.executed_statements[1:])
    assert "ILIKE" not in columnas and "ILIKE" not in celdas
    assert "corrida_linea.codigo_referencia ILIKE" in pagina
    assert "corrida_linea.nombre_parte ILIKE" in pagina
    assert "filtro\\_\\%" in pagina


async def test_the_pedido_state_filter_restricts_the_columns():
    cerradas = [COLUMNAS[1]]

    cuerpo, sesion = await _correr(
        [_corrida(), cerradas, PAGINA[:1], CELDAS[:2]],
        estado_pedido="CERRADO")

    assert [t["nombre"] for t in cuerpo["tiendas"]] == ["Bogota"]
    columnas, pagina = (_sql(s) for s in sesion.executed_statements[1:3])
    assert "corrida_sucursal.estado_pedido = 'CERRADO'" in columnas
    assert str(B) in pagina and str(A) not in pagina


async def test_amounts_always_carry_two_decimals_even_when_empty():
    columnas = [_col(A, "Armenia", unidades="0", valor="0")]

    cuerpo, _ = await _correr([_corrida(), columnas, []])

    assert str(cuerpo["tiendas"][0]["unidades"]) == "0.00"
    assert str(cuerpo["tiendas"][0]["valor"]) == "0.00"
    assert str(cuerpo["totales"]["unidades"]) == "0.00"
    assert str(cuerpo["totales"]["valor"]) == "0.00"


async def test_the_row_totals_and_cells_carry_two_decimals():
    pagina = [(R1, "00-A", "Filtro", D("12"), 1)]
    celdas = [(R1, A, D("12"))]

    cuerpo, _ = await _correr([_corrida(), COLUMNAS, pagina, celdas])

    fila = cuerpo["filas"][0]
    assert str(fila["total"]) == "12.00"
    assert str(fila["celdas"][str(A)]) == "12.00"
