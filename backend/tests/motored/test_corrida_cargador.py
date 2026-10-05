"""
Motored Pedidos F3 "Motor", S5b (sdd/motored-pedidos-motor, ADR-6): cargador
por sucursal (consultas set-based + armado puro de `EntradaReferencia`).

Escenarios: orígenes sumados, demanda perdida por mes de ocurrencia, M0 sólo
cuando es efectivo, V por sucursal / W y X por SIC, T13, T14, filtro de cargas
ANULADO (con la excepción de las filas BOT), atributos de la sucursal
(E-CORRIDA-020/021) y el contrato con la consolidación (la sustituta final
siempre viene en las entradas).
"""
import datetime
import uuid
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.services.corridas import cargador as cg
from app.motored.services.corridas import codigos
from app.motored.services.corridas.parametros_corrida import (
    ParametrosCorrida)
from app.motored.services.corridas.transito_corte import TransitoAlCorte
from app.motored.services.corridas.vigencia import ResultadoVigencia
from app.motored.services.motor.mes_en_curso import ResolucionMesEnCurso
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    MesEnCurso, NodoMaestro, ParametrosMotor)
from tests.motored.conftest import FakeAsyncSession
from tests.motored.fixtures.motor.constructores import atributos

CORTE = datetime.date(2026, 9, 21)
CORTE_INVENTARIO = datetime.date(2026, 9, 19)
CORTE_BACKORDER = datetime.date(2026, 9, 18)
SUC, OTRA_SUC = uuid.uuid4(), uuid.uuid4()
REF_A, REF_B, REF_C, REF_D = (uuid.uuid4() for _ in range(4))
PROVEEDOR = cg.FilaProveedor(
    id=uuid.uuid4(), dias_empaque_default=4, dias_transito_default=5,
    dias_seguridad_default=Decimal("3"))
PONDERADO = MesEnCurso("PONDERADO", 14, 30, Fraction(3))


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def _num(valor):
    return None if valor is None else Decimal(valor)


def _serie(ref, cerrados=(0,) * 6, m0=None):
    """Fila de un pivote mensual: c1 = M6 (el más viejo) .. c6 = M1."""
    valores = {f"c{i}": _num(v) for i, v in enumerate(cerrados, 1)}
    if m0 is not None:
        valores["c0"] = _num(m0)
    return SimpleNamespace(referencia_id=ref, **valores)


def _total(ref, cantidad):
    return SimpleNamespace(referencia_id=ref, total=Decimal(cantidad))


def _attr(ref, codigo, precio="100", unidad=1, corregido=False):
    return SimpleNamespace(
        id=ref, codigo=codigo, nombre=f"Repuesto {codigo}",
        linea_comercial="MOTOR", precio_normal=_num(precio),
        unidad_empaque=unidad, unidad_empaque_advertencia=corregido)


def _contexto(**cambios):
    base = dict(
        proveedor=PROVEEDOR, fecha_corte=CORTE,
        corte_inventario=CORTE_INVENTARIO, corte_backorder=CORTE_BACKORDER)
    return cg.ContextoCarga(**{**base, **cambios})


async def _cargar(ventas=(), perdidas=(), inventario=(), backorder=(),
                  referencias=(), **cambios):
    db = FakeAsyncSession(execute_queue=[
        list(ventas), list(perdidas), list(inventario), list(backorder),
        list(referencias)])
    resultado = await cg.cargar_entradas(db, SUC, _contexto(**cambios))
    return resultado, db


def _por_codigo(resultado):
    return {e.codigo: e for e in resultado.entradas}


# --- Universo y series mensuales ---------------------------------------------


async def test_the_universe_is_sales_in_a_closed_month_and_m0_never_counts():
    ventas = [
        _serie(REF_A, (10, 0, 0, 0, 0, 5)),
        _serie(REF_B, (None,) * 6, m0=9),
        _serie(REF_C, (0, 0, 0, -3, 0, 0)),
    ]

    resultado, db = await _cargar(
        ventas, referencias=[_attr(REF_A, "A-1")],
        mes_en_curso=PONDERADO)

    assert [e.codigo for e in resultado.entradas] == ["A-1"]
    consulta = _sql(db.executed_statements[4])
    assert str(REF_A) in consulta
    assert str(REF_B) not in consulta and str(REF_C) not in consulta


