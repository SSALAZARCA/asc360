"""
Motored Pedidos F3 "Motor", S5a (sdd/motored-pedidos-motor, ADR-6): tránsito
(W) recalculado AL CORTE, sin leer las banderas mutables de F2.

Escenarios T09, T10, T11, [OFF-ID] tránsito vencido y "mismo corte en dos
fechas de ejecución -> mismo W".
"""
import datetime
import uuid
from decimal import Decimal

import pytest

from app.motored.services.corridas import transito_corte as tc
from app.motored.services.corridas.transito_corte import (
    IngresoDocumento, LineaFactura)
from tests.motored.conftest import FakeAsyncSession

CORTE = datetime.date(2026, 9, 21)
SUC_A, SUC_B = uuid.uuid4(), uuid.uuid4()
REF_1, REF_2 = uuid.uuid4(), uuid.uuid4()
VENTANA = 45
TOLERANCIA = 5.0


def _linea(numero, dias_antes, cantidad, sucursal=SUC_A, ref=REF_1,
           valor=None, prefijo="RH"):
    return LineaFactura(
        prefijo_rh=prefijo, numero_rh=numero,
        fecha_factura=CORTE - datetime.timedelta(days=dias_antes),
        sucursal_id=sucursal, referencia_id=ref,
        cantidad=Decimal(cantidad),
        valor_total=Decimal(cantidad if valor is None else valor),
    )


def _ingreso(numero, dias_antes, valor, prefijo="RH"):
    return IngresoDocumento(
        prefijo_rh=prefijo, numero_rh=numero,
        fecha_ingreso=CORTE - datetime.timedelta(days=dias_antes),
        valor_neto=Decimal(valor),
    )


def _calcular(facturas, ingresos=(), excluir=False):
    return tc.calcular_transito_corte(
        facturas, ingresos, CORTE, excluir_vencido=excluir,
        dias_ventana_ingresos=VENTANA, tolerancia_ingreso_pct=TOLERANCIA,
    )


def test_t09_a_20_day_invoice_without_ingreso_is_in_w():
    resultado = _calcular([_linea(1, 20, 12)])

    assert resultado.w == {(SUC_A, REF_1): Decimal(12)}
    assert resultado.vencidas == ()


def test_off_id_a_60_day_invoice_stays_in_w_with_the_toggle_off():
    resultado = _calcular([_linea(1, 60, 30)], excluir=False)

    assert resultado.w == {(SUC_A, REF_1): Decimal(30)}
    assert resultado.vencidas == ()


def test_t10_toggle_on_excludes_the_vencido_invoice_and_lists_it():
    facturas = [_linea(1, 60, 30), _linea(2, 20, 12)]

    resultado = _calcular(facturas, excluir=True)

    assert resultado.w == {(SUC_A, REF_1): Decimal(12)}
    assert len(resultado.vencidas) == 1
    vencida = resultado.vencidas[0]
    assert (vencida.numero_rh, vencida.cantidad) == (1, Decimal(30))
    assert vencida.sucursal_id == SUC_A and vencida.referencia_id == REF_1


def test_t10_a_vencido_invoice_with_an_ingreso_is_not_listed():
    resultado = _calcular(
        [_linea(1, 60, 30, valor=100)], [_ingreso(1, 10, 100)],
        excluir=True)

    assert resultado.vencidas == ()
    assert resultado.w == {}


def test_t11_a_credit_note_line_reduces_w():
    facturas = [_linea(1, 10, 10), _linea(2, 5, -3)]

    resultado = _calcular(facturas)

    assert resultado.w == {(SUC_A, REF_1): Decimal(7)}


def test_w_sums_documents_per_sucursal_and_reference():
    facturas = [
        _linea(1, 10, 5), _linea(2, 8, 6),
        _linea(3, 8, 4, ref=REF_2), _linea(4, 8, 9, sucursal=SUC_B),
    ]

    resultado = _calcular(facturas)

    assert resultado.w == {
        (SUC_A, REF_1): Decimal(11), (SUC_A, REF_2): Decimal(4),
        (SUC_B, REF_1): Decimal(9),
    }


def test_an_ingresada_document_leaves_transit_at_document_level():
    facturas = [_linea(1, 10, 5), _linea(1, 10, 7, ref=REF_2),
                _linea(2, 10, 3)]

    resultado = _calcular(facturas, [_ingreso(1, 3, 12)])

    assert resultado.w == {(SUC_A, REF_1): Decimal(3)}


