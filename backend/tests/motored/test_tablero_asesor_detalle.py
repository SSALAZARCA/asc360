"""
KPI's, Asesores tab, single-asesor detail: pure math (no database).

Hand-computed world, three asesores and three months. Budgets (Ana has none in
February, so her February point is null):

            Ene            Feb            Mar
  Ana  100  600 / 600      600 / -        700 / 1000     store Norte
  Beto 200  400 / 500      300 / 500      500 / 500      store Norte
  Cami 300  100 / 200      200 / 200      800 / 400      store Sur

Sales period total: Ana 1900, Beto 1200, Cami 1100 (network 4200).
Tecnired: only Ana, 100 (February, ACCESORIOS). Cost: 70 % of Ana's sales, 80 % of Beto's, 90 % of Cami's.
"""
import datetime
import uuid
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.motored.services import tablero_asesor_detalle as d
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.presupuestos import LineaPresupuesto
from app.motored.services.tablero_asesores import FilaCubo, FilaClientes, FilaFacturas, FilaPersona

NORTE, SUR = uuid.uuid4(), uuid.uuid4()
TIENDAS = {str(NORTE): "Norte", str(SUR): "Sur"}
MESES = ["2026-01", "2026-02", "2026-03"]
COSTO = {"100": D("0.7"), "200": D("0.8"), "300": D("0.9")}


def _v(cedula, mes, monto, linea="REPUESTOS", tecnired=False):
    return FilaCubo(
        f"P:{cedula}", mes, linea, False, tecnired, False, True, D(monto), D(monto), D(0), D(1), 1,
        D(monto) * COSTO[cedula])


CUBO = [
    _v("100", "2026-01", 600), _v("100", "2026-02", 500), _v("100", "2026-02", 100, "ACCESORIOS", True),
    _v("100", "2026-03", 700),
    _v("200", "2026-01", 400), _v("200", "2026-02", 300), _v("200", "2026-03", 500),
    _v("300", "2026-01", 100), _v("300", "2026-02", 200), _v("300", "2026-03", 800),
]
PRESUPUESTOS = {
    ("2026-01", "100"): LineaPresupuesto(NORTE, 600), ("2026-03", "100"): LineaPresupuesto(NORTE, 1000),
    ("2026-01", "200"): LineaPresupuesto(NORTE, 500), ("2026-02", "200"): LineaPresupuesto(NORTE, 500),
    ("2026-03", "200"): LineaPresupuesto(NORTE, 500),
    ("2026-01", "300"): LineaPresupuesto(SUR, 200), ("2026-02", "300"): LineaPresupuesto(SUR, 200),
    ("2026-03", "300"): LineaPresupuesto(SUR, 400),
}
SUCURSALES = {str(NORTE): ("Norte", None), str(SUR): ("Sur", None)}
NOMBRES = {"100": "Ana", "200": "Beto", "300": "Cami"}
FACTURAS = [
    FilaFacturas("P:100", 10, 0, (0,) * 7), FilaFacturas("P:200", 12, 0, (0,) * 7),
    FilaFacturas("P:300", 20, 0, (0,) * 7), FilaFacturas(t.CLAVE_TOTAL, 42, 0, (0,) * 7),
]
CLIENTES = [
    FilaClientes("P:100", 7, D(0)), FilaClientes("P:200", 5, D(0)), FilaClientes("P:300", 3, D(0)),
    FilaClientes(t.CLAVE_TOTAL, 12, D(0)),
]
PERSONAS = [
    FilaPersona(f"P:{c}", 1, n, "ASESOR DE REPUESTOS", "Norte" if c != "300" else "Sur")
    for c, n in NOMBRES.items()
]
COMISION = {
    "mes_liquidado": "2026-03",
    "reglas": {"comision_base_pago": "sin_hmcl"},
    "resumen": {"comision_promedio": 394000.0},
    "tramos": [
        {"nombre": "BASE", "desde_pct": 0.0, "tasa_pct": 1.0},
        {"nombre": "PRO", "desde_pct": 90.0, "tasa_pct": 1.5},
        {"nombre": "ELITE", "desde_pct": 105.0, "tasa_pct": 1.8},
    ],
    "asesores": [{
        "cedula": "100", "presupuesto": 1000, "venta_cumplimiento": 700.0, "venta_comision": 700.0,
        "tramo": "BASE", "tasa_pct": 1.0, "comision": 7.0, "cumplimiento_pct": 0.7,
        "gate": {"umbral": 95.0, "cumple": False}, "bono_total": 0, "total_a_pagar": 7.0,
        "bonos": [{"linea": "CASCOS", "etiqueta": "Cascos", "venta": 70.0, "pct_real": 0.1, "pct_meta": 6.0,
                   "bono": 30000, "cumple": True, "paga": False, "activo": True, "bono_pagado": 0}],
        "sig": {"nombre": "PRO", "desde_pct": 90.0, "tasa_pct": 1.5, "falta": 200.0, "gana": 3.5},
    }],
}
TOP = [SimpleNamespace(nit="9001", razon_social="Taller Uno", venta=D(100)), SimpleNamespace(nit="9002", razon_social=None, venta=D(40))]


