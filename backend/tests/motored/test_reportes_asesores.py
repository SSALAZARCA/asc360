"""
Daily asesor report (odd/motored-reporte-diario-asesor, T2): pure slicing, no database.

Hand-computed world, default commission rules (tiers BASE 0 % / PRO 90 % / ELITE 105 %, gate 95 %,
payment base sin_hmcl, cumplimiento base con_hmcl), month 2026-03, last sale on 2026-03-20:

  Ana  100  budget 1000  sells 700 (CASCOS 70, TECNIRED 40)   -> tier BASE 1 %, commission 7, next PRO
  Beto 200  budget 500   sells 600 (HMCL 100 inside)          -> cumplimiento 120 %, ELITE
  Cami 300  no budget    sells 50
  Dani 400  cargo VENDEDOR (not commissioned), budget 100
"""
import datetime
import uuid
from decimal import Decimal as D

import pytest

from app.motored.models.presupuesto import PresupuestoLinea  # noqa: F401  (keeps the model registry loaded)
from app.motored.services import festivos_colombia as festivos
from app.motored.services import reportes_asesores as r
from app.motored.services import tablero_asesor_detalle as d
from app.motored.services import tablero_comisiones as c
from app.motored.services.presupuestos import LineaPresupuesto

MES = "2026-03"
FECHA_DATOS = datetime.date(2026, 3, 20)
NORTE = uuid.uuid4()
REGLAS = c.reglas_desde_valores({})
CARGO = "ASESOR DE REPUESTOS"
PRESUPUESTOS = {
    "100": LineaPresupuesto(NORTE, 1000), "200": LineaPresupuesto(NORTE, 500), "400": LineaPresupuesto(NORTE, 100),
}
VENTAS = {  # {cedula: (con HMCL, sin HMCL)}
    "100": (D(700), D(700)), "200": (D(600), D(500)), "300": (D(50), D(50)), "400": (D(10), D(10)),
}
POR_LINEA = {
    "100": {"CASCOS": (D(70), D(70)), c.TECNIRED: (D(40), D(40))},
}
NOMBRES = {"100": "Ana", "200": "Beto", "300": "Cami", "400": "Dani"}
CARGOS = {"100": (CARGO,), "200": (CARGO,), "300": (CARGO,), "400": ("VENDEDOR",)}


def _liquidar():
    return c.liquidar_mes(VENTAS, PRESUPUESTOS, NOMBRES, CARGOS, {str(NORTE): "Norte"}, REGLAS, POR_LINEA)


def _armar(sin_cedula=None, nombres_por_clave=None, fecha_datos=FECHA_DATOS):
    asesores, advertencias = _liquidar()
    return r.armar_reportes(
        REGLAS, MES, asesores, advertencias, sin_cedula or {}, nombres_por_clave or {}, fecha_datos)


def test_the_detail_comes_from_the_callback_per_cedula():
    asesores, advertencias = _liquidar()

    resultado = r.armar_reportes(
        REGLAS, MES, asesores, advertencias, {}, {}, FECHA_DATOS, lambda cedula: {"para": cedula})

    assert resultado["reportes"]["100"]["detalle"] == {"para": "100"}
    assert resultado["reportes"]["200"]["detalle"] == {"para": "200"}


def test_slices_one_report_per_commissioned_asesor_with_a_budget():
    resultado = _armar()

    assert set(resultado) == {"reportes", "sin_presupuesto", "sin_cedula"}
    assert set(resultado["reportes"]) == {"100", "200"}


def test_a_report_has_exactly_the_agreed_fields():
    reporte = _armar()["reportes"]["100"]

    assert set(reporte) == {
        "cedula", "nombre", "tienda", "mes", "fecha_datos", "venta_cumplimiento", "venta_comision", "presupuesto",
        "cumplimiento_pct", "tramo", "comision", "bono_total", "total_a_pagar", "siguiente_tramo", "compuerta",
        "falta_100", "dias_habiles_restantes", "venta_diaria_necesaria", "bonos", "tramos", "detalle"}
    assert set(reporte["tramo"]) == {"nombre", "tasa_pct"}
    assert set(reporte["compuerta"]) == {"umbral_pct", "cumple", "falta"}
    assert set(reporte["siguiente_tramo"]) == {"nombre", "falta", "comision_si_llega"}
    assert all(set(b) == {"linea", "etiqueta", "meta_pct", "bono", "activo", "ganado", "pagado", "falta_venta"}
               for b in reporte["bonos"])
    assert all(set(x) == {"nombre", "desde_pct", "tasa_pct"} for x in reporte["tramos"])