def test_an_ingreso_dated_after_the_corte_leaves_the_invoice_in_transit():
    resultado = _calcular([_linea(1, 10, 5)], [_ingreso(1, -2, 5)])

    assert resultado.w == {(SUC_A, REF_1): Decimal(5)}


def test_an_ingreso_dated_on_the_corte_counts():
    resultado = _calcular([_linea(1, 10, 5)], [_ingreso(1, 0, 5)])

    assert resultado.w == {}


def test_an_invoice_dated_after_the_corte_is_excluded():
    resultado = _calcular([_linea(1, -1, 8), _linea(2, 0, 4)])

    assert resultado.w == {(SUC_A, REF_1): Decimal(4)}


def test_other_prefix_ingresos_never_match_an_rh_invoice():
    resultado = _calcular(
        [_linea(1, 10, 5)], [_ingreso(1, 3, 5, prefijo="FE")])

    assert resultado.w == {(SUC_A, REF_1): Decimal(5)}


def test_the_same_corte_gives_identical_w_regardless_of_run_date():
    facturas = [_linea(1, 60, 30), _linea(2, 20, 12)]
    ingresos = [_ingreso(2, -4, 12)]

    primera = _calcular(facturas, ingresos, excluir=True)
    segunda = _calcular(facturas, ingresos, excluir=True)

    assert primera == segunda
    assert primera.w == {(SUC_A, REF_1): Decimal(12)}
    assert len(primera.vencidas) == 1


# --- Lectura -----------------------------------------------------------------


class _Fila:
    def __init__(self, **campos):
        self.__dict__.update(campos)


async def _cargar(facturas, ingresos, **kw):
    db = FakeAsyncSession(execute_queue=[facturas, ingresos])
    resultado = await tc.cargar_transito_corte(
        db, CORTE, excluir_vencido=kw.get("excluir", False),
        dias_ventana_ingresos=VENTANA, tolerancia_ingreso_pct=TOLERANCIA,
    )
    return resultado, db


async def test_the_loader_assembles_w_from_rows():
    fila = _Fila(
        prefijo_rh="RH", numero_rh=7,
        fecha_factura=CORTE - datetime.timedelta(days=20),
        sucursal_id=SUC_A, referencia_id=REF_1,
        cantidad=Decimal("12"), valor_total=Decimal("100"),
    )
    ingreso = _Fila(
        prefijo_rh="RH", numero_rh=8,
        fecha_ingreso=CORTE, valor_neto=Decimal("50"),
    )

    resultado, db = await _cargar([fila], [ingreso])

    assert resultado.w == {(SUC_A, REF_1): Decimal(12)}
    assert len(db.executed_statements) == 2


async def test_the_loader_never_selects_the_mutable_f2_flags():
    _, db = await _cargar([], [])

    sql = " ".join(str(s) for s in db.executed_statements).lower()
    assert "ingresada" not in sql
    assert "transito_vencido" not in sql
    assert "ingreso_parcial_sospechoso" not in sql


async def test_the_loader_filters_annulled_cargas_and_dates_at_the_corte():
    _, db = await _cargar([], [])

    facturas_sql = str(db.executed_statements[0]).lower()
    ingresos_sql = str(db.executed_statements[1]).lower()
    assert "carga_archivo" in facturas_sql
    assert "carga_archivo" in ingresos_sql
    assert "fecha_factura <=" in facturas_sql
    assert "fecha_ingreso <=" in ingresos_sql


async def test_the_loader_returns_an_empty_transit_without_rows():
    resultado, _ = await _cargar([], [])

    assert resultado.w == {}
    assert resultado.vencidas == ()
    assert isinstance(resultado, tc.TransitoAlCorte)


@pytest.mark.parametrize("excluir, esperado", [
    (False, Decimal(30)), (True, None),
])
async def test_the_loader_honors_the_toggle(excluir, esperado):
    fila = _Fila(
        prefijo_rh="RH", numero_rh=1,
        fecha_factura=CORTE - datetime.timedelta(days=60),
        sucursal_id=SUC_A, referencia_id=REF_1,
        cantidad=Decimal("30"), valor_total=Decimal("30"),
    )

    resultado, _ = await _cargar([fila], [], excluir=excluir)

    assert resultado.w.get((SUC_A, REF_1)) == esperado
