"""
KPI's, pestana Comisiones: matematica pura (sin base de datos) de la liquidacion de un mes.
La lectura de ventas, presupuestos y reglas esta en `pg_real/test_tablero_comisiones_pg.py`.
"""
import uuid
from decimal import Decimal as D

import pytest

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_comisiones as c
from app.motored.services.presupuestos import LineaPresupuesto
from app.motored.services.tablero_asesores import FilaCubo

S1 = uuid.uuid4()
TIENDAS = {str(S1): "Norte"}
ASESOR = ("ASESOR DE REPUESTOS",)
REGLAS = c.reglas_desde_valores({})


def _linea(monto):
    return LineaPresupuesto(S1, monto)


def _liquidar(ventas, presupuestos, cargos=None, reglas=REGLAS, nombres=None):
    cargos = cargos if cargos is not None else {ced: ASESOR for ced in set(ventas) | set(presupuestos)}
    return c.liquidar_mes(
        {k: (D(v[0]), D(v[1])) for k, v in ventas.items()},
        {k: _linea(m) for k, m in presupuestos.items()}, nombres or {}, cargos, TIENDAS, reglas)


def _fila(asesores, cedula):
    return next(a for a in asesores if a["cedula"] == cedula)


def _venta(cedula, mes, monto, *, hmcl=False, linea="REPUESTOS", clave=None):
    return FilaCubo(
        clave or f"P:{cedula}", mes, linea, hmcl, False, False, True, D(monto), D(monto), D(0), D(1), 1, D(0))


# --- Rules -------------------------------------------------------------------------------------


def test_default_rules_match_the_registry_defaults():
    assert [(x.nombre, x.desde_pct, x.tasa_pct) for x in REGLAS.tramos] == [
        ("BASE", 0, D("1.0")), ("PRO", 90, D("1.5")), ("ELITE", 105, D("1.8"))]
    assert (REGLAS.base_pago, REGLAS.cumplimiento_base) == ("sin_hmcl", "con_hmcl")
    assert REGLAS.cargos == {"ASESOR DE REPUESTOS", "ASESOR DE REPUESTOS SUPERNUMERARIO"}


def test_rules_sort_the_tiers_and_normalize_the_cargos():
    r = c.reglas_desde_valores({
        "comision_tramos": [
            {"nombre": "TOP", "desde_pct": 120, "tasa_pct": 3}, {"nombre": "B", "desde_pct": 0, "tasa_pct": 1}],
        "comision_cargos_asesor": [" Asesor de Repuestós "], "comision_base_pago": "con_hmcl"})

    assert [x.nombre for x in r.tramos] == ["B", "TOP"]
    assert r.cargos == {"ASESOR DE REPUESTOS"} and r.base_pago == "con_hmcl"


@pytest.mark.parametrize("malo", [None, [], "x", [{"nombre": "A"}], [{"nombre": "A", "desde_pct": "x", "tasa_pct": 1}]])
def test_invalid_tiers_fall_back_to_the_defaults(malo):
    assert len(c.reglas_desde_valores({"comision_tramos": malo, "comision_base_pago": "otra"}).tramos) == 3


# --- Tier selection ----------------------------------------------------------------------------


@pytest.mark.parametrize("venta, esperado", [
    (0, "BASE"), (8999, "BASE"), (9000, "PRO"), (10499, "PRO"), (10500, "ELITE"), (30000, "ELITE")])
def test_the_tier_boundaries_are_inclusive_and_exact(venta, esperado):
    assert c.tramo_de(D(venta), 10000, REGLAS.tramos).nombre == esperado


def test_the_boundary_has_no_floating_point_error():
    # 105 % of 3 is 3.15: 3.15 / 3 in floats is 1.0499999...
    assert c.tramo_de(D("3.15"), 3, REGLAS.tramos).nombre == "ELITE"


def test_no_budget_means_no_tier_and_no_tier_reached_is_none():
    assert c.tramo_de(D(500), 0, REGLAS.tramos) is None
    sin_base = c.reglas_desde_valores({"comision_tramos": [{"nombre": "X", "desde_pct": 50, "tasa_pct": 2}]})
    assert c.tramo_de(D(10), 100, sin_base.tramos) is None


# --- Liquidation -------------------------------------------------------------------------------


def test_the_rate_is_flat_over_the_whole_paid_base():
    # Cumplimiento (con HMCL) 11000 / 10000 = 110 % -> ELITE 1.8 % of the sin-HMCL base 9000.
    asesores, adv = _liquidar({"1": (11000, 9000)}, {"1": 10000}, nombres={"1": "Ana"})

    a = _fila(asesores, "1")
    assert (a["tramo"], a["tasa_pct"], a["comision"]) == ("ELITE", 1.8, 162.0)
    assert (a["venta_cumplimiento"], a["venta_comision"], a["cumplimiento_pct"]) == (11000.0, 9000.0, 1.1)
    assert (a["nombre"], a["tienda"], a["sucursal_id"], a["presupuesto"]) == ("Ana", "Norte", str(S1), 10000)
    assert a["cargo"] == "ASESOR DE REPUESTOS"
    assert adv == {"sin_presupuesto": [], "cargo_desconocido": 0}


def test_the_bases_come_from_the_rules():
    reglas = c.reglas_desde_valores({"cumplimiento_base": "sin_hmcl", "comision_base_pago": "con_hmcl"})

    a = _fila(_liquidar({"1": (11000, 8000)}, {"1": 10000}, reglas=reglas)[0], "1")

    assert (a["venta_cumplimiento"], a["venta_comision"], a["tramo"]) == (8000.0, 11000.0, "BASE")
    assert a["comision"] == 110.0


