"""
KPI's, pestana Comisiones: per-line bonuses (pure math, no database).
Gate: total cumplimiento >= umbral; line: line venta >= pct_meta % of the asesor's TOTAL venta.
Everything is measured on `cumplimiento_base`.
"""
import uuid
from decimal import Decimal as D

import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_comisiones as c
from app.motored.services.presupuestos import LineaPresupuesto
from app.motored.services.tablero_asesores import FilaCubo

S1 = uuid.uuid4()
TIENDAS = {str(S1): "Norte"}
ASESOR = ("ASESOR DE REPUESTOS",)
REGLAS = c.reglas_desde_valores({})
UMBRAL = D(95)


def _bono(linea, pct, bono, activo=True):
    return c.LineaBono(linea, D(pct), bono, activo)


LINEAS = (_bono("CASCOS", 6, 30000), _bono("LUBRICANTES", 21, 35000), _bono("TECNIRED", 6, 25000))


def _calcular(total, presupuesto, por_linea=None, tecnired=0, lineas=LINEAS, umbral=UMBRAL):
    return c.bonos_de_asesor(
        D(total), presupuesto, {k: D(v) for k, v in (por_linea or {}).items()}, D(tecnired), lineas, umbral)


def _linea_de(resultado, linea):
    return next(b for b in resultado["bonos"] if b["linea"] == linea)


# --- Rules -------------------------------------------------------------------------------------


def test_default_bonus_rules_match_the_registry_defaults():
    esperado = [(x["linea"], D(x["pct_meta"]), int(x["bono"]), x["activo"]) for x in pc.REGISTRO["comision_lineas"].default]
    assert [tuple(x) for x in REGLAS.bonos] == esperado
    assert REGLAS.umbral_bono_pct == D(pc.REGISTRO["comision_bono_umbral_pct"].default)
    assert c.respaldos()["comision_lineas"] == pc.REGISTRO["comision_lineas"].default
    assert c.respaldos()["comision_bono_umbral_pct"] == "95"


def test_rules_read_numbers_and_strings_and_keep_the_config_order():
    r = c.reglas_desde_valores({
        "comision_lineas": [
            {"linea": "TECNIRED", "pct_meta": 6.5, "bono": "25000", "activo": False},
            {"linea": "CASCOS", "pct_meta": "6", "bono": 30000.0, "activo": True}],
        "comision_bono_umbral_pct": 90})
    assert r.bonos == (_bono("TECNIRED", "6.5", 25000, False), _bono("CASCOS", 6, 30000))
    assert r.umbral_bono_pct == D(90)


def test_an_empty_list_means_no_bonuses():
    assert c.reglas_desde_valores({"comision_lineas": []}).bonos == ()


@pytest.mark.parametrize("valor", [
    "x", [{"linea": "CASCOS"}], [{"linea": "CASCOS", "pct_meta": "0", "bono": "1", "activo": True}],
    [{"linea": "CASCOS", "pct_meta": "5", "bono": "-1", "activo": True}],
])
def test_an_invalid_bonus_list_goes_back_to_the_default(valor):
    assert c.reglas_desde_valores({"comision_lineas": valor}).bonos == REGLAS.bonos


def test_an_invalid_threshold_goes_back_to_the_default():
    assert c.reglas_desde_valores({"comision_bono_umbral_pct": "abc"}).umbral_bono_pct == D(95)


def test_the_rules_echo_carries_the_bonus_keys_with_labels():
    eco = c.eco_reglas_comision(REGLAS)
    assert eco["comision_bono_umbral_pct"] == 95.0
    assert eco["comision_lineas"][0] == {
        "linea": "LUBRICANTES", "etiqueta": "Lubricantes", "pct_meta": 21.0, "bono": 35000, "activo": True}
    assert {x["linea"]: x["etiqueta"] for x in eco["comision_lineas"]}["ACCESORIOS"] == "Otros accesorios"


# --- minimo_linea ------------------------------------------------------------------------------


def test_the_line_minimum_is_the_budget_times_threshold_times_target():
    assert c.minimo_linea(1_000_000, D(95), D(21)) == 199_500


