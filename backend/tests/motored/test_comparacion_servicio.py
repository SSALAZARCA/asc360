"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-9, decisión
F4-8, spec SC-07..SC-13): comparar un escenario con la corrida real de la
misma semana (`services/corridas/comparacion.py`).

Con la sesión de juguete (`FakeAsyncSession`, que graba el SQL) se prueba lo
que no depende de Postgres: el EMPAREJAMIENTO válido (E-CORRIDA-063 en cada
forma de invalidarlo, antes de leer una sola línea), las tiendas que se
comparan (las OK en las dos corridas) y las que no (listadas con su motivo),
cómo arma las filas (el delta con signo, lo que sólo está de un lado vale 0)
y los totales por tienda de los dos lados, y la forma del SQL (UN FULL OUTER
JOIN paginado en SQL, sin líneas excluidas). El resultado contra datos reales
está en `pg_real/test_comparacion_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import codigos, comparacion
from app.motored.services.corridas.codigos import ErrorCorrida
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures import corridas_api as fx

ESC, REAL = uuid.UUID(int=510), uuid.UUID(int=511)
A, B, C = fx.SUC_A, fx.SUC_B, uuid.UUID(int=603)
R1, R2 = uuid.UUID(int=801), uuid.UUID(int=802)
CORTE = fx.CORTE
D = Decimal


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _c(corrida_id, *, escenario, estado="BORRADOR", corte=CORTE,
       proveedor=fx.PROVEEDOR_ID):
    codigo = "ESC-1" if escenario else "PED-1"
    return (corrida_id, codigo, estado, escenario, corte, proveedor)


def _pareja(**real):
    return [_c(ESC, escenario=True), _c(REAL, escenario=False, **real)]


def _t(corrida_id, sucursal_id, nombre, estado="OK"):
    return (corrida_id, sucursal_id, nombre, estado)


TIENDAS = [
    _t(ESC, A, "Armenia"), _t(REAL, A, "Armenia"),
    _t(ESC, B, "Bogota"), _t(REAL, B, "Bogota"),
]
FILAS = [
    (A, "Armenia", R1, "00-A", "Filtro", "AF", "AF", D("50"), D("62"),
     D("55"), 2),
    (B, "Bogota", R2, "00-B", "Bujia", None, "BM", D("0"), D("8"),
     D("0"), 2),
]
TOTALES = [
    (REAL, A, D("50"), D("500.00")), (ESC, A, D("62"), D("620.00")),
    (REAL, B, D("10"), D("100.00")), (ESC, B, D("18"), D("180.00")),
]


async def _correr(cola, **kw):
    sesion = FakeAsyncSession(execute_queue=cola)
    kw.setdefault("limite", 100)
    kw.setdefault("offset", 0)
    cuerpo = await comparacion.comparar(sesion, ESC, REAL, **kw)
    return cuerpo, sesion


async def _feliz(**kw):
    return await _correr([_pareja(), TIENDAS, FILAS, TOTALES], **kw)


async def _invalido(corridas):
    with pytest.raises(ErrorCorrida) as error:
        await _correr([corridas])
    assert error.value.codigo == codigos.E_CORRIDA_COMPARACION_INVALIDA
    return error.value


# --- El emparejamiento ------------------------------------------------------


async def test_an_unknown_scenario_is_none_after_one_query():
    cuerpo, sesion = await _correr([[_c(REAL, escenario=False)]])

    assert cuerpo is None
    assert len(sesion.executed_statements) == 1


async def test_a_real_corrida_that_does_not_exist_is_063_sc_11():
    await _invalido([_c(ESC, escenario=True)])


async def test_the_scenario_must_be_a_scenario_sc_11():
    await _invalido([
        _c(ESC, escenario=False), _c(REAL, escenario=False)])


async def test_the_real_corrida_cannot_be_a_scenario_sc_11():
    await _invalido([_c(ESC, escenario=True), _c(REAL, escenario=True)])


async def test_a_corrida_compared_with_itself_is_063():
    sesion = FakeAsyncSession(execute_queue=[[_c(ESC, escenario=True)]])

    with pytest.raises(ErrorCorrida) as error:
        await comparacion.comparar(sesion, ESC, ESC, limite=100, offset=0)

    assert error.value.codigo == codigos.E_CORRIDA_COMPARACION_INVALIDA


async def test_another_fecha_corte_is_063_sc_10():
    error = await _invalido(_pareja(corte=datetime.date(2026, 9, 28)))

    assert "fecha de corte" in error.mensaje


async def test_another_proveedor_is_063():
    await _invalido(_pareja(proveedor=uuid.UUID(int=999)))


@pytest.mark.parametrize(
    "estado", ["PENDIENTE", "CALCULANDO", "FALLIDA", "ANULADA"])
async def test_a_real_corrida_that_is_not_calculated_is_063(estado):
    await _invalido(_pareja(estado=estado))


@pytest.mark.parametrize("estado", ["BORRADOR", "CERRADA"])
async def test_a_calculated_real_corrida_compares_whatever_its_pedidos(
        estado):
    cuerpo, _ = await _correr(
        [_pareja(estado=estado), TIENDAS, FILAS, TOTALES])

    assert cuerpo["real"]["estado"] == estado


async def test_an_invalid_pairing_reads_no_lines():
    sesion = FakeAsyncSession(execute_queue=[_pareja(estado="ANULADA")])

    with pytest.raises(ErrorCorrida):
        await comparacion.comparar(sesion, ESC, REAL, limite=1, offset=0)

    assert len(sesion.executed_statements) == 1


# --- La respuesta -----------------------------------------------------------


async def test_the_header_names_both_corridas_and_the_corte():
    cuerpo, _ = await _feliz()

    assert cuerpo["escenario"] == {
        "id": ESC, "codigo": "ESC-1", "estado": "BORRADOR",
        "es_escenario": True}
    assert cuerpo["real"]["id"] == REAL
    assert cuerpo["real"]["es_escenario"] is False
    assert cuerpo["fecha_corte"] == CORTE


async def test_the_comparison_takes_four_queries_whatever_its_size():
    _, sesion = await _feliz()

    assert len(sesion.executed_statements) == 4


async def test_a_row_carries_both_sides_and_a_signed_delta_sc_07():
    cuerpo, _ = await _feliz()

    [fila, _] = cuerpo["filas"]
    assert fila["sucursal"] == "Armenia" and fila["sucursal_id"] == A
    assert (fila["codigo"], fila["nombre"]) == ("00-A", "Filtro")
    assert (fila["sugerido_real"], fila["sugerido_prueba"]) == (
        D("50"), D("62"))
    assert fila["delta"] == D("12")
    assert fila["pedido_final_real"] == D("55")


async def test_a_reference_on_one_side_only_counts_as_zero_sc_08():
    cuerpo, _ = await _feliz()

    [_, fila] = cuerpo["filas"]
    assert fila["sugerido_real"] == D("0")
    assert fila["sugerido_prueba"] == D("8") and fila["delta"] == D("8")
    assert fila["clase_real"] is None and fila["clase_prueba"] == "BM"


async def test_a_lower_scenario_gives_a_negative_delta():
    filas = [(A, "Armenia", R1, "00-A", None, "AF", "AF", D("50"), D("40"),
              D("50"), 1)]

    cuerpo, _ = await _correr([_pareja(), TIENDAS, filas, TOTALES])

    assert cuerpo["filas"][0]["delta"] == D("-10")


async def test_the_paging_fields_report_the_row_count():
    cuerpo, _ = await _feliz(limite=2, offset=0)

    assert (cuerpo["total"], cuerpo["limite"], cuerpo["offset"]) == (2, 2, 0)


async def test_totals_per_tienda_show_both_sides_and_the_gap_sc_09():
    cuerpo, _ = await _feliz()

    [armenia, bogota] = cuerpo["totales_por_sucursal"]
    assert armenia == {
        "sucursal_id": A, "nombre": "Armenia",
        "unidades_real": D("50"), "unidades_prueba": D("62"),
        "diferencia_unidades": D("12"),
        "valor_real": D("500.00"), "valor_prueba": D("620.00"),
        "diferencia_valor": D("120.00")}
    assert bogota["diferencia_unidades"] == D("8")


async def test_a_tienda_missing_from_a_side_is_not_comparable_sc_13():
    tiendas = [*TIENDAS, _t(ESC, C, "Cali"),
               _t(REAL, C, "Cali", estado="FALLIDA")]

    cuerpo, sesion = await _correr(
        [_pareja(), tiendas, FILAS, TOTALES])

    assert [t["sucursal_id"] for t in cuerpo["totales_por_sucursal"]] == [
        A, B]
    [cali] = cuerpo["no_comparables"]
    assert cali["sucursal_id"] == C and cali["nombre"] == "Cali"
    assert (cali["estado_real"], cali["estado_prueba"]) == ("FALLIDA", "OK")
    assert "Cali" not in _sql(sesion.executed_statements[2])
    assert str(C) not in _sql(sesion.executed_statements[2])


async def test_a_tienda_only_in_the_real_corrida_is_not_comparable():
    tiendas = [*TIENDAS, _t(REAL, C, "Cali")]

    cuerpo, _ = await _correr([_pareja(), tiendas, FILAS, TOTALES])

    [cali] = cuerpo["no_comparables"]
    assert (cali["estado_real"], cali["estado_prueba"]) == ("OK", None)
    assert "no está en el escenario" in cali["motivo"]


async def test_with_nothing_to_compare_no_lines_are_read():
    tiendas = [_t(ESC, A, "Armenia"), _t(REAL, B, "Bogota")]

    cuerpo, sesion = await _correr([_pareja(), tiendas])

    assert cuerpo["filas"] == [] and cuerpo["total"] == 0
    assert cuerpo["totales_por_sucursal"] == []
    assert len(cuerpo["no_comparables"]) == 2
    assert len(sesion.executed_statements) == 2


async def test_the_not_comparable_are_ordered_by_name():
    tiendas = [_t(ESC, C, "Cali"), _t(REAL, B, "Bogota")]

    cuerpo, _ = await _correr([_pareja(), tiendas])

    assert [t["nombre"] for t in cuerpo["no_comparables"]] == [
        "Bogota", "Cali"]


async def test_a_tienda_filter_that_is_not_comparable_gives_no_rows():
    cuerpo, sesion = await _correr(
        [_pareja(), TIENDAS, TOTALES], sucursal_id=C)

    assert cuerpo["filas"] == [] and cuerpo["total"] == 0
    assert len(cuerpo["totales_por_sucursal"]) == 2
    assert len(sesion.executed_statements) == 3


async def test_a_page_past_the_end_asks_for_the_real_count():
    cuerpo, sesion = await _correr(
        [_pareja(), TIENDAS, [], [(250,)], TOTALES], offset=300)

    assert cuerpo["filas"] == [] and cuerpo["total"] == 250
    contar = _sql(sesion.executed_statements[3])
    assert "count(*)" in contar and "LIMIT" not in contar


# --- Forma del SQL ----------------------------------------------------------


async def test_the_rows_are_one_full_outer_join_paged_in_sql():
    _, sesion = await _feliz(limite=50, offset=100)

    sql = _sql(sesion.executed_statements[2])
    assert "FULL OUTER JOIN" in sql
    assert "LIMIT 50 OFFSET 100" in sql
    assert "count(*) OVER ()" in sql
    assert "ORDER BY sucursal.nombre" in sql


async def test_both_sides_leave_excluded_lines_out_and_use_the_scenario():
    _, sesion = await _feliz()

    sql = _sql(sesion.executed_statements[2])
    assert sql.count("corrida_linea.motivo_exclusion IS NULL") == 2
    assert str(ESC) in sql and str(REAL) in sql


async def test_only_the_comparable_tiendas_enter_the_row_query():
    _, sesion = await _feliz()

    filas, totales = (_sql(s) for s in sesion.executed_statements[2:])
    for sql in (filas, totales):
        assert str(A) in sql and str(B) in sql


async def test_solo_diferencias_adds_the_inequality_only_when_asked():
    _, normal = await _feliz()
    _, filtrada = await _feliz(solo_diferencias=True)

    base = _sql(normal.executed_statements[2])
    solo = _sql(filtrada.executed_statements[2])
    assert " != " not in base and "<>" not in base
    assert "<>" in solo or " != " in solo


async def test_a_tienda_filter_narrows_both_sides_of_the_join():
    _, sesion = await _feliz(sucursal_id=B)

    sql = _sql(sesion.executed_statements[2])
    assert str(B) in sql and str(A) not in sql


async def test_totals_come_from_one_grouped_query_over_both_corridas():
    _, sesion = await _feliz(sucursal_id=B)

    sql = _sql(sesion.executed_statements[3])
    assert ("GROUP BY corrida_linea.corrida_id, "
            "corrida_linea.sucursal_id") in sql
    assert str(A) in sql and str(B) in sql
    assert "round(corrida_linea.pedido_sugerido" in sql


async def test_a_side_that_is_missing_still_shows_two_decimals():
    filas = [(B, "Bogota", R2, "00-B", "Bujia", None, "BM", D("0"), D("8"),
              D("0"), 1)]

    cuerpo, _ = await _correr([_pareja(), TIENDAS, filas, []])

    fila = cuerpo["filas"][0]
    assert str(fila["sugerido_real"]) == "0.00"
    assert str(fila["delta"]) == "8.00"
    assert str(fila["pedido_final_real"]) == "0.00"


async def test_a_comparable_tienda_without_lines_totals_zero_with_decimals():
    cuerpo, _ = await _correr([_pareja(), TIENDAS, [], [], []])

    [armenia, _] = cuerpo["totales_por_sucursal"]
    assert str(armenia["unidades_real"]) == "0.00"
    assert str(armenia["diferencia_valor"]) == "0.00"
