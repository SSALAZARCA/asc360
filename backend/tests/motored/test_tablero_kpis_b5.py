"""
KPI's (B5), pure math (no database): inventory days and the Tecnired block.
The queries behind them are covered in `pg_real/test_tablero_kpis_b5_pg.py`.
"""
import datetime
from decimal import Decimal

import pytest

from app.motored.services import tablero_kpis as k
from app.motored.services import tablero_kpis_consultas as qk

D = Decimal


@pytest.mark.parametrize("valor, costo_venta, dias_ventana, esperado", [
    (D("700"), D("900"), 90, 70.0),          # 900 over 90 days = 10 per day
    (D("1000"), D("920"), 92, 100.0),
    (D("0"), D("900"), 90, 0.0),
    (D("700"), D("0"), 90, None),            # no cost of sales -> no days
    (D("700"), None, 90, None),
    (D("700"), D("-5"), 90, None),
])
def test_inventory_days_divide_the_value_by_the_daily_cost_of_sales(valor, costo_venta, dias_ventana, esperado):
    assert k.dias_de_inventario(valor, costo_venta, dias_ventana) == esperado


def test_the_inventory_block_is_empty_without_inventory_loaded():
    bloque = k.construir_inventario([], {}, 90, None)

    assert bloque["fecha_corte"] is None and bloque["tiendas"] == {}
    assert bloque["red"]["dias"] is None and bloque["red"]["valor_inventario"] == 0.0


def test_the_inventory_block_has_the_days_per_store_and_for_the_network():
    corte = datetime.date(2026, 6, 30)
    filas = [qk.FilaInventario("s1", D("700"), 2), qk.FilaInventario("s2", D("300"), 0),
             qk.FilaInventario("s3", D("50"), 1)]
    costo_venta = {"s1": D("900"), "s2": D("900"), "s9": D("5000")}  # s3 has no sales; s9 has no inventory

    bloque = k.construir_inventario(filas, costo_venta, 90, corte)

    assert bloque["fecha_corte"] == "2026-06-30" and bloque["dias_ventana"] == 90
    assert set(bloque["tiendas"]) == {"s1", "s2", "s3"}  # only stores with inventory
    s1, s3 = bloque["tiendas"]["s1"], bloque["tiendas"]["s3"]
    assert (s1["valor_inventario"], s1["costo_venta_diario"], s1["dias"]) == (700.0, 10.0, 70.0)
    assert s1["lineas_sin_costo"] == 2 and s1["fecha_corte"] == "2026-06-30"
    assert (s3["costo_venta_diario"], s3["dias"]) == (0.0, None)
    # Network = sum of the listed stores: (700 + 300 + 50) over (900 + 900 + 0) / 90.
    assert bloque["red"]["valor_inventario"] == 1050.0
    assert bloque["red"]["costo_venta_diario"] == 20.0
    assert bloque["red"]["dias"] == 52.5 and bloque["red"]["lineas_sin_costo"] == 3


def test_the_tecnired_block_averages_per_client_and_falls_back_to_the_nit():
    total = {"venta_tecnired": 1000.0, "pct_tecnired": 0.25,
             "tecnired_por_mes": {"2026-01": 400.0, "2026-02": 600.0}, "tecnired_por_linea": {"REPUESTOS": 1000.0}}
    top = [qk.FilaTopTecnired("800", "Taller Uno", D("700")), qk.FilaTopTecnired("801", None, D("300"))]

    bloque = k.construir_tecnired(total, 4, {"2026-01": 3}, top, ["2026-01", "2026-02"])

    assert bloque["venta"] == 1000.0 and bloque["pct"] == 0.25 and bloque["clientes"] == 4
    assert bloque["venta_por_cliente"] == 250.0
    assert bloque["por_mes"] == {"2026-01": {"venta": 400.0, "clientes": 3},
                                 "2026-02": {"venta": 600.0, "clientes": 0}}
    assert bloque["por_linea"] == {"REPUESTOS": 1000.0}
    assert [f["razon_social"] for f in bloque["top5"]] == ["Taller Uno", "801"]
    assert bloque["top5"][0]["pct"] == pytest.approx(0.7) and bloque["top5"][0]["venta"] == 700.0


def test_the_tecnired_block_without_clients_has_no_average():
    total = {"venta_tecnired": 0.0, "pct_tecnired": None, "tecnired_por_mes": {}, "tecnired_por_linea": {}}

    bloque = k.construir_tecnired(total, 0, {}, [], ["2026-01"])

    assert bloque["venta_por_cliente"] is None and bloque["top5"] == []
    assert bloque["por_mes"] == {"2026-01": {"venta": 0.0, "clientes": 0}}