async def test_series_keep_the_m6_to_m1_order_for_sales_and_lost_demand():
    resultado, _ = await _cargar(
        [_serie(REF_A, (1, 2, 3, 4, 5, 6))],
        perdidas=[_serie(REF_A, (0, 0, 0, 0, 2, 7))],
        referencias=[_attr(REF_A, "A-1")])

    entrada = resultado.entradas[0]
    assert entrada.ventas == tuple(Decimal(v) for v in (1, 2, 3, 4, 5, 6))
    assert entrada.perdidas == tuple(Decimal(v) for v in (0, 0, 0, 0, 2, 7))


async def test_a_month_without_movements_is_zero_not_none():
    resultado, _ = await _cargar(
        [_serie(REF_A, (None, None, 4, None, None, None))],
        referencias=[_attr(REF_A, "A-1")])

    entrada = resultado.entradas[0]
    assert entrada.ventas == tuple(Decimal(v) for v in (0, 0, 4, 0, 0, 0))
    assert entrada.perdidas == (Decimal(0),) * 6


async def test_lost_demand_alone_does_not_bring_a_reference_in():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        perdidas=[_serie(REF_A, (0,) * 6), _serie(REF_B, (0, 0, 0, 0, 0, 8))],
        referencias=[_attr(REF_A, "A-1")])

    assert [e.codigo for e in resultado.entradas] == ["A-1"]


# --- Mes en curso ---------------------------------------------------------


async def test_m0_columns_are_loaded_only_when_ponderado_is_effective():
    resultado, db = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0), m0=7)],
        perdidas=[_serie(REF_A, (0,) * 6, m0=2)],
        referencias=[_attr(REF_A, "A-1")], mes_en_curso=PONDERADO)

    entrada = resultado.entradas[0]
    assert (entrada.venta_m0, entrada.perdida_m0) == (Decimal(7), Decimal(2))
    assert "AS c0" in _sql(db.executed_statements[0])
    assert "(2026, 9)" in _sql(db.executed_statements[0])
    assert "AS c0" in _sql(db.executed_statements[1])


async def test_m0_without_rows_is_zero_when_effective():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0), m0=None)],
        referencias=[_attr(REF_A, "A-1")], mes_en_curso=PONDERADO)

    entrada = resultado.entradas[0]
    assert (entrada.venta_m0, entrada.perdida_m0) == (Decimal(0), Decimal(0))


async def test_m0_is_none_and_never_queried_when_excluido():
    resultado, db = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        referencias=[_attr(REF_A, "A-1")])

    entrada = resultado.entradas[0]
    assert (entrada.venta_m0, entrada.perdida_m0) == (None, None)
    ventas_sql = _sql(db.executed_statements[0])
    assert "AS c0" not in ventas_sql and "AS c0" not in _sql(
        db.executed_statements[1])
    assert "(2026, 9)" not in ventas_sql


async def test_lost_demand_of_m0_is_bounded_by_the_corte_only_when_effective():
    _, con_m0 = await _cargar(mes_en_curso=PONDERADO)
    _, sin_m0 = await _cargar()

    con = _sql(con_m0.executed_statements[1])
    sin = _sql(sin_m0.executed_statements[1])
    assert "<= '2026-09-21'" in con
    assert "<= '2026-09-21'" not in sin
    assert ">= '2026-03-01'" in con and ">= '2026-03-01'" in sin
    assert "< '2026-09-01'" in sin


# --- V / W / X ------------------------------------------------------------


async def test_v_w_and_x_come_by_sucursal_and_sic():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        inventario=[_total(REF_A, "27")], backorder=[_total(REF_A, "6")],
        referencias=[_attr(REF_A, "A-1")],
        transito={SUC: {REF_A: Decimal(70)}, OTRA_SUC: {REF_A: Decimal(8)}})

    entrada = resultado.entradas[0]
    assert (entrada.inventario, entrada.transito, entrada.backorder) == (
        Decimal(27), Decimal(70), Decimal(6))