@pytest.mark.parametrize("presupuesto, umbral, pct, esperado", [
    (10, 50, 10, 1),     # 0.5 rounds up
    (1, 50, 50, 0),      # 0.25
    (3, 50, 50, 1),      # 0.75
    (1_234_567, 95, 3, 35_185),  # 35185.0095 -> 35185
])
def test_the_line_minimum_rounds_half_up_to_whole_pesos(presupuesto, umbral, pct, esperado):
    assert c.minimo_linea(presupuesto, D(umbral), D(pct)) == esperado


# --- Gate --------------------------------------------------------------------------------------


def test_the_gate_is_inclusive_at_exactly_the_threshold():
    ok = _calcular(950_000, 1_000_000, {"CASCOS": 950_000})
    assert ok["gate"] == {"umbral": 95.0, "cumple": True}
    assert _linea_de(ok, "CASCOS")["bono_pagado"] == 30000


def test_below_the_threshold_nothing_is_paid_but_the_line_status_is_still_shown():
    r = _calcular(949_999, 1_000_000, {"CASCOS": 949_999})
    assert r["gate"]["cumple"] is False
    cascos = _linea_de(r, "CASCOS")
    assert cascos["cumple"] is True and cascos["bono_pagado"] == 0 and r["bono_total"] == 0


def test_no_budget_means_the_gate_fails_without_dividing():
    r = _calcular(1_000, 0, {"CASCOS": 1_000})
    assert r["gate"]["cumple"] is False and r["bono_total"] == 0


# --- Lines -------------------------------------------------------------------------------------


def test_a_line_is_met_at_exactly_its_percentage_of_the_total():
    r = _calcular(1_000_000, 1_000_000, {"CASCOS": 60_000})
    cascos = _linea_de(r, "CASCOS")
    assert cascos["cumple"] is True and cascos["pct_real"] == 0.06 and cascos["bono_pagado"] == 30000
    assert _linea_de(_calcular(1_000_000, 1_000_000, {"CASCOS": 59_999}), "CASCOS")["cumple"] is False


def test_each_line_reports_its_target_label_and_sale():
    r = _calcular(1_000_000, 1_000_000, {"LUBRICANTES": 250_000})
    assert _linea_de(r, "LUBRICANTES") == {
        "linea": "LUBRICANTES", "etiqueta": "Lubricantes", "venta": 250_000.0, "pct_real": 0.25, "pct_meta": 21.0,
        "bono": 35000, "cumple": True, "paga": True, "activo": True, "bono_pagado": 35000}
    assert [b["linea"] for b in r["bonos"]] == ["CASCOS", "LUBRICANTES", "TECNIRED"]


def test_an_inactive_line_is_shown_as_met_but_not_paid():
    lineas = (_bono("CASCOS", 6, 30000, activo=False),)
    cascos = _linea_de(_calcular(1_000_000, 1_000_000, {"CASCOS": 100_000}, lineas=lineas), "CASCOS")
    assert (cascos["cumple"], cascos["activo"], cascos["paga"], cascos["bono_pagado"]) == (True, False, False, 0)


def test_a_line_without_sales_is_never_met_even_with_no_total():
    r = _calcular(0, 1_000_000)
    assert all(not b["cumple"] and b["pct_real"] is None for b in r["bonos"])


def test_tecnired_counts_the_tecnired_sale_and_overlaps_the_other_lines():
    r = _calcular(1_000_000, 1_000_000, {"CASCOS": 60_000}, tecnired=60_000)
    assert _linea_de(r, "CASCOS")["bono_pagado"] == 30000
    assert _linea_de(r, "TECNIRED")["bono_pagado"] == 25000
    assert r["bono_total"] == 55000


def test_the_total_is_the_sum_of_the_paid_bonuses_only():
    lineas = (_bono("CASCOS", 6, 30000), _bono("LUBRICANTES", 21, 35000, activo=False))
    r = _calcular(1_000_000, 1_000_000, {"CASCOS": 70_000, "LUBRICANTES": 300_000}, lineas=lineas)
    assert r["bono_total"] == 30000