def _mundo(presupuestos=PRESUPUESTOS, cubo=CUBO):
    tablero = t.construir_tablero(cubo, FACTURAS, CLIENTES, PERSONAS, MESES)
    tablero["meses"] = MESES
    tablero["reglas"] = q.eco_reglas(t.REGLAS_POR_DEFECTO, MESES[-1])
    kw = dict(sucursales=SUCURSALES, nombres=NOMBRES)
    cumplimiento = k.construir_cumplimiento(cubo, presupuestos, t.REGLAS_POR_DEFECTO, **kw)
    por_mes = k.cumplimiento_por_mes(cubo, presupuestos, t.REGLAS_POR_DEFECTO, MESES, **kw)
    return tablero, cumplimiento, por_mes


def _detalle(cedula="100", comision=COMISION, maestro=None, clientes=4, top=TOP, fecha_datos=None, **mundo):
    tablero, cumplimiento, por_mes = _mundo(**mundo)
    return d.construir_detalle(
        cedula, tablero, cumplimiento, por_mes, comision, clientes, top, maestro, TIENDAS, fecha_datos)


def _con_fila(**cambios):
    return {**COMISION, "asesores": [{**COMISION["asesores"][0], **cambios}]}


# --- cumplimiento_por_mes ----------------------------------------------------------------------


def test_each_month_is_measured_only_against_the_budgets_of_that_month():
    _, _, por_mes = _mundo()

    assert list(por_mes) == MESES
    ene = next(a for a in por_mes["2026-01"]["asesores"] if a["cedula"] == "100")
    assert (ene["presupuesto"], ene["venta_cumplimiento"], ene["cumplimiento_pct"]) == (600, 600.0, 1.0)
    feb = next(a for a in por_mes["2026-02"]["asesores"] if a["cedula"] == "100")
    assert (feb["presupuesto"], feb["cumplimiento_pct"], feb["semaforo"]) == (0, None, None)
    assert por_mes["2026-03"]["red"]["cumplimiento_pct"] == pytest.approx(2000 / 1900)
    assert por_mes["2026-02"]["red"]["cumplimiento_pct"] == pytest.approx(500 / 700)


# --- Ficha y puestos ---------------------------------------------------------------------------


def test_the_ficha_names_the_asesor_with_the_store_of_the_budget():
    r = _detalle()

    assert r["asesor"] == {
        "cedula": "100", "nombre": "Ana", "cargo": "ASESOR DE REPUESTOS", "tienda": "Norte",
        "sucursal_id": str(NORTE)}


def test_puestos_rank_cumplimiento_of_the_last_month_venta_and_tecnired():
    r = _detalle()

    assert r["puestos"]["cumplimiento"] == {"puesto": 3, "de": 3}  # .7 against Beto 1.0 and Cami 2.0 in March
    assert r["puestos"]["venta"] == {"puesto": 1, "de": 3}
    assert r["puestos"]["tecnired"] == {"puesto": 1, "de": 3}


def test_puestos_share_the_position_on_a_tie_and_skip_the_next():
    beto, cami = _detalle("200")["puestos"], _detalle("300")["puestos"]

    # Nobody but Ana sold to Tecnired: Beto and Cami tie for 2nd of 3.
    assert beto["tecnired"] == cami["tecnired"] == {"puesto": 2, "de": 3}
    assert beto["venta"] == {"puesto": 2, "de": 3} and cami["venta"] == {"puesto": 3, "de": 3}