async def test_a_reference_without_stock_has_zero_v_w_and_x():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        inventario=[_total(REF_B, "9")],
        referencias=[_attr(REF_A, "A-1")],
        transito={SUC: {REF_B: Decimal(3)}})

    entrada = resultado.entradas[0]
    assert (entrada.inventario, entrada.transito, entrada.backorder) == (
        Decimal(0), Decimal(0), Decimal(0))


async def test_t13_inventory_is_the_consolidated_snapshot_at_the_cut():
    _, db = await _cargar()

    inventario = _sql(db.executed_statements[2])
    backorder = _sql(db.executed_statements[3])
    assert "fecha_corte = '2026-09-19'" in inventario
    assert "fecha_corte = '2026-09-18'" in backorder
    for consulta in (inventario, backorder):
        assert str(SUC) in consulta
        assert "bodega" not in consulta


async def test_the_queries_only_read_the_principal_supplier_references():
    _, db = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        referencias=[_attr(REF_A, "A-1")])

    for posicion in range(5):
        consulta = _sql(db.executed_statements[posicion])
        assert str(PROVEEDOR.id) in consulta


# --- Origen, cargas anuladas y forma del SQL ------------------------------


async def test_sales_sum_mostrador_and_taller_in_one_pivot_query():
    _, db = await _cargar()

    consulta = _sql(db.executed_statements[0])
    assert "sum(venta_mensual.unidades) FILTER (WHERE" in consulta
    assert "'MOSTRADOR'" in consulta and "'TALLER'" in consulta
    assert "GROUP BY venta_mensual.referencia_id" in consulta


async def test_annulled_excel_cargas_are_dropped_from_every_source():
    _, db = await _cargar()

    for posicion in (0, 2, 3):
        consulta = _sql(db.executed_statements[posicion])
        assert "carga_archivo.estado != 'ANULADO'" in consulta


async def test_bot_lost_demand_rows_are_exempt_from_the_annulled_filter():
    _, db = await _cargar()

    consulta = _sql(db.executed_statements[1])
    assert ("demanda_perdida.origen = 'BOT' OR "
            "carga_archivo.estado != 'ANULADO'") in consulta


async def test_the_query_count_does_not_grow_with_the_number_of_references():
    pocas, db_pocas = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        referencias=[_attr(REF_A, "A-1")])
    ids = [uuid.uuid4() for _ in range(300)]
    muchas, db_muchas = await _cargar(
        [_serie(i, (5, 0, 0, 0, 0, 0)) for i in ids],
        inventario=[_total(i, "1") for i in ids],
        referencias=[_attr(i, f"R-{n}") for n, i in enumerate(ids)])

    assert len(pocas.entradas) == 1 and len(muchas.entradas) == 300
    assert len(db_pocas.executed_statements) == 5
    assert len(db_muchas.executed_statements) == 5


async def test_no_attribute_query_runs_when_the_universe_is_empty():
    resultado, db = await _cargar()

    assert resultado.entradas == ()
    assert len(db.executed_statements) == 4


# --- Atributos de la referencia ---------------------------------------------


async def test_reference_attributes_and_unit_come_from_the_master():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        referencias=[_attr(REF_A, "A-1", precio="460.75", unidad=12)])

    entrada = resultado.entradas[0]
    assert entrada.referencia_id == REF_A
    assert (entrada.codigo, entrada.nombre) == ("A-1", "Repuesto A-1")
    assert entrada.linea_comercial == "MOTOR"
    assert (entrada.precio, entrada.unidad_empaque) == (
        Decimal("460.75"), 12)
    assert entrada.ajuste == Decimal(0)
    assert entrada.banderas == frozenset()