# --- liquidar_mes ------------------------------------------------------------------------------


def _liquidar(ventas, presupuestos, por_linea, reglas=REGLAS):
    cargos = {ced: ASESOR for ced in set(ventas) | set(presupuestos)}
    return c.liquidar_mes(
        {k: (D(v[0]), D(v[1])) for k, v in ventas.items()},
        {k: LineaPresupuesto(S1, m) for k, m in presupuestos.items()}, {}, cargos, TIENDAS, reglas,
        {ced: {linea: (D(v[0]), D(v[1])) for linea, v in lineas.items()} for ced, lineas in por_linea.items()})


def test_the_asesor_total_adds_the_bonuses_to_the_commission():
    asesores, _ = _liquidar(
        {"100": (1_000_000, 900_000)}, {"100": 1_000_000},
        {"100": {"CASCOS": (70_000, 60_000), "TECNIRED": (100_000, 0)}})
    a = asesores[0]
    assert a["gate"] == {"umbral": 95.0, "cumple": True}
    assert a["comision"] == 13500.0           # 900.000 sin HMCL x 1.5 % (PRO)
    paga = {b["linea"]: b["bono_pagado"] for b in a["bonos"]}
    assert paga["CASCOS"] == 30000 and paga["TECNIRED"] == 25000 and paga["LUBRICANTES"] == 0
    assert a["bono_total"] == 55000 and a["total_a_pagar"] == 68500.0


def test_the_lines_are_measured_on_the_cumplimiento_base():
    reglas = c.reglas_desde_valores({"cumplimiento_base": "sin_hmcl"})
    asesores, _ = _liquidar(
        {"100": (1_000_000, 960_000)}, {"100": 1_000_000}, {"100": {"CASCOS": (900_000, 60_000)}}, reglas)
    cascos = _linea_de(asesores[0], "CASCOS")
    assert asesores[0]["gate"]["cumple"] is True and cascos["venta"] == 60_000.0 and cascos["cumple"] is True


def test_an_asesor_without_a_budget_is_left_out_with_no_bonuses():
    asesores, adv = _liquidar({"100": (5_000, 5_000)}, {}, {"100": {"CASCOS": (5_000, 5_000)}})
    assert asesores == [] and [x["cedula"] for x in adv["sin_presupuesto"]] == ["100"]


def test_an_asesor_with_a_budget_and_no_sales_has_zero_bonuses():
    asesores, _ = _liquidar({}, {"100": 1_000_000}, {})
    a = asesores[0]
    assert a["bono_total"] == 0 and a["total_a_pagar"] == 0 and a["gate"]["cumple"] is False


def test_liquidar_without_line_sales_still_works():
    asesores, _ = c.liquidar_mes(
        {"100": (D(1000), D(1000))}, {"100": LineaPresupuesto(S1, 1000)}, {}, {"100": ASESOR}, TIENDAS, REGLAS)
    assert asesores[0]["bono_total"] == 0 and asesores[0]["total_a_pagar"] == asesores[0]["comision"]


# --- resumen -----------------------------------------------------------------------------------


def _mes():
    asesores, _ = _liquidar(
        {"100": (1_000_000, 1_000_000), "200": (1_000_000, 1_000_000), "300": (900_000, 500_000)},
        {"100": 1_000_000, "200": 1_000_000, "300": 1_000_000},
        {"100": {"CASCOS": (60_000, 60_000), "LUBRICANTES": (210_000, 210_000)},
         "200": {"CASCOS": (60_000, 60_000)}, "300": {"CASCOS": (900_000, 900_000)}})
    return asesores


def test_the_summary_totals_the_bonuses_and_the_amount_to_pay():
    r = c.resumen_de(_mes(), REGLAS)
    assert r["bonos_total"] == 30000 + 35000 + 30000     # asesor 300 fails the 95 % gate
    assert r["total_a_pagar"] == round(r["comision_total"] + r["bonos_total"], 2)


