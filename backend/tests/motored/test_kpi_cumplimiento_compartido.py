"""
Pure checks of the shared work of the cumplimiento (odd/motored-kpis-velocidad, S4): the sales of a cube are
computed once for the period and every month, and the rollup rows of the Tecnired counts split into the
total and the months.
"""
from decimal import Decimal

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_kpis as k
from app.motored.services import tablero_kpis_consultas as qk
from app.motored.services.presupuestos import LineaPresupuesto

REGLAS = t.REGLAS_POR_DEFECTO


def _fila(clave, mes, linea, venta, hmcl=False):
    return t.FilaCubo(clave, mes, linea, hmcl, False, True, True, Decimal(venta), Decimal(venta), Decimal(0),
                      Decimal(1), 1, Decimal(0), Decimal(0))


def _mundo():
    cubo = [
        _fila("P:ANA", "2097-01", "REPUESTOS", 100), _fila("P:ANA", "2097-02", "REPUESTOS", 50, hmcl=True),
        _fila("P:ANA", "2097-02", "LLANTAS", 70), _fila("P:LUIS", "2097-02", "REPUESTOS", 30),
        _fila("P:SIN", "2097-01", "REPUESTOS", 10), _fila(t.GRUPO_RESTO, "2097-01", "REPUESTOS", 500),
    ]
    presupuestos = {
        ("2097-01", "1000"): LineaPresupuesto("s1", 200), ("2097-02", "1000"): LineaPresupuesto("s1", 100),
        ("2097-02", "2000"): LineaPresupuesto("s2", 80),
    }
    return cubo, presupuestos


def test_cumplimiento_por_mes_equals_one_cumplimiento_per_month():
    cubo, presupuestos = _mundo()
    meses = ["2097-01", "2097-02"]

    compartido = k.cumplimiento_por_mes(cubo, presupuestos, REGLAS, meses)

    por_separado = {
        mes: k.construir_cumplimiento(
            cubo, {clave: linea for clave, linea in presupuestos.items() if clave[0] == mes}, REGLAS)
        for mes in meses
    }
    assert compartido == por_separado


def test_a_precomputed_venta_gives_the_same_cumplimiento():
    cubo, presupuestos = _mundo()

    con_venta = k.construir_cumplimiento(cubo, presupuestos, REGLAS, venta=k.venta_para_cumplimiento(cubo, REGLAS))

    assert con_venta == k.construir_cumplimiento(cubo, presupuestos, REGLAS)


def test_the_rollup_rows_split_into_the_total_and_the_months():
    assert qk._total_y_por_mes([("2097-01", 2), ("2097-02", 3), (None, 4)]) == (4, {"2097-01": 2, "2097-02": 3})
    assert qk._total_y_por_mes([(None, 0)]) == (0, {})
    assert qk._total_y_por_mes([]) == (0, {})