async def test_a_reference_without_price_is_flagged_and_warned():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0)), _serie(REF_B, (2,) * 6)],
        referencias=[_attr(REF_A, "A-1", precio=None),
                     _attr(REF_B, "B-1")])

    entradas = _por_codigo(resultado)
    assert entradas["A-1"].precio is None
    assert entradas["A-1"].banderas == frozenset({cg.BANDERA_SIN_PRECIO})
    assert entradas["B-1"].banderas == frozenset()
    assert [(a.codigo, a.mensaje) for a in resultado.advertencias] == [
        (codigos.A_CORRIDA_SIN_PRECIO,
         codigos.mensaje(codigos.A_CORRIDA_SIN_PRECIO, referencia="A-1"))]


async def test_a_corrected_packaging_unit_is_flagged():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        referencias=[_attr(REF_A, "A-1", corregido=True)])

    assert resultado.entradas[0].banderas == frozenset(
        {cg.BANDERA_EMPAQUE_CORREGIDO})


async def test_entries_come_sorted_by_code_whatever_the_row_order():
    resultado, _ = await _cargar(
        [_serie(REF_B, (2,) * 6), _serie(REF_A, (1,) * 6)],
        referencias=[_attr(REF_B, "B-1"), _attr(REF_A, "A-1")])

    assert [e.codigo for e in resultado.entradas] == ["A-1", "B-1"]


# --- Consolidación de sustituidas (contrato con S3) --------------------------


def _maestro():
    return {
        REF_A: NodoMaestro(REF_A, False, REF_B),
        REF_C: NodoMaestro(REF_C, False, None),
    }


def _consolidacion(**cambios):
    maestro = _maestro()
    base = dict(consolidar=True, resoluciones=resolver_cadenas(maestro))
    return {**base, **cambios}


async def test_with_consolidation_off_old_references_are_not_loaded():
    resultado, db = await _cargar(
        [_serie(REF_D, (4,) * 6)], inventario=[_total(REF_A, "30")],
        referencias=[_attr(REF_D, "D-1")],
        consolidar=False, resoluciones=resolver_cadenas(_maestro()))

    assert [e.codigo for e in resultado.entradas] == ["D-1"]
    consulta = _sql(db.executed_statements[4])
    assert str(REF_A) not in consulta and str(REF_B) not in consulta


async def test_with_consolidation_on_old_refs_with_data_and_finals_load():
    resultado, db = await _cargar(
        [_serie(REF_D, (4,) * 6)],
        inventario=[_total(REF_A, "30"), _total(REF_C, "5")],
        referencias=[_attr(REF_D, "D-1"), _attr(REF_A, "A-1"),
                     _attr(REF_B, "B-1"), _attr(REF_C, "C-1")],
        **_consolidacion())

    consulta = _sql(db.executed_statements[4])
    for ref in (REF_A, REF_B, REF_C, REF_D):
        assert str(ref) in consulta
    assert sorted(_por_codigo(resultado)) == [
        "A-1", "B-1", "C-1", "D-1"]
    final = _por_codigo(resultado)["B-1"]
    assert (final.ventas, final.inventario) == (
        (Decimal(0),) * 6, Decimal(0))


async def test_the_price_warning_covers_only_the_sales_universe():
    resultado, _ = await _cargar(
        [_serie(REF_D, (4,) * 6)], inventario=[_total(REF_A, "30")],
        referencias=[_attr(REF_D, "D-1"), _attr(REF_A, "A-1", precio=None),
                     _attr(REF_B, "B-1")],
        **_consolidacion())

    por_codigo = _por_codigo(resultado)
    assert por_codigo["A-1"].banderas == frozenset({cg.BANDERA_SIN_PRECIO})
    assert resultado.advertencias == ()


async def test_an_old_reference_without_any_data_brings_nothing_in():
    resultado, db = await _cargar(
        [_serie(REF_D, (4,) * 6)], referencias=[_attr(REF_D, "D-1")],
        **_consolidacion())

    consulta = _sql(db.executed_statements[4])
    assert str(REF_A) not in consulta and str(REF_B) not in consulta
    assert [e.codigo for e in resultado.entradas] == ["D-1"]