def test_an_asesor_without_budget_in_the_last_month_has_no_cumplimiento_puesto():
    presupuestos = {k_: v for k_, v in PRESUPUESTOS.items() if k_ != ("2026-03", "100")}

    r = _detalle(presupuestos=presupuestos)

    assert r["puestos"]["cumplimiento"] == {"puesto": None, "de": 2}
    assert r["cumplimiento_mes"]["pct"] is None and r["cumplimiento_mes"]["semaforo"] is None


# --- Cumplimiento del mes y tendencia ------------------------------------------------------------


def test_cumplimiento_mes_is_the_last_month_against_her_own_budget():
    r = _detalle()

    assert r["cumplimiento_mes"] == {
        "mes": "2026-03", "venta": 700.0, "presupuesto": 1000, "pct": pytest.approx(0.7),
        "semaforo": k.AMBAR, "red_pct": pytest.approx(2000 / 1900), "base": t.CUMPLIMIENTO_CON_HMCL}


def test_tendencia_has_one_point_per_month_and_null_where_she_has_no_budget():
    r = _detalle()

    assert [p["mes"] for p in r["tendencia"]] == MESES
    assert [p["pct"] for p in r["tendencia"]] == [pytest.approx(1.0), None, pytest.approx(0.7)]
    assert [p["red_pct"] for p in r["tendencia"]] == [
        pytest.approx(1100 / 1300), pytest.approx(500 / 700), pytest.approx(2000 / 1900)]


# --- Comision ----------------------------------------------------------------------------------


def test_comision_reuses_the_liquidation_of_the_last_month():
    r = _detalle()

    assert r["comision"] == {
        "mes": "2026-03", "tramo": "BASE", "tasa_pct": 1.0, "comision": 7.0, "venta_base": 700.0,
        "base_pago": "sin_hmcl", "presupuesto": 1000, "promedio_red": 394000.0,
        "cumplimiento_pct": 0.7, "gate": {"umbral": 95.0, "cumple": False}, "bono_total": 0, "total_a_pagar": 7.0,
        "bonos": COMISION["asesores"][0]["bonos"],
        "sig": {"tramo": "PRO", "desde_pct": 90.0, "tasa_pct": 1.5, "falta": 200.0, "gana": 3.5, "meta": 900.0},
        "fecha_datos": None, "dias_habiles_restantes": None, "falta_100": 300.0, "venta_diaria_necesaria": None,
        "falta_compuerta": 250, "siguiente_tramo": {"nombre": "PRO", "falta": 200.0, "comision_si_llega": 10.5},
        "venta_hmcl": None,
        "tramos": COMISION["tramos"],
    }


def test_the_days_left_run_from_the_day_after_the_last_sale_to_month_end_without_sundays_and_holidays():
    # Fri 2026-03-20: Sat 21, (Sun 22), (Mon 23 is a holiday), Tue 24 - Sat 28, (Sun 29), Mon 30, Tue 31
    c = _detalle(fecha_datos=datetime.date(2026, 3, 20))["comision"]

    assert c["fecha_datos"] == "2026-03-20" and c["dias_habiles_restantes"] == 8
    assert c["venta_diaria_necesaria"] == 38  # ceil(300 / 8)


def test_no_days_left_means_no_daily_sale_to_ask_for():
    c = _detalle(fecha_datos=datetime.date(2026, 3, 31))["comision"]

    assert c["dias_habiles_restantes"] == 0 and c["venta_diaria_necesaria"] is None and c["falta_100"] == 300.0


def test_nothing_is_missing_for_the_budget_once_it_is_reached():
    c = _detalle(comision=_con_fila(venta_cumplimiento=1200.0), fecha_datos=datetime.date(2026, 3, 20))["comision"]

    assert c["falta_100"] == 0 and c["venta_diaria_necesaria"] is None


def test_the_gate_gap_is_what_the_umbral_asks_over_the_budget_rounded_up():
    assert _detalle(comision=_con_fila(presupuesto=1001))["comision"]["falta_compuerta"] == 251  # ceil(950.95) - 700
    assert _detalle(comision=_con_fila(venta_cumplimiento=990.0))["comision"]["falta_compuerta"] == 0


def test_hmcl_sales_are_the_difference_between_the_two_bases_only_when_they_differ():
    c = _detalle(comision=_con_fila(venta_cumplimiento=900.0))["comision"]

    assert c["venta_hmcl"] == 200.0


