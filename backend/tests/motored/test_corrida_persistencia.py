"""
Motored Pedidos F3 "Motor", S6a (sdd/motored-pedidos-motor, ADR-3/ADR-4,
decisión #16): persistencia de una sucursal calculada.

Tres capas: (1) el armado PURO de filas (`armar_filas`), donde se cuantiza
sólo al escribir con ROUND_HALF_UP; (2) el guardado transaccional por
sucursal, guardado por `estado = 'CALCULANDO'` (T18: una corrida cerrada
rechaza cualquier escritura); (3) el vínculo `corrida_carga`.
"""
import dataclasses
import uuid
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.services.corridas import codigos
from app.motored.services.corridas import persistencia as pe
from app.motored.services.corridas.cargador import DatosSucursal
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import NodoMaestro
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
    parametros_legacy,
)

CORRIDA = uuid.UUID(int=900)
IDS = {letra: uuid.UUID(int=i) for i, letra in enumerate("ABCD", start=1)}
CEROS = (0, 0, 0, 0, 0, 0)
UNOS = (1, 1, 1, 1, 1, 1)


def _ref(letra, ventas=CEROS, perdidas=CEROS, **kw):
    return entrada(
        ventas, perdidas, codigo=f"REF-{letra}",
        referencia_id=IDS[letra], **kw)


def _armar(entradas, sucursal=None, *, nodos=(), consolidar=False,
           perdida=False):
    sucursal = sucursal or atributos()
    params = parametros_legacy(
        consolidar_sustituidas=consolidar, incluir_demanda_perdida=perdida)
    resoluciones = resolver_cadenas({n.referencia_id: n for n in nodos})
    resultado = calcular_sucursal(
        entradas, sucursal, params, resoluciones)
    filas = pe.armar_filas(
        CORRIDA, sucursal, entradas, resultado, consolidar=consolidar)
    return resultado, filas


def _sql(sentencia) -> str:
    return str(sentencia.compile(dialect=postgresql.dialect()))


def _linea_de(filas, letra):
    return next(
        f for f in filas.lineas if f["referencia_id"] == IDS[letra])


# --- Fila de línea: cuantización sólo al escribir ---------------------------


def test_pattern_row_persists_the_ten_documented_values():
    resultado, filas = _armar([fila_patron()])

    fila = filas.lineas[0]
    assert fila["demanda_ponderada"] == Decimal("85.428571")
    assert fila["meses_cobertura"] == Decimal("1.750000")
    assert fila["stock_objetivo"] == Decimal("149.500000")
    assert fila["inventario_final"] == Decimal("97.00")
    assert fila["pedido_sugerido"] == Decimal("50.00")
    assert fila["valor_pedido"] == Decimal("23037.50")
    assert fila["cobertura_final"] == Decimal("1.720736")
    assert fila["clase"] == "CF"
    assert fila["estado_quiebre"] == "NORMAL"
    assert fila["punto_minimo"] == Decimal("64.071429")


def test_pedido_final_equals_the_suggestion_in_f3():
    _, filas = _armar([fila_patron()])

    fila = filas.lineas[0]
    assert fila["pedido_final"] == fila["pedido_sugerido"] == Decimal("50")


def test_raw_inputs_are_stored_next_to_the_outputs():
    _, filas = _armar([fila_patron()])

    fila = filas.lineas[0]
    meses = [fila[f"venta_m{i}"] for i in (6, 5, 4, 3, 2, 1)]
    assert meses == [Decimal(v) for v in (102, 112, 108, 105, 74, 59)]
    assert (fila["inventario"], fila["transito"], fila["backorder"]) == (
        Decimal(27), Decimal(70), Decimal(0))
    assert fila["ajuste"] == Decimal(-3)
    assert fila["precio"] == Decimal("460.75")
    assert fila["unidad_empaque"] == 1
    assert fila["venta_m0"] is None and fila["perdida_m0"] is None
    assert fila["venta_m0_proyectada"] is None


def test_every_column_of_corrida_linea_is_set_by_the_row_builder():
    _, filas = _armar([fila_patron()])

    columnas = {c.key for c in CorridaLinea.__table__.columns} - {"id"}
    assert set(filas.lineas[0]) == columnas