@pytest.mark.parametrize("dato", ["ventas_m0", "perdida", "transito"])
async def test_any_kind_of_data_makes_an_old_reference_load(dato):
    ventas = [_serie(REF_D, (4,) * 6)]
    perdidas, transito, cambios = [], {}, {}
    if dato == "ventas_m0":
        ventas.append(_serie(REF_A, (0,) * 6, m0=3))
        cambios["mes_en_curso"] = PONDERADO
    elif dato == "perdida":
        perdidas = [_serie(REF_A, (0, 0, 0, 0, 0, 2))]
    else:
        transito = {SUC: {REF_A: Decimal(6)}}

    resultado, _ = await _cargar(
        ventas, perdidas=perdidas,
        referencias=[_attr(REF_D, "D-1"), _attr(REF_A, "A-1"),
                     _attr(REF_B, "B-1")],
        transito=transito, **cambios, **_consolidacion())

    assert "A-1" in _por_codigo(resultado)
    assert "B-1" in _por_codigo(resultado)


async def test_a_final_that_is_not_a_valid_principal_reference_is_skipped():
    resultado, _ = await _cargar(
        [_serie(REF_D, (4,) * 6)], inventario=[_total(REF_A, "30")],
        referencias=[_attr(REF_D, "D-1"), _attr(REF_A, "A-1")],
        **_consolidacion())

    assert sorted(_por_codigo(resultado)) == ["A-1", "D-1"]


async def test_loaded_entries_feed_the_engine_and_the_stock_nets_out():
    """A vendió y tiene stock; B (su sustituta) no tiene nada: el motor
    pone a B en el pedido y le resta el stock de A."""
    resultado, _ = await _cargar(
        [_serie(REF_A, (12, 12, 12, 12, 12, 12))],
        inventario=[_total(REF_A, "30")],
        referencias=[_attr(REF_A, "A-1"), _attr(REF_B, "B-1")],
        **_consolidacion())
    resoluciones = resolver_cadenas(_maestro())

    calculo = calcular_sucursal(
        resultado.entradas, atributos(fecha_corte=CORTE),
        ParametrosMotor(consolidar_sustituidas=True), resoluciones)

    assert [linea.entrada.codigo for linea in calculo.lineas] == ["B-1"]
    linea = calculo.lineas[0]
    assert linea.inventario_efectivo == 30
    assert [(x.entrada.codigo, x.motivo, x.sustituta_final_codigo)
            for x in calculo.excluidas] == [("A-1", "SUSTITUIDA", "B-1")]


# --- Atributos de la sucursal ---------------------------------------------


def _sucursal(**cambios):
    base = dict(
        id=SUC, nombre="MANIZALES AV SANTANDER", sic="SIC-01",
        fecha_apertura=datetime.date(2024, 1, 15), dias_empaque=3,
        dias_transito=2, dias_seguridad=Decimal("2.5"))
    return cg.FilaSucursal(**{**base, **cambios})


def _atributos(sucursal=None, proveedor=PROVEEDOR, dias=30):
    return cg.resolver_atributos(
        sucursal or _sucursal(), proveedor, CORTE, dias)


def test_the_sucursal_own_values_win_over_the_supplier_defaults():
    resultado = _atributos()

    assert resultado.sucursal_id == SUC
    assert resultado.fecha_corte == CORTE
    assert resultado.fecha_apertura == datetime.date(2024, 1, 15)
    assert (resultado.dias_empaque, resultado.dias_transito) == (
        Decimal(3), Decimal(2))
    assert resultado.dias_seguridad == Decimal("2.5")
    assert resultado.dias_entre_pedidos == Decimal(30)


def test_missing_sucursal_days_fall_back_to_the_supplier_defaults():
    resultado = _atributos(_sucursal(
        dias_empaque=None, dias_transito=None, dias_seguridad=None))

    assert (resultado.dias_empaque, resultado.dias_transito) == (
        Decimal(4), Decimal(5))
    assert resultado.dias_seguridad == Decimal(3)