def test_comision_is_null_when_the_asesor_is_not_liquidated():
    assert _detalle(comision={**COMISION, "asesores": []})["comision"] is None


def test_the_top_tier_has_no_next_one():
    fila = {**COMISION["asesores"][0], "tramo": "ELITE", "sig": None}

    r = _detalle(comision={**COMISION, "asesores": [fila]})

    assert r["comision"]["sig"] is None and r["comision"]["tramo"] == "ELITE"


# --- Tiles -------------------------------------------------------------------------------------


def _tile(r, nombre):
    return next(x for x in r["tiles"] if x["id"] == nombre)


def test_tiles_compare_volume_with_the_asesores_average_and_ratios_with_the_network():
    r = _detalle()

    assert [x["id"] for x in r["tiles"]] == ["venta", "ticket", "facturas", "clientes_unicos", "margen", "pct_tecnired"]
    assert _tile(r, "venta") == {
        "id": "venta", "valor": 1900.0, "ref": pytest.approx(4200 / 3), "ref_de": "asesores",
        "dif_tipo": "pct", "dif": pytest.approx(1900 / (4200 / 3) - 1)}
    assert _tile(r, "ticket")["valor"] == pytest.approx(190) and _tile(r, "ticket")["ref"] == pytest.approx(100)
    assert _tile(r, "ticket")["ref_de"] == "red"
    assert (_tile(r, "facturas")["valor"], _tile(r, "facturas")["ref"]) == (10, pytest.approx(14))
    assert (_tile(r, "clientes_unicos")["valor"], _tile(r, "clientes_unicos")["ref"]) == (7, pytest.approx(5))
    margen = _tile(r, "margen")
    assert margen["valor"] == pytest.approx(0.3) and margen["ref"] == pytest.approx(920 / 4200)
    assert margen["dif_tipo"] == "pts" and margen["dif"] == pytest.approx(0.3 - 920 / 4200)
    tec = _tile(r, "pct_tecnired")
    assert tec["valor"] == pytest.approx(100 / 1900) and tec["ref"] == pytest.approx(100 / 4200)


# --- Lineas, strip y comparacion -------------------------------------------------------------------


def test_lineas_hold_the_mix_of_the_asesor_and_of_the_network():
    r = _detalle()

    repuestos = next(x for x in r["lineas"] if x["linea"] == "REPUESTOS")
    accesorios = next(x for x in r["lineas"] if x["linea"] == "ACCESORIOS")
    assert repuestos["pct"] == pytest.approx(1800 / 1900) and repuestos["red_pct"] == pytest.approx(4100 / 4200)
    assert accesorios["pct"] == pytest.approx(100 / 1900) and accesorios["red_pct"] == pytest.approx(100 / 4200)
    assert [x["linea"] for x in r["lineas"]] == list(t.LINEAS)


def test_the_strip_has_the_others_the_asesor_and_the_tier_cuts():
    r = _detalle()

    assert sorted(r["strip"]["otros"]) == [pytest.approx(1.0), pytest.approx(2.0)]
    assert r["strip"]["yo"] == pytest.approx(0.7)
    assert r["strip"]["tramos"] == [
        {"nombre": "BASE", "desde_pct": 0.0}, {"nombre": "PRO", "desde_pct": 90.0},
        {"nombre": "ELITE", "desde_pct": 105.0}]


def test_comparacion_averages_her_store_and_the_network():
    r = _detalle()["comparacion"]

    assert r["tienda"] == {"nombre": "Norte", "asesores": 2}
    venta = r["venta_mes"]
    assert venta["yo"] == 700.0 and venta["tienda"] == pytest.approx(600) and venta["red"] == pytest.approx(2000 / 3)
    cump = r["cumplimiento_mes"]
    assert cump["yo"] == pytest.approx(0.7) and cump["tienda"] == pytest.approx(0.85)
    assert cump["red"] == pytest.approx(2000 / 1900)
    # Ratios of her store weigh each asesor by their invoices / sales: (1900 + 1200) / (10 + 12).
    assert r["ticket"]["yo"] == pytest.approx(190) and r["ticket"]["tienda"] == pytest.approx(3100 / 22)
    assert r["ticket"]["red"] == pytest.approx(100)
    assert r["margen"]["tienda"] == pytest.approx((570 + 240) / 3100)
    assert r["pct_tecnired"]["tienda"] == pytest.approx(100 / 3100) and r["pct_tecnired"]["red"] == pytest.approx(100 / 4200)