def _linea_con(**cambios):
    resultado, _ = _armar([fila_patron()])
    return dataclasses.replace(resultado.lineas[0], **cambios)


def test_quantization_is_half_up_away_from_zero_on_the_seventh_decimal():
    linea = _linea_con(n=Fraction(1234565, 10 ** 7))

    fila = pe.fila_linea(CORRIDA, uuid.uuid4(), linea, linea.entrada)

    assert fila["demanda_ponderada"] == Decimal("0.123457")


def test_quantization_of_a_negative_half_goes_away_from_zero():
    linea = _linea_con(n=Fraction(-1234565, 10 ** 7))

    fila = pe.fila_linea(CORRIDA, uuid.uuid4(), linea, linea.entrada)

    assert fila["demanda_ponderada"] == Decimal("-0.123457")


def test_null_coverage_stays_null_when_n_is_zero():
    linea = _linea_con(cobertura_final=None, cobertura_actual=None)

    fila = pe.fila_linea(CORRIDA, uuid.uuid4(), linea, linea.entrada)

    assert fila["cobertura_final"] is None
    assert fila["cobertura_actual"] is None


def test_ponderado_projection_and_m0_inputs_are_stored():
    cruda = dataclasses.replace(
        fila_patron(), venta_m0=Decimal("63"), perdida_m0=Decimal("0"))
    linea = _linea_con(venta_m0_proyectada=Fraction(135))

    fila = pe.fila_linea(CORRIDA, uuid.uuid4(), linea, cruda)

    assert fila["venta_m0"] == Decimal("63")
    assert fila["venta_m0_proyectada"] == Decimal("135.000000")


def test_engine_line_warnings_join_the_flags_sorted():
    cruda = dataclasses.replace(
        _ref("A", (5, 5, 5, 5, 5, 5), unidad_empaque=0),
        banderas=frozenset({"SIN_PRECIO"}))

    _, filas = _armar([cruda])

    assert filas.lineas[0]["banderas"] == [
        "SIN_PRECIO", "UNIDAD_EMPAQUE_INVALIDA"]


# --- Consolidación: líneas receptoras y excluidas ---------------------------


def _con_sustitucion(perdida=False):
    vieja = _ref("A", (5, 0, 3, 0, 2, 4), inventario=30, transito=20,
                 backorder=5)
    final = _ref("B", (1, 1, 1, 1, 1, 1), inventario=10)
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"])]
    return _armar([vieja, final], nodos=nodos, consolidar=True,
                  perdida=perdida)


def test_the_receiving_line_keeps_its_own_raw_inputs():
    _, filas = _con_sustitucion()

    fila = _linea_de(filas, "B")
    assert [fila[f"venta_m{i}"] for i in (6, 5, 4, 3, 2, 1)] == [
        Decimal(1)] * 6
    assert fila["inventario"] == Decimal(10)


def test_the_received_stock_goes_to_y_recibido_and_the_final_y():
    _, filas = _con_sustitucion()

    fila = _linea_de(filas, "B")
    assert fila["y_recibido"] == Decimal("55.00")
    assert fila["inventario_final"] == Decimal("65.00")


def test_a_line_that_receives_nothing_has_zero_y_recibido():
    _, filas = _armar([fila_patron()])

    assert filas.lineas[0]["y_recibido"] == Decimal("0.00")
    assert filas.lineas[0]["detalle_consolidacion"] is None


def test_the_receiving_line_lists_the_origins_it_absorbed():
    _, filas = _con_sustitucion()

    detalle = _linea_de(filas, "B")["detalle_consolidacion"]
    origen = detalle["origenes"][0]
    assert origen["codigo"] == "REF-A"
    assert origen["referencia_id"] == str(IDS["A"])
    assert Decimal(origen["inventario"]) == 30


def test_the_origin_detail_does_not_depend_on_the_decimal_scale():
    def _detalle_con(escala):
        vieja = _ref("A", (5, 0, 3, 0, 2, 4), inventario=escala("30"),
                     transito=escala("0"), backorder=escala("5"))
        final = _ref("B", UNOS)
        nodos = [NodoMaestro(IDS["A"], False, IDS["B"])]
        sucursal = atributos()
        _, filas = _armar(
            [vieja, final], sucursal, nodos=nodos, consolidar=True)
        return _linea_de(filas, "B")["detalle_consolidacion"]

    sin_escala = _detalle_con(lambda v: v)
    con_escala = _detalle_con(lambda v: f"{v}.00")

    assert sin_escala == con_escala
    assert sin_escala["origenes"][0]["transito"] == "0.00"