def test_safety_days_default_to_2_5_when_nobody_defines_them():
    proveedor = cg.FilaProveedor(PROVEEDOR.id, 4, 5, None)

    resultado = _atributos(_sucursal(dias_seguridad=None), proveedor)

    assert resultado.dias_seguridad == Decimal("2.5")


def test_only_one_missing_lead_time_counts_as_zero():
    proveedor = cg.FilaProveedor(PROVEEDOR.id, None, None, None)

    resultado = _atributos(_sucursal(dias_transito=None), proveedor)

    assert (resultado.dias_empaque, resultado.dias_transito) == (
        Decimal(3), Decimal(0))


def test_both_lead_times_missing_is_e_corrida_020():
    proveedor = cg.FilaProveedor(PROVEEDOR.id, None, None, None)

    with pytest.raises(cg.ErrorCargador) as error:
        _atributos(
            _sucursal(dias_empaque=None, dias_transito=None), proveedor)

    assert error.value.codigo == codigos.E_CORRIDA_SIN_EMPAQUE_NI_TRANSITO
    assert "MANIZALES AV SANTANDER" in error.value.mensaje


@pytest.mark.parametrize("sic", [None, "", "   "])
def test_a_sucursal_without_sic_is_e_corrida_021(sic):
    with pytest.raises(cg.ErrorCargador) as error:
        _atributos(_sucursal(sic=sic))

    assert error.value.codigo == codigos.E_CORRIDA_SUCURSAL_SIN_SIC
    assert "MANIZALES AV SANTANDER" in error.value.mensaje


def test_t14_trailing_spaces_in_the_sucursal_name_are_trimmed():
    resultado = _atributos(_sucursal(nombre="  MANIZALES AV SANTANDER   "))

    assert resultado.nombre == "MANIZALES AV SANTANDER"


def test_dias_entre_pedidos_is_the_value_given_for_the_sucursal():
    assert _atributos(dias=7).dias_entre_pedidos == Decimal(7)


# --- Lecturas por corrida ---------------------------------------------------


