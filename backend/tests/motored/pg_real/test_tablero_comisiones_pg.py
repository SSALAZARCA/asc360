"""
KPI's, pestana Comisiones, contra un Postgres real (opt-in): ventas + presupuestos + maestro de
vendedores + reglas de Configuracion de punta a punta.

Mundo de `test_tablero_kpis_cumplimiento_pg` (anio 2097, Norte y Sur), periodo enero-febrero, mes
liquidado febrero. Con las reglas por defecto (BASE 1 %, PRO 90 % -> 1,5 %, ELITE 105 % -> 1,8 %;
comision sobre la venta sin HMCL, cumplimiento con HMCL), calculado a mano:
- Febrero: Ana 800 / 1000 = 80 % (BASE) -> 800 * 1 % = 8; Beto 600 / 500 = 120 % (ELITE) -> 600 * 1,8 % = 10,8.
  Total 18,8 sobre una base de 1400. Ana esta a 10 puntos de PRO: le faltan 100 y ganaria 5,5.
- Enero: Ana 1500 / 1200 = 125 % (ELITE) -> base sin HMCL 1000 * 1,8 % = 18; Beto 400 / 800 (BASE) -> 4;
  Cami (presupuesto, sin ventas) 0. Total 22 sobre una base de 1400. Enero solo se liquida si es el ultimo mes.
"""
import datetime
import uuid

from app.config import settings
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import kpi_resumen as resumen
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401
from tests.motored.pg_real.test_tablero_kpis_cumplimiento_pg import _mundo

MESES = ["2097-01", "2097-02"]


async def _calcular(db, sucursales=None, modo="incluir", meses=MESES):
    return await k.calcular_kpis_comisiones(db, await q.cargar_filtro(db, meses, modo, sucursales))


async def test_the_settled_month_is_the_last_one_and_matches_the_hand_calculation(sesion):
    sfx, _, _ = await _mundo(sesion)

    r = await _calcular(sesion)

    assert r["mes_liquidado"] == "2097-02" and r["usando_resumen"] is False
    assert [(a["cedula"], a["tramo"], a["comision"]) for a in r["asesores"]] == [
        ("1200", "ELITE", 10.8), ("100", "BASE", 8.0)]
    beto = r["asesores"][0]
    assert (beto["nombre"], beto["tienda"], beto["presupuesto"], beto["venta_comision"]) == (
        f"Beto {sfx}", f"Norte {sfx}", 500, 600.0)
    assert beto["cargo"] == "ASESOR DE REPUESTOS"
    assert r["resumen"]["comision_total"] == 18.8 and r["resumen"]["venta_base"] == 1400.0
    assert [(x["nombre"], x["asesores"]) for x in r["tramos"]] == [("BASE", 1), ("PRO", 0), ("ELITE", 1)]
    assert [(f["cedula"], f["falta"], f["gana"]) for f in r["cerca_de_subir"]] == [("100", 100.0, 5.5)]
    assert r["reglas"]["comision_tramos"][1] == {"nombre": "PRO", "desde_pct": 90.0, "tasa_pct": 1.5}
    assert r["reglas"]["vigencia"] == "2097-02" and r["advertencias"]["sin_presupuesto"] == []


async def test_the_rules_in_force_at_the_settled_month_apply(sesion):
    await _mundo(sesion)
    sesion.add_all([
        ParametroMetodologia(
            id=uuid.uuid4(), clave="comision_tramos", vigente_desde=datetime.date(2097, 2, 1),
            valor=[{"nombre": "UNICO", "desde_pct": 0, "tasa_pct": 2.0}]),
        ParametroMetodologia(  # starts after the settled month: must not apply
            id=uuid.uuid4(), clave="comision_base_pago", vigente_desde=datetime.date(2097, 3, 1),
            valor="con_hmcl"),
    ])
    await sesion.flush()

    r = await _calcular(sesion)

    # A flat 2 % over the sin-HMCL base: 800 * 2 % + 600 * 2 % = 28.
    assert r["resumen"]["comision_total"] == 28.0 and [x["nombre"] for x in r["tramos"]] == ["UNICO"]
    assert r["reglas"]["comision_base_pago"] == "sin_hmcl"


async def test_the_period_does_not_change_the_settled_month(sesion):
    await _mundo(sesion)

    largo, corto = await _calcular(sesion), await _calcular(sesion, meses=["2097-02"])

    for clave in ("mes_liquidado", "reglas", "asesores", "resumen", "tramos", "cerca_de_subir", "advertencias"):
        assert largo[clave] == corto[clave]


async def test_the_store_filter_limits_the_budgets_and_keeps_the_full_sales(sesion):
    _, norte, sur = await _mundo(sesion)

    solo_sur = await _calcular(sesion, [sur.id])
    solo_norte = await _calcular(sesion, [norte.id])

    # February budgets are both at Norte; Beto sold at Sur but is measured at his budget store.
    assert solo_sur["asesores"] == [] and solo_sur["advertencias"]["sin_presupuestos"] is True
    assert solo_norte["resumen"]["comision_total"] == 18.8


async def test_the_hmcl_selector_does_not_change_the_bases(sesion):
    await _mundo(sesion)

    incluir, solo = await _calcular(sesion), await _calcular(sesion, modo="solo")

    for clave in ("asesores", "resumen", "tramos", "cerca_de_subir"):
        assert incluir[clave] == solo[clave]


async def test_an_asesor_that_sold_without_budget_is_a_warning_not_a_commission(sesion):
    sfx, _, _ = await _mundo(sesion)

    r = await _calcular(sesion, meses=["2097-01"])

    # January: Eli sold 50 with no budget; Dani sold 100 with no cedula.
    assert r["advertencias"]["sin_presupuesto"] == [{"cedula": "400", "nombre": f"Eli {sfx}", "venta": 50.0}]
    assert r["advertencias"]["sin_cedula"] == {"personas": 1, "venta": 100.0}
    assert [a["cedula"] for a in r["asesores"]] == ["100", "1200", "300"]  # Ana 18, Beto 4, Cami 0


async def test_the_summary_switch_gives_the_same_answer(sesion, monkeypatch):
    await _mundo(sesion)
    await resumen.reconstruir_todo(sesion)
    casos = [(None, "incluir", MESES), (None, "excluir", ["2097-01", "2097-02", "2097-03"]), (None, "incluir", ["2097-02"])]

    for sucursales, modo, meses in casos:
        monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
        en_vivo = await _calcular(sesion, sucursales, modo, meses)
        monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
        assert await lectura.usar_resumen(sesion)
        desde_resumen = await _calcular(sesion, sucursales, modo, meses)

        assert desde_resumen.pop("usando_resumen") is True and en_vivo.pop("usando_resumen") is False
        desde_resumen.pop("datos_actualizados_en"), en_vivo.pop("datos_actualizados_en")
        assert desde_resumen == en_vivo