def test_the_replaced_reference_is_stored_as_an_excluded_line():
    _, filas = _con_sustitucion()

    fila = _linea_de(filas, "A")
    assert fila["motivo_exclusion"] == "SUSTITUIDA"
    assert fila["sustituta_final_id"] == IDS["B"]
    assert fila["venta_m6"] == Decimal(5) and fila["inventario"] == Decimal(30)


def test_an_excluded_line_carries_no_calculated_output():
    _, filas = _con_sustitucion()

    fila = _linea_de(filas, "A")
    for columna in ("demanda_ponderada", "orden_abc", "clase",
                    "pedido_sugerido", "valor_pedido", "estado_quiebre",
                    "stock_objetivo", "inventario_final", "y_recibido"):
        assert fila[columna] is None, columna


def test_a_reference_without_replacement_is_excluded_without_a_link():
    vieja = _ref("C", (4, 4, 4, 4, 4, 4))
    nodos = [NodoMaestro(IDS["C"], False, None)]

    _, filas = _armar([vieja, _ref("B", UNOS)], nodos=nodos,
                      consolidar=True)

    fila = _linea_de(filas, "C")
    assert fila["motivo_exclusion"] == "INACTIVA_SIN_REEMPLAZO"
    assert fila["sustituta_final_id"] is None


def test_an_unlisted_lost_only_reference_is_kept_as_an_auxiliary_input():
    perdedora = _ref("C", CEROS, (0, 0, 0, 0, 0, 8))
    vieja = _ref("A", (5, 0, 3, 0, 2, 4))
    final = _ref("B", UNOS)
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"]),
             NodoMaestro(IDS["C"], False, IDS["B"])]

    _, filas = _armar([perdedora, vieja, final], nodos=nodos,
                      consolidar=True, perdida=True)

    auxiliares = filas.sucursal["parametros"]["entradas_auxiliares"]
    assert [pe.deserializar_entrada(a).codigo for a in auxiliares] == [
        "REF-C"]
    assert pe.deserializar_entrada(auxiliares[0]).perdidas[-1] == Decimal(8)


def test_without_consolidation_no_auxiliary_input_is_stored():
    perdedora = _ref("C", CEROS, (0, 0, 0, 0, 0, 8))

    _, filas = _armar([perdedora, _ref("B", UNOS)])

    assert filas.sucursal["parametros"]["entradas_auxiliares"] == []


def test_a_zero_final_that_receives_a_listed_stock_is_kept_as_auxiliary():
    vieja = _ref("A", CEROS, inventario=9)
    final = _ref("B", CEROS)
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"])]

    resultado, filas = _armar(
        [vieja, final], nodos=nodos, consolidar=True)

    assert [x.motivo for x in resultado.excluidas] == ["SUSTITUIDA"]
    codigos_aux = [
        pe.deserializar_entrada(a).codigo
        for a in filas.sucursal["parametros"]["entradas_auxiliares"]]
    assert codigos_aux == ["REF-B"]


# --- Serialización de entradas ----------------------------------------------


def test_an_input_survives_the_json_round_trip():
    original = dataclasses.replace(
        _ref("A", (1, 2, 3, 4, 5, 6), (0, 0, 1, 0, 0, 2), precio="12.50",
             unidad_empaque=4, inventario="7.25", venta_m0="3",
             perdida_m0="1"),
        nombre="Bujía", linea_comercial="MOTOR",
        banderas=frozenset({"SIN_PRECIO", "EMPAQUE_CORREGIDO"}))

    restaurada = pe.deserializar_entrada(pe.serializar_entrada(original))

    assert restaurada == original


def test_an_input_without_price_or_m0_round_trips_with_nones():
    original = _ref("A", (1, 2, 3, 4, 5, 6))

    restaurada = pe.deserializar_entrada(pe.serializar_entrada(original))

    assert restaurada.precio is None and restaurada.venta_m0 is None
    assert restaurada == original


# --- Resumen ----------------------------------------------------------------