async def test_the_principal_supplier_is_read_with_its_defaults():
    fila = SimpleNamespace(
        id=PROVEEDOR.id, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    db = FakeAsyncSession(execute_queue=[[fila]])

    proveedor = await cg.cargar_proveedor_principal(db)

    assert proveedor == PROVEEDOR
    assert "es_principal" in _sql(db.executed_statements[0])


@pytest.mark.parametrize("filas", [0, 2])
async def test_exactly_one_principal_supplier_is_required(filas):
    fila = SimpleNamespace(
        id=uuid.uuid4(), dias_empaque_default=None,
        dias_transito_default=None, dias_seguridad_default=None)
    db = FakeAsyncSession(execute_queue=[[fila] * filas])

    with pytest.raises(LookupError):
        await cg.cargar_proveedor_principal(db)


async def test_the_master_holds_inactive_and_substituted_references_only():
    filas = [
        SimpleNamespace(id=REF_A, activa=False, sustituida_por=REF_B),
        SimpleNamespace(id=REF_C, activa=True, sustituida_por=REF_D),
    ]
    db = FakeAsyncSession(execute_queue=[filas])

    maestro = await cg.cargar_maestro(db, PROVEEDOR.id)

    assert maestro == {
        REF_A: NodoMaestro(REF_A, False, REF_B),
        REF_C: NodoMaestro(REF_C, True, REF_D),
    }
    consulta = _sql(db.executed_statements[0])
    assert str(PROVEEDOR.id) in consulta
    assert "sustituida_por IS NOT NULL" in consulta
    assert "activa IS false" in consulta


async def test_the_sucursal_row_is_read_and_a_missing_one_is_an_error():
    fila = SimpleNamespace(
        id=SUC, nombre="X", sic="S", fecha_apertura=None, dias_empaque=1,
        dias_transito=1, dias_seguridad=Decimal("2.5"))

    encontrada = await cg.cargar_sucursal_fila(
        FakeAsyncSession(execute_queue=[[fila]]), SUC)

    assert (encontrada.id, encontrada.nombre) == (SUC, "X")
    with pytest.raises(LookupError):
        await cg.cargar_sucursal_fila(
            FakeAsyncSession(execute_queue=[[]]), SUC)


async def test_cargar_sucursal_reads_the_row_then_the_five_queries():
    fila = SimpleNamespace(
        id=SUC, nombre="MANIZALES ", sic="S", fecha_apertura=None,
        dias_empaque=3, dias_transito=2, dias_seguridad=Decimal("2.5"))
    db = FakeAsyncSession(execute_queue=[
        [fila], [_serie(REF_A, (5, 0, 0, 0, 0, 0))], [], [], [],
        [_attr(REF_A, "A-1")]])

    datos = await cg.cargar_sucursal(
        db, SUC, _contexto(dias_entre_pedidos={SUC: 7}))

    assert len(db.executed_statements) == 6
    assert datos.atributos.nombre == "MANIZALES"
    assert datos.atributos.dias_entre_pedidos == Decimal(7)
    assert [e.codigo for e in datos.entradas] == ["A-1"]


async def test_a_sucursal_error_is_raised_before_any_movement_query():
    fila = SimpleNamespace(
        id=SUC, nombre="X", sic=None, fecha_apertura=None, dias_empaque=3,
        dias_transito=2, dias_seguridad=Decimal("2.5"))
    db = FakeAsyncSession(execute_queue=[[fila]])

    with pytest.raises(cg.ErrorCargador):
        await cg.cargar_sucursal(
            db, SUC, _contexto(dias_entre_pedidos={SUC: 30}))

    assert len(db.executed_statements) == 1


# --- Contexto de la corrida -------------------------------------------


def _vigencia(mes_en_curso=None):
    return ResultadoVigencia(
        antiguedad={}, mes_en_curso=ResolucionMesEnCurso(mes_en_curso),
        seleccion_datos={"cortes": {
            "inventario": "2026-09-19", "backorder": "2026-09-18"}},
        advertencias=(), cargas_usadas={})


def _parametros(consolidar=False, dias=None):
    return ParametrosCorrida(
        motor=ParametrosMotor(consolidar_sustituidas=consolidar),
        dias_entre_pedidos=dias or {}, limites_antiguedad={},
        modo_mes_en_curso="EXCLUIDO", tope_mes_en_curso=Fraction(3),
        min_dias_mes_en_curso=5, excluir_transito_vencido=False,
        snapshot={})


def _construir(consolidar=False, mes_en_curso=None, w=None, dias=None):
    return cg.construir_contexto(
        PROVEEDOR, CORTE, _vigencia(mes_en_curso),
        TransitoAlCorte(w=w or {}, vencidas=()),
        _parametros(consolidar, dias), _maestro())


def test_the_context_takes_the_cortes_and_the_effective_m0_of_the_preflight():
    contexto = _construir(mes_en_curso=PONDERADO)

    assert contexto.proveedor == PROVEEDOR and contexto.fecha_corte == CORTE
    assert contexto.corte_inventario == CORTE_INVENTARIO
    assert contexto.corte_backorder == CORTE_BACKORDER
    assert contexto.mes_en_curso == PONDERADO
    assert _construir().mes_en_curso is None


def test_the_context_indexes_w_by_sucursal_and_keeps_the_days_per_sucursal():
    contexto = _construir(
        w={(SUC, REF_A): Decimal(5), (OTRA_SUC, REF_A): Decimal(3),
           (SUC, REF_B): Decimal(1)},
        dias={SUC: 7, OTRA_SUC: 30})

    assert contexto.transito == {
        SUC: {REF_A: Decimal(5), REF_B: Decimal(1)},
        OTRA_SUC: {REF_A: Decimal(3)}}
    assert contexto.dias_entre_pedidos == {SUC: 7, OTRA_SUC: 30}


def test_the_context_resolves_the_chains_only_with_consolidation_on():
    apagado = _construir(consolidar=False)
    encendido = _construir(consolidar=True)

    assert apagado.consolidar is False and apagado.resoluciones == {}
    assert encendido.consolidar is True
    assert encendido.resoluciones == resolver_cadenas(_maestro())
    assert encendido.resoluciones[REF_A].final_id == REF_B


# --- Grupo de la tienda principal (sucursales asociadas) -----------------


ASOCIADA = uuid.uuid4()


async def test_the_group_reads_every_source_for_the_principal_and_members():
    _, db = await _cargar(grupos={SUC: (ASOCIADA,)})

    for posicion in range(4):
        consulta = _sql(db.executed_statements[posicion])
        assert str(SUC) in consulta and str(ASOCIADA) in consulta
        assert str(OTRA_SUC) not in consulta
        assert "activa" not in consulta


async def test_the_group_rows_sum_by_reference_and_merge_the_transit():
    resultado, db = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 4))],
        perdidas=[_serie(REF_A, (1, 0, 0, 0, 0, 2))],
        inventario=[_total(REF_A, "27"), _total(REF_A, "3")],
        backorder=[_total(REF_A, "6"), _total(REF_A, "1")],
        referencias=[_attr(REF_A, "A-1")],
        transito={SUC: {REF_A: Decimal(70)},
                  ASOCIADA: {REF_A: Decimal(8), REF_B: Decimal(2)},
                  OTRA_SUC: {REF_A: Decimal(100)}},
        grupos={SUC: (ASOCIADA,)})

    entrada = resultado.entradas[0]
    assert entrada.ventas[-1] == Decimal(4) and entrada.perdidas[0] == 1
    assert (entrada.inventario, entrada.transito, entrada.backorder) == (
        Decimal(30), Decimal(78), Decimal(7))
    for posicion in (0, 1, 2, 3):
        assert "GROUP BY" in _sql(db.executed_statements[posicion])