def test_the_summary_lists_every_configured_line_with_winners_and_amount():
    por_linea = {x["linea"]: x for x in c.resumen_de(_mes(), REGLAS)["por_linea"]}
    assert [x["linea"] for x in c.resumen_de(_mes(), REGLAS)["por_linea"]] == [b.linea for b in REGLAS.bonos]
    assert (por_linea["CASCOS"]["ganadores"], por_linea["CASCOS"]["monto"]) == (2, 60000.0)
    assert (por_linea["LUBRICANTES"]["ganadores"], por_linea["LUBRICANTES"]["monto"]) == (1, 35000.0)
    assert por_linea["LUBRICANTES"]["etiqueta"] == "Lubricantes"
    assert (por_linea["LLANTAS"]["ganadores"], por_linea["LLANTAS"]["monto"]) == (0, 0.0)


def test_the_summary_of_an_empty_month_has_zero_bonuses():
    r = c.resumen_de([], REGLAS)
    assert (r["bonos_total"], r["total_a_pagar"]) == (0.0, 0.0)
    assert all(x["ganadores"] == 0 for x in r["por_linea"])


# --- Sales per line ----------------------------------------------------------------------------


def _fila(cedula, mes, monto, linea, *, hmcl=False, tecnired=False, clave=None):
    return FilaCubo(
        clave or f"P:{cedula}", mes, linea, hmcl, tecnired, False, True, D(monto), D(monto), D(0), D(1), 1, D(0))


def test_line_sales_accumulate_both_bases_and_tecnired_across_lines():
    cubo = [
        _fila("100", "2097-01", 1000, "CASCOS"), _fila("100", "2097-01", 500, "CASCOS", hmcl=True),
        _fila("100", "2097-01", 200, "LUBRICANTES", tecnired=True),
        _fila("100", "2097-01", 70, "CASCOS", tecnired=True, hmcl=True),
        _fila("100", "2097-01", 9, None, tecnired=True), _fila("100", "2097-01", 9, "OTRA"),
        _fila("x", "2097-01", 9, "CASCOS", clave="P:abc"), _fila("x", "2097-01", 9, "CASCOS", clave="GRUPO"),
        _fila("100", "2097-02", 300, "CASCOS"),
    ]
    r = c.ventas_por_linea_cedula_mes(cubo, t.LINEAS)
    assert r[("100", "2097-01")] == {
        "CASCOS": (D(1570), D(1000)), "LUBRICANTES": (D(200), D(200)), "TECNIRED": (D(270), D(200))}
    assert r[("100", "2097-02")] == {"CASCOS": (D(300), D(300))} and ("abc", "2097-01") not in r


# --- Presupuestos month detail -------------------------------------------------------------------


def test_the_budget_detail_lists_only_the_active_lines_in_config_order():
    reglas = c.reglas_desde_valores({"comision_lineas": [
        {"linea": "TECNIRED", "pct_meta": "6.5", "bono": "25000", "activo": True},
        {"linea": "CASCOS", "pct_meta": "6", "bono": "30000", "activo": False},
        {"linea": "LLANTAS", "pct_meta": "1", "bono": "0", "activo": True}]})

    assert c.lineas_con_bono(reglas) == [
        {"linea": "TECNIRED", "etiqueta": "Tecnired (clientes)", "pct_meta": 6.5, "bono": 25000},
        {"linea": "LLANTAS", "etiqueta": "Llantas", "pct_meta": 1.0, "bono": 0}]


def test_the_minimums_of_a_budget_use_the_threshold_and_each_target():
    reglas = c.reglas_desde_valores({"comision_bono_umbral_pct": "90", "comision_lineas": [
        {"linea": "CASCOS", "pct_meta": "6", "bono": "30000", "activo": True},
        {"linea": "LLANTAS", "pct_meta": "1", "bono": "1", "activo": False}]})

    assert c.minimos_de_presupuesto(reglas, 1_000_000) == {"CASCOS": 54_000}
    assert c.minimos_de_presupuesto(c.reglas_desde_valores({"comision_lineas": []}), 1_000_000) == {}