def test_the_resumen_has_the_ten_classes_and_a_total_row():
    _, filas = _armar([fila_patron()])

    clases = [f["clase"] for f in filas.resumen]
    assert clases == [
        "AF", "AM", "AS", "BF", "BM", "BS", "CF", "CM", "CS", "DS", "TOTAL"]


def test_the_resumen_row_of_the_line_class_holds_its_order():
    _, filas = _armar([fila_patron()])

    cf = next(f for f in filas.resumen if f["clase"] == "CF")
    assert cf["unidades"] == Decimal("50.00")
    assert cf["referencias"] == 1
    assert cf["valor"] == Decimal("23037.50")
    assert cf["porcentaje_peso"] == Decimal("1.000000")


def test_the_total_row_and_empty_classes_are_zero_weighted_correctly():
    _, filas = _armar([fila_patron()])

    total = filas.resumen[-1]
    vacia = next(f for f in filas.resumen if f["clase"] == "AF")
    assert total["unidades"] == Decimal("50.00")
    assert total["porcentaje_peso"] == Decimal("1.000000")
    assert vacia["unidades"] == Decimal("0.00")
    assert vacia["porcentaje_peso"] == Decimal("0.000000")


def test_resumen_rows_carry_the_corrida_and_sucursal_keys():
    sucursal = atributos()

    _, filas = _armar([fila_patron()], sucursal)

    assert {(f["corrida_id"], f["sucursal_id"]) for f in filas.resumen} == {
        (CORRIDA, sucursal.sucursal_id)}


# --- Fila de la sucursal ----------------------------------------------------


def test_the_sucursal_row_summarizes_lines_units_and_value():
    sucursal = atributos()

    resultado, filas = _armar([fila_patron()], sucursal)

    valores = filas.sucursal
    assert valores["estado"] == "OK"
    assert valores["lineas"] == 1 and valores["excluidas"] == 0
    assert valores["unidades"] == Decimal("50.00")
    assert valores["valor"] == Decimal("23037.50")
    assert valores["divisor"] == 21
    assert valores["buckets_operados"] == 0b111111
    assert valores["dias_empaque"] == Decimal("3.00")
    assert valores["dias_entre_pedidos"] == Decimal("30.00")
    assert valores["fecha_apertura"] is None
    assert valores["codigo"] is None and valores["mensaje"] is None


def test_the_sucursal_row_keeps_the_exact_class_coverages():
    _, filas = _armar([fila_patron()])

    assert filas.sucursal["coberturas"] == {"CF": "7/4"}


def test_the_sucursal_row_keeps_the_name_for_the_replay():
    _, filas = _armar([fila_patron()], atributos(nombre="MANIZALES"))

    assert filas.sucursal["parametros"]["nombre"] == "MANIZALES"


def test_the_bucket_bitmask_marks_only_the_operated_months():
    sucursal = atributos(
        fecha_corte=date(2026, 9, 15), fecha_apertura=date(2026, 6, 1))

    _, filas = _armar([_ref("A", (0, 0, 0, 0, 3, 4))], sucursal)

    assert filas.sucursal["divisor"] == 15
    assert filas.sucursal["buckets_operados"] == 0b111000


def test_a_skipped_sucursal_records_the_102_warning_and_no_rows():
    sucursal = atributos(
        nombre="NUEVA", fecha_corte=date(2026, 9, 15),
        fecha_apertura=date(2026, 9, 5))

    resultado, filas = _armar([_ref("A", (0, 0, 0, 0, 0, 4))], sucursal)

    valores = filas.sucursal
    assert valores["estado"] == "OMITIDA"
    assert valores["codigo"] == codigos.A_CORRIDA_SUCURSAL_OMITIDA
    assert valores["mensaje"] == (
        "Sucursal NUEVA abrió hace menos de un mes: sin historia para "
        "calcular el pedido")
    assert valores["lineas"] == 0 and valores["divisor"] == 0
    assert valores["buckets_operados"] == 0
    assert filas.lineas == [] and filas.resumen == []


def test_the_engine_warnings_are_listed_on_the_sucursal():
    sucursal = atributos()

    resultado, filas = _armar(
        [_ref("A", (0, 0, 0, 0, 0, 4)), _ref("B", (0, 0, 0, 0, 0, -4))],
        sucursal)

    advertencias = filas.sucursal["parametros"]["advertencias"]
    assert {a["codigo"] for a in advertencias} == {
        a.codigo for a in resultado.advertencias}


