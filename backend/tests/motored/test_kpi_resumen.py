"""KPI summary service (R2): pure helpers. The SQL is covered in `pg_real/test_kpi_resumen_pg.py`."""
from app.motored.services import kpi_resumen as k


def test_union_lineas_keeps_the_default_and_every_historical_value_normalized():
    result = k.union_lineas([["Motos", " baterías "], "not a list", [], ["REPUESTOS", 7]])

    assert result == tuple(sorted({*k.t.LINEAS, "MOTOS", "BATERIAS"}))


def test_union_lineas_without_history_is_the_registry_default():
    assert k.union_lineas([]) == tuple(sorted(k.t.LINEAS))


def test_union_nits_keeps_the_default_and_strips_and_ignores_blanks():
    result = k.union_nits([[" 811000111 ", "  "], None, ["900723988"], "x"])

    assert result == tuple(sorted({*k.t.HMCL_NITS, "811000111"}))