async def test_a_member_transit_counts_for_a_reference_of_the_principal():
    resultado, _ = await _cargar(
        [_serie(REF_A, (5, 0, 0, 0, 0, 0))],
        referencias=[_attr(REF_A, "A-1")],
        transito={ASOCIADA: {REF_A: Decimal(9)}},
        grupos={SUC: (ASOCIADA,)})

    assert resultado.entradas[0].transito == Decimal(9)


async def test_without_a_frozen_group_the_store_reads_only_itself():
    _, db = await _cargar(transito={ASOCIADA: {REF_A: Decimal(9)}})

    for posicion in range(4):
        assert str(ASOCIADA) not in _sql(db.executed_statements[posicion])
    assert cg.ContextoCarga(
        proveedor=PROVEEDOR, fecha_corte=CORTE,
        corte_inventario=CORTE_INVENTARIO,
        corte_backorder=CORTE_BACKORDER).miembros(SUC) == (SUC,)


async def test_the_group_uses_the_principal_row_and_its_own_attributes():
    fila = SimpleNamespace(
        id=SUC, nombre="PRINCIPAL", sic="S", fecha_apertura=None,
        dias_empaque=3, dias_transito=2, dias_seguridad=Decimal("2.5"))
    db = FakeAsyncSession(execute_queue=[
        [fila], [_serie(REF_A, (5, 0, 0, 0, 0, 0))], [], [], [],
        [_attr(REF_A, "A-1")]])

    datos = await cg.cargar_sucursal(db, SUC, _contexto(
        dias_entre_pedidos={SUC: 7, ASOCIADA: 30},
        grupos={SUC: (ASOCIADA,)}))

    assert str(ASOCIADA) not in _sql(db.executed_statements[0])
    assert datos.atributos.sucursal_id == SUC
    assert datos.atributos.nombre == "PRINCIPAL"
    assert datos.atributos.dias_entre_pedidos == Decimal(7)


def test_the_frozen_groups_are_read_back_from_the_seleccion():
    seleccion = {"grupos": {str(SUC): [str(ASOCIADA)]}}

    assert cg.grupos_desde_seleccion(seleccion) == {SUC: (ASOCIADA,)}
    assert cg.grupos_desde_seleccion({}) == {}
    assert cg.grupos_desde_seleccion({"grupos": None}) == {}
