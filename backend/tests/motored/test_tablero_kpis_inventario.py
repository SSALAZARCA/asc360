"""
KPI's, Inventario tab: the pure pieces (cut choice, trend months, age bands, availability,
coverage, rotation, color cuts) and the builder that turns the query rows into the payload.
The real queries run in `pg_real/test_tablero_kpis_inventario_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal

import pytest

from app.motored.services import tablero_kpis_inventario as inv

D = Decimal
F = datetime.date
R1, R2, R3, R4 = (uuid.UUID(int=i) for i in (1, 2, 3, 4))


def _ym(anio, mes):
    return anio * 12 + mes - 1


# --- cuts ---------------------------------------------------------------------------------------


def test_the_corte_is_the_latest_one_on_or_before_the_end_of_the_month():
    cortes = [F(2026, 8, 31), F(2026, 9, 30), F(2026, 10, 7)]
    assert inv.elegir_corte(cortes, F(2026, 9, 30)) == F(2026, 9, 30)
    assert inv.elegir_corte(cortes, F(2026, 9, 29)) == F(2026, 8, 31)
    assert inv.elegir_corte(cortes, F(2026, 10, 31)) == F(2026, 10, 7)


def test_without_a_corte_before_the_month_the_latest_one_is_used():
    assert inv.elegir_corte([F(2026, 10, 1), F(2026, 10, 7)], F(2026, 8, 31)) == F(2026, 10, 7)
    assert inv.elegir_corte([], F(2026, 8, 31)) is None


def test_the_trend_keeps_only_months_with_a_corte_and_uses_the_latest_of_each():
    cortes = [F(2026, 7, 31), F(2026, 9, 15), F(2026, 9, 30), F(2026, 10, 1)]
    assert inv.cortes_de_tendencia(cortes, "2026-10") == [
        ("2026-07", F(2026, 7, 31)), ("2026-09", F(2026, 9, 30)), ("2026-10", F(2026, 10, 1))]


def test_the_trend_looks_back_12_months_and_never_past_the_reference_month():
    cortes = [F(2025, 10, 31), F(2025, 11, 30), F(2026, 10, 5), F(2026, 11, 3)]
    assert [m for m, _ in inv.cortes_de_tendencia(cortes, "2026-10")] == ["2025-11", "2026-10"]
    assert inv.cortes_de_tendencia([F(2025, 9, 30)], "2026-10") == []


def test_the_previous_corte_is_the_one_of_the_month_before_and_never_the_corte_itself():
    cortes = [F(2026, 8, 31), F(2026, 9, 30), F(2026, 10, 7)]
    assert inv.corte_anterior(cortes, "2026-10", F(2026, 10, 7)) == F(2026, 9, 30)
    assert inv.corte_anterior([F(2026, 10, 1), F(2026, 10, 7)], "2026-10", F(2026, 10, 7)) is None
    assert inv.corte_anterior(cortes, "2026-08", F(2026, 8, 31)) is None


# --- rotation and color cuts -------------------------------------------------------------------


def test_the_rotation_is_365_over_the_days():
    assert inv.rotacion(73.0) == pytest.approx(5.0)
    assert inv.rotacion(None) is None
    assert inv.rotacion(0) is None


def test_the_color_cuts_come_back_as_numbers_and_fall_back_to_the_default():
    assert inv.cortes_color({"verde_hasta": "45.5", "ambar_hasta": 75}) == {"verde_hasta": 45.5, "ambar_hasta": 75}
    assert inv.cortes_color(None) == {"verde_hasta": 60, "ambar_hasta": 90}
    assert inv.cortes_color({"verde_hasta": 90, "ambar_hasta": 60}) == {"verde_hasta": 60, "ambar_hasta": 90}


@pytest.mark.parametrize("valor", [
    {"verde_hasta": float("inf"), "ambar_hasta": float("inf")},
    {"verde_hasta": 10, "ambar_hasta": float("inf")},
    {"verde_hasta": float("nan"), "ambar_hasta": 90},
    {"verde_hasta": "inf", "ambar_hasta": "1e999"},
])
def test_non_finite_color_cuts_fall_back_to_the_default(valor):
    assert inv.cortes_color(valor) == {"verde_hasta": 60, "ambar_hasta": 90}


# --- days without sales and age bands -----------------------------------------------------------


def test_days_without_sales_count_from_the_last_day_of_the_last_month_with_sales():
    corte = F(2026, 10, 7)
    assert inv.dias_sin_venta(corte, _ym(2026, 9), _ym(2026, 1)) == 7
    assert inv.dias_sin_venta(corte, _ym(2026, 3), _ym(2026, 1)) == (corte - F(2026, 3, 31)).days
    assert inv.dias_sin_venta(corte, _ym(2026, 10), _ym(2026, 1)) == 0  # sold this month: never negative


def test_a_pair_never_sold_counts_from_the_first_day_of_the_sales_history():
    corte = F(2026, 10, 7)
    assert inv.dias_sin_venta(corte, None, _ym(2026, 1)) == (corte - F(2026, 1, 1)).days
    assert inv.dias_sin_venta(corte, None, None) == 6  # no history at all: since the first of the corte's month


@pytest.mark.parametrize("dias,banda", [(0, 0), (90, 0), (91, 1), (180, 1), (181, 2), (365, 2), (366, 3), (900, 3)])
def test_the_age_band_edges(dias, banda):
    assert inv.indice_de_banda(dias) == banda


def test_the_age_bands_add_up_value_and_share():
    pares = [(D("600"), 10), (D("300"), 100), (D("100"), 400), (D("0"), 500)]
    antig = inv.armar_antiguedad(pares, _ym(2026, 1))
    assert antig["historial_desde"] == "2026-01"
    assert [(b["desde"], b["hasta"]) for b in antig["bandas"]] == [(0, 90), (91, 180), (181, 365), (366, None)]
    assert [b["valor"] for b in antig["bandas"]] == [600.0, 300.0, 0.0, 100.0]
    assert [b["pct"] for b in antig["bandas"]] == [0.6, 0.3, 0.0, 0.1]


def test_the_age_bands_of_an_empty_inventory_have_no_share():
    antig = inv.armar_antiguedad([], None)
    assert antig["historial_desde"] is None
    assert all(b["valor"] == 0 and b["pct"] is None for b in antig["bandas"])


# --- demand, availability and transit coverage --------------------------------------------------


def _demanda():
    return {
        ("s1", R1): inv.Demanda(D("10"), D("2"), "REPUESTOS"),   # has stock
        ("s1", R2): inv.Demanda(D("5"), D("0"), "REPUESTOS"),    # out
        ("s1", R3): inv.Demanda(D("0"), D("4"), None),           # out, only lost sales
        ("s2", R1): inv.Demanda(D("-3"), D("0"), "REPUESTOS"),   # net returns: no demand
        ("s2", R4): inv.Demanda(D("7"), D("1"), "GPS"),          # out
    }


def test_the_demand_pairs_split_into_available_and_out_of_stock():
    evaluadas = inv.evaluar_demanda(_demanda(), {("s1", R1)}, {("s2", R4): D("8")})
    assert {(e.tienda, e.referencia_id) for e in evaluadas} == {
        ("s1", R1), ("s1", R2), ("s1", R3), ("s2", R4)}
    agotadas = [e for e in evaluadas if not e.disponible]
    assert {e.referencia_id for e in agotadas} == {R2, R3, R4}
    r4 = next(e for e in agotadas if e.referencia_id == R4)
    assert (r4.vendidas, r4.perdidas, r4.demanda, r4.transito) == (D("7"), D("1"), D("8"), D("8"))


def test_availability_is_the_share_of_demand_pairs_that_have_stock():
    evaluadas = inv.evaluar_demanda(_demanda(), {("s1", R1)}, {})
    assert inv.disponibilidad(evaluadas) == {"pct": 0.25, "agotadas": 3}
    assert inv.disponibilidad([]) == {"pct": None, "agotadas": 0}


def test_transit_coverage_is_capped_at_the_demand():
    assert inv.cobertura(D("60"), D("86")) == pytest.approx(60 / 86)
    assert inv.cobertura(D("200"), D("86")) == 1.0
    assert inv.cobertura(D("0"), D("86")) == 0.0
    assert inv.cobertura(D("5"), D("0")) is None


# --- the builder ---------------------------------------------------------------------------------

CORTE = F(2026, 10, 7)
S1, S2, S3 = "s1", "s2", "s3"


def _entradas(**cambios):
    """Two stores with stock at the corte (s1: 1000, s2: 500), s3 sells but has no inventory.
    Cost of sales (3 months, 92 days Aug-Oct): s1 = 600, s2 = 300, s3 = 900 (not counted: no inventory)."""
    base = dict(
        corte=CORTE, ultimo_mes="2026-10",
        valores_por_corte={
            F(2026, 9, 30): {S1: D("800"), S2: D("400")},
            CORTE: {S1: D("1000"), S2: D("500")}},
        cortes_tendencia=[("2026-09", F(2026, 9, 30)), ("2026-10", CORTE)],
        corte_anterior=F(2026, 9, 30),
        costos=[("2026-08", S1, "REPUESTOS", D("100")), ("2026-09", S1, "REPUESTOS", D("200")),
                ("2026-10", S1, None, D("300")), ("2026-08", S2, "GPS", D("300")),
                ("2026-09", S3, "REPUESTOS", D("900")), ("2026-07", S1, "REPUESTOS", D("5000"))],
        pares=[
            inv.Par(S1, R1, "REPUESTOS", D("10"), D("600"), _ym(2026, 10)),   # sold this month
            inv.Par(S1, R2, "REPUESTOS", D("4"), D("300"), _ym(2026, 3)),     # idle 190 days
            inv.Par(S1, R3, None, D("1"), D("100"), None),                    # never sold
            inv.Par(S2, R1, "GPS", D("5"), D("500"), _ym(2026, 6)),           # idle 98 days
        ],
        demanda={
            (S1, R1): inv.Demanda(D("10"), D("0"), "REPUESTOS"),
            (S1, R4): inv.Demanda(D("20"), D("6"), "REPUESTOS"),              # out, 60 coming
            (S2, R4): inv.Demanda(D("3"), D("0"), "GPS"),                     # out, nothing coming
            (S2, R1): inv.Demanda(D("2"), D("0"), "GPS"),
        },
        transito={(S1, R4): D("60")}, historial_ym=_ym(2026, 1),
        lineas=("REPUESTOS", "GPS"), umbral=180, dias_meta=60,
        cortes_color={"verde_hasta": 60, "ambar_hasta": 90}, pendientes=(286.5, 12),
        nombres_tienda={S1: "Norte", S2: "Sur", S3: "Este"})
    base.update(cambios)
    return inv.Entradas(**base)


def test_the_cards_value_days_rotation_and_previous_month():
    tarjetas = inv.analizar(_entradas()).datos["tarjetas"]
    assert tarjetas["valor"] == 1500.0 and tarjetas["valor_mes_anterior"] == 1200.0
    # 1500 / ((100+200+300+300) / 92 days of Aug..Oct); s3 has no inventory so its cost stays out.
    assert tarjetas["dias"] == pytest.approx(1500 * 92 / 900)
    assert tarjetas["rotacion"] == pytest.approx(365 / tarjetas["dias"])
    assert tarjetas["dias_meta"] == 60
    assert tarjetas["transito"] == {"valor": 286.5, "facturas": 12}


def test_the_previous_value_is_empty_without_a_previous_corte():
    assert inv.analizar(_entradas(corte_anterior=None)).datos["tarjetas"]["valor_mes_anterior"] is None


def test_idle_stock_uses_the_threshold_and_never_sold_pairs_count_from_the_history_start():
    resultado = inv.analizar(_entradas())
    sin_mov = resultado.datos["tarjetas"]["sin_movimiento"]
    # s1/R2 (190 d, 300) and s1/R3 never sold since Jan 1 (279 d, 100); s2/R1 is 98 d: under the 180 threshold.
    assert sin_mov["valor"] == 400.0 and sin_mov["pct"] == pytest.approx(400 / 1500)
    assert [(x["sucursal_id"], x["valor"], x["dias_sin_venta"]) for x in resultado.sin_movimiento] == [
        (S1, 300.0, (CORTE - F(2026, 3, 31)).days), (S1, 100.0, (CORTE - F(2026, 1, 1)).days)]
    assert inv.analizar(_entradas(umbral=90)).datos["tarjetas"]["sin_movimiento"]["valor"] == 900.0


def test_the_age_bands_and_the_history_start_are_in_the_payload():
    antiguedad = inv.analizar(_entradas()).datos["antiguedad"]
    assert antiguedad["historial_desde"] == "2026-01"
    assert [b["valor"] for b in antiguedad["bandas"]] == [600.0, 500.0, 400.0, 0.0]


def test_availability_counts_the_pairs_with_demand_that_have_stock():
    resultado = inv.analizar(_entradas())
    assert resultado.datos["tarjetas"]["disponibilidad"] == {"pct": 0.5, "agotadas": 2}
    agotadas = resultado.datos["agotadas"]
    assert (agotadas["total"], agotadas["en_transito"], agotadas["sin_pedir"]) == (2, 1, 1)
    assert [(a["sucursal_id"], a["vendidas"], a["perdidas"], a["demanda"], a["transito"]) for a in resultado.agotadas] == [
        (S1, 20, 6, 26, 60), (S2, 3, 0, 3, 0)]
    assert [a["cobertura"] for a in resultado.agotadas] == [1.0, 0.0]  # 60 of 26 is capped at all covered


def test_the_trend_has_one_point_per_corte_month_with_its_own_days():
    tendencia = inv.analizar(_entradas()).datos["tendencia"]
    assert [p["mes"] for p in tendencia] == ["2026-09", "2026-10"]
    assert tendencia[0]["corte"] == "2026-09-30" and tendencia[0]["valor"] == 1200.0
    # September window = Jul..Sep (92 days): s1 5000+100... only Aug and Sep and Jul rows of s1/s2.
    costo_sep = 5000 + 100 + 200 + 300
    assert tendencia[0]["dias"] == pytest.approx(1200 * 92 / costo_sep)
    assert tendencia[1]["dias"] == pytest.approx(1500 * 92 / 900)


def test_the_lines_carry_value_share_days_and_availability_with_a_bucket_for_no_line():
    lineas = {x["linea"]: x for x in inv.analizar(_entradas()).datos["lineas"]}
    assert list(lineas) == ["REPUESTOS", "GPS", "Sin línea"]
    assert lineas["REPUESTOS"]["valor"] == 900.0 and lineas["REPUESTOS"]["pct"] == pytest.approx(0.6)
    assert lineas["REPUESTOS"]["dias"] == pytest.approx(900 * 92 / 300)
    assert lineas["REPUESTOS"]["disponibilidad_pct"] == pytest.approx(1 / 2)
    assert lineas["GPS"]["dias"] == pytest.approx(500 * 92 / 300)
    assert lineas["Sin línea"]["valor"] == 100.0 and lineas["Sin línea"]["disponibilidad_pct"] is None


def test_the_no_line_bucket_is_left_out_when_it_is_empty():
    pares = [inv.Par(S1, R1, "REPUESTOS", D("1"), D("10"), _ym(2026, 10))]
    nombres = [x["linea"] for x in inv.analizar(_entradas(pares=pares, demanda={})).datos["lineas"]]
    assert nombres == ["REPUESTOS", "GPS"]


def test_the_stores_are_ordered_by_days_and_only_those_with_inventory_appear():
    tiendas = inv.analizar(_entradas()).datos["tiendas"]
    assert [t_["sucursal_id"] for t_ in tiendas] == [S1, S2]  # s3 sells but has no inventory
    s1 = tiendas[0]
    assert s1["nombre"] == "Norte" and s1["valor"] == 1000.0
    assert s1["dias"] == pytest.approx(1000 * 92 / 600) and s1["rotacion"] == pytest.approx(365 / s1["dias"])
    assert s1["sin_movimiento_valor"] == 400.0
    assert (s1["disponibilidad_pct"], s1["agotadas"]) == (0.5, 1)
    assert tiendas[1]["sin_movimiento_valor"] == 0.0 and tiendas[1]["agotadas"] == 1


def test_a_store_without_cost_of_sales_has_no_days_and_goes_last():
    costos = [("2026-10", S1, "REPUESTOS", D("600"))]
    tiendas = inv.analizar(_entradas(costos=costos)).datos["tiendas"]
    assert [x["sucursal_id"] for x in tiendas] == [S1, S2]
    assert tiendas[1]["dias"] is None and tiendas[1]["rotacion"] is None


def test_the_window_and_the_color_cuts_are_echoed():
    datos = inv.analizar(_entradas()).datos
    assert (datos["corte"], datos["costo_desde"], datos["costo_hasta"]) == ("2026-10-07", "2026-08-01", "2026-10-31")
    assert datos["cortes_color"] == {"verde_hasta": 60, "ambar_hasta": 90}


def test_an_empty_world_gives_an_empty_but_complete_payload():
    resultado = inv.analizar(_entradas(
        valores_por_corte={CORTE: {}}, cortes_tendencia=[], corte_anterior=None, costos=[], pares=[],
        demanda={}, transito={}, historial_ym=None, pendientes=(0, 0)))
    datos = resultado.datos
    assert datos["tarjetas"]["valor"] == 0 and datos["tarjetas"]["dias"] is None
    assert datos["tarjetas"]["disponibilidad"] == {"pct": None, "agotadas": 0}
    assert datos["tendencia"] == [] and datos["tiendas"] == [] and resultado.agotadas == []


# --- the bands of the trend ----------------------------------------------------------------------

CORTES_60_90 = {"verde_hasta": 60, "ambar_hasta": 90}


@pytest.mark.parametrize("dias, banda", [
    (0, "verde"), (60, "verde"), (60.4, "ambar"), (61, "ambar"), (90, "ambar"), (90.01, "violeta"),
    (91, "violeta"), (None, "violeta")])
def test_the_band_of_a_pair_follows_its_days_and_the_configured_cuts(dias, banda):
    assert inv.banda_de_dias(dias, CORTES_60_90) == banda


def test_the_band_cuts_are_the_configured_ones():
    cortes = {"verde_hasta": 30, "ambar_hasta": 45}
    assert [inv.banda_de_dias(d, cortes) for d in (30, 31, 45, 46)] == ["verde", "ambar", "ambar", "violeta"]


def _pares_de_bandas():
    """Aug..Oct has 92 days, so a pair of value V and cost 92 lasts exactly V days."""
    return {
        CORTE: [(S1, R1, D("60")), (S1, R2, D("61")), (S1, R3, D("90")), (S2, R1, D("91")), (S2, R2, D("50"))],
        F(2026, 9, 30): [(S1, R1, D("30"))]}


def _costos_de_bandas():
    return [("2026-10", S1, R1, D("92")), ("2026-09", S1, R2, D("40")), ("2026-08", S1, R2, D("52")),
            ("2026-08", S1, R3, D("92")), ("2026-10", S2, R1, D("92")), ("2026-07", S2, R2, D("999")),
            ("2026-10", S2, R2, D("-5"))]


def test_each_trend_point_splits_its_value_by_the_days_of_each_pair_at_the_boundaries():
    e = _entradas(pares_por_corte=_pares_de_bandas(), costos_por_par=_costos_de_bandas())

    bandas = {b["banda"]: b for b in inv.analizar(e).datos["tendencia"][1]["bandas"]}

    assert list(bandas) == ["verde", "ambar", "violeta"]
    assert bandas["verde"]["valor"] == 60.0                     # exactly 60 days
    assert bandas["ambar"]["valor"] == 151.0                    # 61 days (cost 40+52 over two months) and 90 days
    assert bandas["violeta"]["valor"] == 141.0                  # 91 days, and a pair whose only cost is outside / negative
    assert [b["pct"] for b in bandas.values()] == pytest.approx([60 / 352, 151 / 352, 141 / 352])
    assert sum(b["pct"] for b in bandas.values()) == pytest.approx(1.0)


def test_a_pair_without_cost_of_sales_in_the_window_is_not_moving_so_it_falls_in_violet():
    e = _entradas(pares_por_corte={CORTE: [(S1, R1, D("10"))]}, costos_por_par=[("2026-05", S1, R1, D("500"))])

    bandas = inv.analizar(e).datos["tendencia"][1]["bandas"]

    assert [(b["banda"], b["valor"]) for b in bandas] == [("verde", 0.0), ("ambar", 0.0), ("violeta", 10.0)]


def test_each_point_uses_the_window_that_ends_in_its_own_month():
    e = _entradas(pares_por_corte=_pares_de_bandas(), costos_por_par=[("2026-07", S1, R1, D("92"))])

    septiembre, octubre = inv.analizar(e).datos["tendencia"]

    assert [b["valor"] for b in septiembre["bandas"]] == [30.0, 0.0, 0.0]   # Jul..Sep sees the July cost
    assert [b["valor"] for b in octubre["bandas"]][2] == 352.0            # Aug..Oct does not: all violet


def test_a_point_without_pairs_has_zero_values_and_no_share():
    bandas = inv.analizar(_entradas()).datos["tendencia"][0]["bandas"]

    assert [(b["valor"], b["pct"]) for b in bandas] == [(0.0, None)] * 3