def test_an_asesor_without_budget_earns_nothing_and_is_reported():
    asesores, adv = _liquidar({"1": (500, 400), "2": (100, 100)}, {"1": 1000}, nombres={"2": "Beto"})

    assert [a["cedula"] for a in asesores] == ["1"]
    assert adv["sin_presupuesto"] == [{"cedula": "2", "nombre": "Beto", "venta": 100.0}]


def test_a_budget_without_sales_is_rated_at_zero():
    a = _fila(_liquidar({}, {"1": 1000})[0], "1")

    assert (a["venta_cumplimiento"], a["cumplimiento_pct"], a["tramo"], a["comision"]) == (0.0, 0.0, "BASE", 0.0)


def test_only_commissioned_cargos_are_rated_and_unknown_ones_are_counted():
    cargos = {"1": ("ASESOR DE REPUESTOS",), "2": ("GERENTE",), "3": ()}

    ventas = {k: (1, 1) for k in "1234"}

    asesores, adv = _liquidar(ventas, {k: 10 for k in "1234"}, cargos)

    assert [a["cedula"] for a in asesores] == ["1"]
    # 2 (GERENTE) is excluded silently; 3 (empty cargo) and 4 (no entry) are unknown.
    assert adv["cargo_desconocido"] == 2 and adv["sin_presupuesto"] == []


# --- Summary, tiers and near-tier ------------------------------------------------------------


def _mes_de_ejemplo():
    ventas = {"1": (11000, 10000), "2": (9500, 9000), "3": (2000, 2000)}
    nombres = {"1": "Ana", "2": "Beto", "3": "Cami"}
    asesores, _ = _liquidar(ventas, {"1": 10000, "2": 10000, "3": 10000}, nombres=nombres)
    return asesores


def test_the_summary_totals_the_month():
    r = c.resumen_de(_mes_de_ejemplo())

    # Ana 10000 * 1.8 % = 180; Beto 9000 * 1.5 % = 135; Cami 2000 * 1 % = 20.
    assert (r["asesores"], r["comision_total"], r["venta_base"], r["comision_promedio"]) == (3, 335.0, 21000.0, 111.67)
    assert r["comision_mayor"] == {"cedula": "1", "nombre": "Ana", "comision": 180.0}
    assert r["comision_pct_venta"] == pytest.approx(335 / 21000)


def test_an_empty_month_has_a_neutral_summary():
    r = c.resumen_de([])

    assert (r["asesores"], r["comision_total"], r["comision_promedio"], r["comision_mayor"]) == (0, 0.0, 0.0, None)
    assert r["comision_pct_venta"] is None


def test_the_tiers_carry_the_count_of_asesores_in_each():
    tramos = c.tramos_con_conteo(_mes_de_ejemplo(), REGLAS)

    assert [(x["nombre"], x["desde_pct"], x["hasta_pct"], x["asesores"]) for x in tramos] == [
        ("BASE", 0.0, 90.0, 1), ("PRO", 90.0, 105.0, 1), ("ELITE", 105.0, None, 1)]


def test_near_tier_math_and_order():
    # Beto: 95 % (PRO), next ELITE at 105 %: falta 10000 * 1.05 - 9500 = 1000;
    # gana (9000 + 1000) * 1.8 % - 135 = 45. Cami is 85 pts away; Ana is already ELITE.
    cerca = c.cerca_de_subir(_mes_de_ejemplo())

    assert [f["cedula"] for f in cerca] == ["2"]
    f = cerca[0]
    assert (f["siguiente"], f["brecha_pts"], f["falta"], f["gana"], f["tramo"]) == ("ELITE", 10.0, 1000.0, 45.0, "PRO")


def test_near_tier_orders_by_smallest_gap_and_needs_sales():
    ventas = {"1": (8000, 8000), "2": (8950, 8950), "3": (0, 0), "4": (10400, 10400)}
    asesores, _ = _liquidar(ventas, {k: 10000 for k in ventas})

    cerca = c.cerca_de_subir(asesores)

    # 2 is 0.5 pt from PRO, 4 is 1 pt from ELITE, 1 is 10 pts from PRO; 3 sold nothing.
    assert [(f["cedula"], f["brecha_pts"]) for f in cerca] == [("2", 0.5), ("4", 1.0), ("1", 10.0)]


def test_the_gap_limit_is_15_points_inclusive():
    asesores, _ = _liquidar({"1": (7500, 7500), "2": (7499, 7499)}, {"1": 10000, "2": 10000})

    assert [f["cedula"] for f in c.cerca_de_subir(asesores)] == ["1"]


# --- Sales by cedula and month ---------------------------------------------------------------


def test_sales_accumulate_both_bases_per_cedula_and_month():
    cubo = [
        _venta("100", "2097-01", 1000), _venta("100", "2097-01", 500, hmcl=True), _venta("100", "2097-02", 300),
        _venta("100", "2097-01", 70, linea="OTRA"), _venta("1.200", "2097-01", 40),
        _venta("x", "2097-01", 9, clave="P:abc"), _venta("x", "2097-01", 9, clave="GRUPO"),
    ]

    ventas, claves, sin_cedula = c.ventas_por_cedula_mes(cubo, t.LINEAS)

    assert ventas[("100", "2097-01")] == (D(1500), D(1000)) and ventas[("100", "2097-02")] == (D(300), D(300))
    assert ventas[("1200", "2097-01")] == (D(40), D(40)) and claves["100"] == "P:100"
    assert sin_cedula == {"2097-01": {"P:abc": D(9)}}