def test_the_figures_of_ana_match_the_hand_computed_world():
    reporte = _armar()["reportes"]["100"]
    dias = festivos.dias_habiles(datetime.date(2026, 3, 21), datetime.date(2026, 3, 31))

    assert (reporte["cedula"], reporte["nombre"], reporte["tienda"]) == ("100", "Ana", "Norte")
    assert (reporte["mes"], reporte["fecha_datos"]) == ("2026-03", "2026-03-20")
    assert (reporte["venta_cumplimiento"], reporte["venta_comision"], reporte["presupuesto"]) == (700, 700, 1000)
    assert reporte["cumplimiento_pct"] == pytest.approx(0.7)
    assert reporte["tramo"] == {"nombre": "BASE", "tasa_pct": 1.0}
    assert (reporte["comision"], reporte["bono_total"], reporte["total_a_pagar"]) == (7, 0, 7)
    assert reporte["siguiente_tramo"] == {"nombre": "PRO", "falta": 200, "comision_si_llega": 14}  # 7 + 6.5 = 13.5, half up
    assert reporte["compuerta"] == {"umbral_pct": 95.0, "cumple": False, "falta": 250}
    assert reporte["falta_100"] == 300
    assert reporte["dias_habiles_restantes"] == dias
    assert reporte["venta_diaria_necesaria"] == -(-300 // dias)
    assert [x["nombre"] for x in reporte["tramos"]] == ["BASE", "PRO", "ELITE"]


def test_money_is_whole_pesos_and_percentages_are_fractions():
    reporte = _armar()["reportes"]["200"]

    for campo in ("venta_cumplimiento", "venta_comision", "presupuesto", "comision", "bono_total",
                  "total_a_pagar", "falta_100"):
        assert type(reporte[campo]) is int, campo
    assert reporte["cumplimiento_pct"] == pytest.approx(1.2)
    assert reporte["tramo"]["nombre"] == "ELITE"
    assert (reporte["venta_cumplimiento"], reporte["venta_comision"]) == (600, 500)  # HMCL counts only for cumplimiento
    assert reporte["falta_100"] == 0 and reporte["venta_diaria_necesaria"] is None


def test_bonus_lines_say_earned_paid_and_missing():
    reporte = _armar()["reportes"]["100"]
    cascos = next(b for b in reporte["bonos"] if b["linea"] == "CASCOS")

    # 70 / 700 = 10 % >= 6 % but the gate (95 %) is not met: met, not earned
    assert cascos["ganado"] is False and cascos["pagado"] == 0 and cascos["falta_venta"] == 0
    assert cascos["meta_pct"] == 6.0 and cascos["bono"] == 30000 and cascos["activo"] is True
    lubricantes = next(b for b in reporte["bonos"] if b["linea"] == "LUBRICANTES")
    assert lubricantes["falta_venta"] == 1000 * 95 * 21 // 10000 + 1  # 199.5 half up


def test_without_a_budget_the_asesor_is_listed_apart():
    resultado = _armar()

    assert resultado["sin_presupuesto"] == [{"cedula": "300", "nombre": "Cami", "venta": 50}]
    assert "300" not in resultado["reportes"]


def test_a_cargo_that_earns_no_commission_is_left_out_of_both():
    resultado = _armar()

    assert "400" not in resultado["reportes"]
    assert all(x["cedula"] != "400" for x in resultado["sin_presupuesto"])


def test_sellers_without_a_valid_cedula_are_listed_by_name_and_sale():
    clave = f"P:{uuid.uuid4()}"

    resultado = _armar(sin_cedula={clave: D("123.4"), "P:999": D(5)}, nombres_por_clave={clave: "Eva"})

    assert resultado["sin_cedula"] == [{"vendedor": "Eva", "venta": 123}, {"vendedor": "P:999", "venta": 5}]


def test_a_month_without_loaded_sales_has_no_reports():
    resultado = _armar(fecha_datos=None)

    assert resultado["reportes"] == {}


def test_the_report_equals_the_commission_card_of_the_asesor_detail():
    asesores, _ = _liquidar()
    tramos = c.tramos_con_conteo(asesores, REGLAS)
    comision = {
        "mes_liquidado": MES, "reglas": {"comision_base_pago": REGLAS.base_pago},
        "resumen": {"comision_promedio": 0.0}, "tramos": tramos, "asesores": asesores}

    for cedula in ("100", "200"):
        tarjeta = d._comision(comision, cedula, FECHA_DATOS)
        reporte = _armar()["reportes"][cedula]
        assert reporte["venta_cumplimiento"] == tarjeta["venta_base"] + (
            0 if tarjeta["venta_hmcl"] is None else tarjeta["venta_hmcl"])
        assert reporte["presupuesto"] == tarjeta["presupuesto"]
        assert reporte["cumplimiento_pct"] == tarjeta["cumplimiento_pct"]
        assert reporte["tramo"] == {"nombre": tarjeta["tramo"], "tasa_pct": tarjeta["tasa_pct"]}
        assert reporte["comision"] == round(tarjeta["comision"])
        assert reporte["bono_total"] == tarjeta["bono_total"]
        assert reporte["total_a_pagar"] == round(tarjeta["total_a_pagar"])
        assert reporte["fecha_datos"] == tarjeta["fecha_datos"]
        assert reporte["dias_habiles_restantes"] == tarjeta["dias_habiles_restantes"]
        assert reporte["falta_100"] == tarjeta["falta_100"]
        assert reporte["venta_diaria_necesaria"] == tarjeta["venta_diaria_necesaria"]
        assert reporte["compuerta"]["falta"] == tarjeta["falta_compuerta"]
        assert reporte["compuerta"]["cumple"] == tarjeta["gate"]["cumple"]
        assert reporte["tramos"] == tarjeta["tramos"]
        sig = tarjeta["siguiente_tramo"]
        assert (reporte["siguiente_tramo"] and reporte["siguiente_tramo"]["nombre"]) == (sig and sig["nombre"])