def test_a_line_without_price_gets_the_104_warning_from_its_flags():
    sin_precio = dataclasses.replace(
        _ref("A", (5, 5, 5, 5, 5, 5)), banderas=frozenset({"SIN_PRECIO"}))

    _, filas = _armar([sin_precio])

    esperado = {
        "codigo": codigos.A_CORRIDA_SIN_PRECIO,
        "mensaje": codigos.mensaje(
            codigos.A_CORRIDA_SIN_PRECIO, referencia="REF-A"),
    }
    assert esperado in filas.sucursal["parametros"]["advertencias"]


def test_a_substitute_that_only_enters_by_consolidation_is_warned_too():
    vieja = _ref("A", (5, 0, 3, 0, 2, 4))
    final = dataclasses.replace(
        _ref("B", CEROS), banderas=frozenset({"SIN_PRECIO"}))
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"])]

    _, filas = _armar([vieja, final], nodos=nodos, consolidar=True)

    mensajes = [
        a["mensaje"] for a in filas.sucursal["parametros"]["advertencias"]
        if a["codigo"] == codigos.A_CORRIDA_SIN_PRECIO]
    assert mensajes == [
        codigos.mensaje(codigos.A_CORRIDA_SIN_PRECIO, referencia="REF-B")]


def test_an_excluded_reference_without_price_is_not_warned():
    vieja = dataclasses.replace(
        _ref("A", (5, 5, 5, 5, 5, 5)), banderas=frozenset({"SIN_PRECIO"}))
    final = _ref("B", UNOS, precio="10")
    nodos = [NodoMaestro(IDS["A"], False, IDS["B"])]

    _, filas = _armar([vieja, final], nodos=nodos, consolidar=True)

    advertencias = filas.sucursal["parametros"]["advertencias"]
    assert all(
        a["codigo"] != codigos.A_CORRIDA_SIN_PRECIO for a in advertencias)


def test_the_rows_are_deterministic_for_the_same_inputs():
    entradas = [_ref("A", (9, 8, 7, 6, 5, 4)), _ref("B", (1, 2, 3, 4, 5, 6))]

    sucursal = atributos()

    _, primera = _armar(entradas, sucursal)
    _, segunda = _armar(list(reversed(entradas)), sucursal)

    assert primera == segunda


# --- Bloques ----------------------------------------------------------------


def test_blocks_split_a_sequence_without_losing_or_repeating_rows():
    bloques = list(pe.bloques(list(range(7)), 3))

    assert bloques == [[0, 1, 2], [3, 4, 5], [6]]


def test_blocks_of_an_empty_sequence_are_empty():
    assert list(pe.bloques([], 3)) == []


def test_the_block_size_keeps_each_insert_under_the_driver_limit():
    columnas = len(CorridaLinea.__table__.columns) - 1

    assert pe.TAMANO_BLOQUE * columnas < 32767


# --- Guardado por sucursal --------------------------------------------------


def _datos_y_resultado(entradas=None, sucursal=None):
    sucursal = sucursal or atributos()
    entradas = entradas or [fila_patron()]
    resultado = calcular_sucursal(entradas, sucursal, parametros_legacy())
    return DatosSucursal(sucursal, tuple(entradas)), resultado


async def test_saving_a_sucursal_runs_the_guard_deletes_inserts_and_updates():
    datos, resultado = _datos_y_resultado()
    db = FakeAsyncSession(execute_queue=[[1], [], [], [], [], [], []])

    await pe.guardar_sucursal(db, CORRIDA, datos, resultado)

    sentencias = [_sql(s) for s in db.executed_statements]
    assert sentencias[0].startswith("UPDATE corrida SET")
    assert "estado = %(estado_1)s" in sentencias[0]
    assert "RETURNING corrida.id" in sentencias[0]
    assert sentencias[1].startswith("DELETE FROM corrida_linea")
    assert sentencias[2].startswith("DELETE FROM corrida_resumen")
    assert sentencias[3].startswith("INSERT INTO corrida_linea")
    assert sentencias[4].startswith("INSERT INTO corrida_resumen")
    assert sentencias[5].startswith("UPDATE corrida_sucursal SET")
    assert sentencias[6].startswith("UPDATE corrida SET")
    assert len(sentencias) == 7


