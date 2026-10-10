"""
Pure checks of the 12-month window of the monthly KPI charts (odd/motored-kpis-ventana-12-meses): the window
always ends at the last month with sales, never exceeds 12 months, never starts before the first month with
data, and keeps the filter's stores, HMCL mode and rules.
"""
from app.motored.services import tablero_asesores as t


def _meses(primero, cuantos):
    return [t.mes_desplazado(primero, i) for i in range(cuantos)]


def test_the_window_has_at_most_twelve_months_ending_at_the_last_one():
    disponibles = _meses("2025-01", 22)  # 2025-01 .. 2026-10

    ventana = t.meses_de_ventana(disponibles)

    assert len(ventana) == 12
    assert ventana[0] == "2025-11"
    assert ventana[-1] == "2026-10"


def test_the_window_starts_at_the_first_month_with_data_when_there_are_fewer_than_twelve():
    ventana = t.meses_de_ventana(_meses("2026-01", 10))

    assert ventana == _meses("2026-01", 10)  # never padded with empty months before the history


def test_the_window_is_empty_without_sales():
    assert t.meses_de_ventana([]) == []


def test_the_window_filter_keeps_stores_hmcl_and_rules_of_the_period_filter():
    periodo = t.filtro_de_meses(["2026-09"], t.HMCL_SOLO, ["s1"], t.REGLAS_POR_DEFECTO)

    ventana = t.filtro_con_meses(periodo, _meses("2026-01", 10))

    assert ventana.meses == tuple(_meses("2026-01", 10))
    assert ventana.modo_hmcl == t.HMCL_SOLO
    assert ventana.sucursal_ids == frozenset(["s1"])
    assert ventana.reglas is periodo.reglas
    assert len(ventana.rangos) == 1