# --- Tecnired ----------------------------------------------------------------------------------


def test_tecnired_card_has_sales_share_clients_and_the_top_with_nit_as_fallback():
    r = _detalle()["tecnired"]

    assert r["venta"] == 100.0 and r["pct"] == pytest.approx(100 / 1900) and r["red_pct"] == pytest.approx(100 / 4200)
    assert r["clientes"] == 4
    assert r["top"] == [{"cliente": "Taller Uno", "nit": "9001", "venta": 100.0},
                        {"cliente": "9002", "nit": "9002", "venta": 40.0}]


# --- Asesores sin actividad ------------------------------------------------------------------------


def test_an_unknown_cedula_is_none():
    assert _detalle("999") is None


def test_sales_outside_the_store_filter_do_not_put_an_asesor_in_scope():
    # She sold (so cumplimiento knows her: it counts the whole sale) but the tablero, filtered by store, has no
    # row of hers and her budgets are out of the filter.
    tablero, _, _ = _mundo()
    cubo_completo = CUBO + [FilaCubo("P:500", "2026-03", "REPUESTOS", False, False, False, True, D(50), D(50), D(0),
                                     D(1), 1, D(0))]
    cumplimiento = k.construir_cumplimiento(cubo_completo, PRESUPUESTOS, t.REGLAS_POR_DEFECTO, sucursales=SUCURSALES)
    por_mes = k.cumplimiento_por_mes(cubo_completo, PRESUPUESTOS, t.REGLAS_POR_DEFECTO, MESES)

    assert d.construir_detalle("500", tablero, cumplimiento, por_mes, COMISION, 0, [], None, TIENDAS) is None


def test_an_asesor_known_only_by_the_master_has_a_payload_with_empty_numbers():
    maestro = {"nombre": "Dora", "cargo": "ASESOR DE REPUESTOS", "tienda": "Sur", "sucursal_id": str(SUR)}

    r = _detalle("999", comision={**COMISION, "asesores": []}, maestro=maestro, clientes=0, top=[])

    assert r["asesor"]["nombre"] == "Dora" and r["asesor"]["tienda"] == "Sur"
    assert r["puestos"]["venta"] == {"puesto": None, "de": 3}
    assert _tile(r, "venta")["valor"] == 0 and _tile(r, "ticket")["valor"] is None
    assert all(p["pct"] is None for p in r["tendencia"]) and r["comision"] is None
    assert r["tecnired"]["top"] == [] and r["tecnired"]["venta"] == 0.0


# --- Opciones del filtro "Asesor" ---------------------------------------------------------------


def test_the_options_list_who_sold_in_the_period_most_sales_first():
    tablero, _, _ = _mundo()
    maestro = {
        "100": {"nombre": "Ana M.", "tienda": "Norte", "sucursal_id": str(NORTE)},
        "300": {"nombre": "Cami M.", "tienda": "Sur", "sucursal_id": str(SUR)},
    }

    r = d.construir_opciones(tablero, maestro, None)

    assert [(o["cedula"], o["venta"]) for o in r] == [("100", 1900.0), ("200", 1200.0), ("300", 1100.0)]
    assert r[0] == {"cedula": "100", "nombre": "Ana M.", "tienda": "Norte", "sucursal_id": str(NORTE), "venta": 1900.0}
    # Beto is not in the master: the tablero row names him and has no store id.
    assert r[1]["nombre"] == "Beto" and r[1]["tienda"] == "Norte" and r[1]["sucursal_id"] is None


def test_the_options_leave_out_whoever_sold_nothing_in_the_period():
    tablero, _, _ = _mundo(cubo=[c for c in CUBO if c.clave != "P:200"])

    assert [o["cedula"] for o in d.construir_opciones(tablero, {}, None)] == ["100", "300"]


def test_the_options_follow_the_store_of_the_master_like_the_detail_does():
    tablero, _, _ = _mundo()
    maestro = {
        "100": {"nombre": "Ana", "tienda": "Norte", "sucursal_id": str(NORTE)},
        "300": {"nombre": "Cami", "tienda": "Sur", "sucursal_id": str(SUR)},
    }

    assert [o["cedula"] for o in d.construir_opciones(tablero, maestro, {str(SUR)})] == ["200", "300"]