async def test_the_inserted_line_carries_the_quantized_values():
    datos, resultado = _datos_y_resultado()
    db = FakeAsyncSession(execute_queue=[[1], [], [], [], [], [], []])

    await pe.guardar_sucursal(db, CORRIDA, datos, resultado)

    params = db.executed_statements[3].compile(
        dialect=postgresql.dialect()).params
    assert params["pedido_sugerido_m0"] == Decimal("50.00")
    assert params["demanda_ponderada_m0"] == Decimal("85.428571")
    assert params["corrida_id_m0"] == CORRIDA


async def test_a_closed_corrida_rejects_any_write_and_nothing_is_touched():
    datos, resultado = _datos_y_resultado()
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(pe.ErrorCorrida) as error:
        await pe.guardar_sucursal(db, CORRIDA, datos, resultado)

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert len(db.executed_statements) == 1


async def test_an_omitted_sucursal_writes_no_lines_and_no_summary():
    sucursal = atributos(
        fecha_corte=date(2026, 9, 15), fecha_apertura=date(2026, 9, 5))
    datos, resultado = _datos_y_resultado(
        [_ref("A", (0, 0, 0, 0, 0, 4))], sucursal)
    db = FakeAsyncSession(execute_queue=[[1], [], [], [], []])

    await pe.guardar_sucursal(db, CORRIDA, datos, resultado)

    sentencias = [_sql(s) for s in db.executed_statements]
    assert not any(s.startswith("INSERT") for s in sentencias)
    assert any(s.startswith("UPDATE corrida_sucursal") for s in sentencias)


async def test_the_progress_counts_finished_sucursales_instead_of_adding_one():
    datos, resultado = _datos_y_resultado()
    db = FakeAsyncSession(execute_queue=[[1], [], [], [], [], [], []])

    await pe.guardar_sucursal(db, CORRIDA, datos, resultado)

    progreso = _sql(db.executed_statements[6])
    assert "count(*)" in progreso
    assert "sucursales_procesadas" in progreso


async def test_marking_a_sucursal_failed_stores_code_and_message():
    sucursal = uuid.uuid4()
    db = FakeAsyncSession(execute_queue=[[1], [], []])

    await pe.marcar_sucursal_fallida(
        db, CORRIDA, sucursal, "E-CORRIDA-021", "La sucursal X no tiene SIC.")

    actualizacion = db.executed_statements[1].compile(
        dialect=postgresql.dialect())
    assert _sql(db.executed_statements[1]).startswith(
        "UPDATE corrida_sucursal SET")
    assert actualizacion.params["estado"] == "FALLIDA"
    assert actualizacion.params["codigo"] == "E-CORRIDA-021"
    assert actualizacion.params["mensaje"] == "La sucursal X no tiene SIC."


async def test_marking_a_sucursal_failed_on_a_closed_corrida_is_rejected():
    db = FakeAsyncSession(execute_queue=[[]])

    with pytest.raises(pe.ErrorCorrida):
        await pe.marcar_sucursal_fallida(
            db, CORRIDA, uuid.uuid4(), "E-CORRIDA-099", "x")


# --- Vínculo con las cargas -------------------------------------------------


def test_only_the_used_cargas_are_linked_with_their_upper_case_type():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = FakeAsyncSession()

    pe.registrar_cargas(
        db, CORRIDA, {"ventas": (a, b), "inventario": (c,), "backorder": ()})

    vinculos = {(v.carga_id, v.tipo) for v in db.added_of_type(CorridaCarga)}
    assert vinculos == {(a, "VENTAS"), (b, "VENTAS"), (c, "INVENTARIO")}
    assert all(v.corrida_id == CORRIDA for v in db.added_of_type(CorridaCarga))


def test_the_linked_types_map_to_their_carga_type():
    """Los cinco del preflight más la demanda perdida EXCEL (S7)."""
    assert pe.TIPO_CARGA == {
        "ventas": "VENTAS", "inventario": "INVENTARIO",
        "backorder": "BACKORDER", "facturas": "FACTURAS_PEDIDOS",
        "ingresos": "INGRESOS_FACTURAS",
        "demanda_perdida": "DEMANDA_PERDIDA"}
