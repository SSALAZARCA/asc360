"""
KPI's, pestana Comisiones, bonos por linea, contra un Postgres real (opt-in): ventas por linea + Tecnired +
presupuestos + reglas de Configuracion de punta a punta, y el detalle del mes de Presupuestos.

Mundo (anio 2097, febrero, una tienda), calculado a mano con las reglas por defecto (compuerta 95 %; LUBRICANTES 21 %
$35.000, CASCOS 6 % $30.000, TECNIRED 6 % $25.000...; tramos BASE 1 / PRO 90 -> 1,5 / ELITE 105 -> 1,8 %; comision
sobre la venta sin HMCL, cumplimiento con HMCL):
- Ana (presupuesto 1.000.000): REPUESTOS 700.000 + LUBRICANTES 200.000 + CASCOS 60.000 (a un cliente Tecnired) y
  LUBRICANTES 100.000 a HMCL. Con HMCL: total 1.060.000 = 106 % (ELITE, 1,8 % de 960.000 = 17.280); LUBRICANTES
  300.000 / 1.060.000 = 28,3 % -> $35.000; CASCOS y TECNIRED 60.000 / 1.060.000 = 5,66 % -> no. Total 52.280.
  Sin HMCL (cumplimiento_base = sin_hmcl): total 960.000 = 96 % (PRO, 14.400); CASCOS y TECNIRED 6,25 % -> $55.000;
  LUBRICANTES 200.000 / 960.000 = 20,8 % -> no. Total 69.400.
- Beto (presupuesto 500.000): REPUESTOS 400.000 + CASCOS 100.000 = 100 % (PRO, 1,5 % de 500.000 = 7.500); CASCOS 20 %
  -> $30.000. Total 37.500.
"""
import datetime
import uuid
from decimal import Decimal

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import kpi_resumen as resumen
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import presupuestos
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.pg_real.codigos_co import codigo_co_unico
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401

D = Decimal
FEBRERO = datetime.date(2097, 2, 1)
HMCL = "900723988"


async def _mundo(db):
    sfx = uuid.uuid4().hex[:8].upper()
    tecnired = str(uuid.uuid4().int)[:10]
    prov = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
        dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    norte = Sucursal(id=uuid.uuid4(), nombre=f"Norte {sfx}", sic=f"N-{sfx}", codigo_co=codigo_co_unico())
    db.add_all([prov, norte, ClienteTecnired(id=uuid.uuid4(), nit=tecnired, razon_social="Tecni")])
    await db.flush()
    refs = {
        linea: Referencia(
            id=uuid.uuid4(), codigo=f"{linea[:3]}-{sfx}", proveedor_id=prov.id, unidad_empaque=1,
            precio_normal=D("1"), linea_comercial=linea)
        for linea in ("REPUESTOS", "LUBRICANTES", "CASCOS")}
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="APLICADO", nombre_archivo="x.xlsx",
        hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
    db.add_all([*refs.values(), carga])
    await db.flush()
    for nombre, cedula in (("Ana", "100"), ("Beto", "200")):
        db.add(Vendedor(
            id=uuid.uuid4(), nombre=f"{nombre} {sfx}", nombre_norm=normalizar_vendedor(f"{nombre} {sfx}"),
            cargo="ASESOR DE REPUESTOS", cedula=cedula, activo=True))

    def venta(vend, nro, linea, monto, cliente="Taller X"):
        nombre = f"{vend} {sfx}"
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=datetime.date(2097, 2, 5), anio=2097, mes=2,
            sucursal_id=norte.id, referencia_id=refs[linea].id, origen="MOSTRADOR", cantidad=D(1),
            vendedor=nombre, vendedor_norm=normalizar_vendedor(nombre), valor_bruto=D(monto),
            valor_descuentos=D(0), cliente_factura=cliente, nro_documento=f"{nro}-{sfx}"))

    venta("Ana", "A1", "REPUESTOS", 700_000)
    venta("Ana", "A2", "LUBRICANTES", 200_000)
    venta("Ana", "A3", "CASCOS", 60_000, cliente=tecnired)
    venta("Ana", "A4", "LUBRICANTES", 100_000, cliente=HMCL)
    venta("Beto", "B1", "REPUESTOS", 400_000)
    venta("Beto", "B2", "CASCOS", 100_000)
    await _presupuesto(db, FEBRERO, 1, norte, {"100": 1_000_000, "200": 500_000})
    return sfx, norte


async def _presupuesto(db, mes, numero, tienda, montos):
    v = PresupuestoVersion(id=uuid.uuid4(), mes=mes, version=numero, origen="MANUAL")
    db.add(v)
    await db.flush()
    db.add_all([
        PresupuestoLinea(id=uuid.uuid4(), version_id=v.id, cedula=ced, sucursal_id=tienda.id, monto=monto)
        for ced, monto in montos.items()])
    await db.flush()


async def _calcular(db, meses=("2097-02",)):
    return await k.calcular_kpis_comisiones(db, await q.cargar_filtro(db, list(meses), "incluir", None))


def _por_cedula(r):
    return {a["cedula"]: a for a in r["asesores"]}


def _pagos(asesor):
    return {b["linea"]: b["bono_pagado"] for b in asesor["bonos"] if b["bono_pagado"]}


async def test_default_rules_pay_the_lines_on_the_hand_calculation(sesion):
    await _mundo(sesion)

    r = await _calcular(sesion)
    ana, beto = _por_cedula(r)["100"], _por_cedula(r)["200"]

    assert ana["gate"] == {"umbral": 95.0, "cumple": True}
    assert _pagos(ana) == {"LUBRICANTES": 35000} and ana["bono_total"] == 35000
    assert (ana["comision"], ana["total_a_pagar"]) == (17280.0, 52280.0)
    assert _pagos(beto) == {"CASCOS": 30000} and (beto["comision"], beto["total_a_pagar"]) == (7500.0, 37500.0)
    cascos = next(b for b in ana["bonos"] if b["linea"] == "CASCOS")
    assert (cascos["venta"], cascos["cumple"]) == (60000.0, False)
    tecnired = next(b for b in ana["bonos"] if b["linea"] == "TECNIRED")
    assert (tecnired["venta"], tecnired["cumple"]) == (60000.0, False)
    assert r["resumen"]["bonos_total"] == 65000.0 and r["resumen"]["total_a_pagar"] == 89780.0
    por_linea = {x["linea"]: (x["ganadores"], x["monto"]) for x in r["resumen"]["por_linea"]}
    assert por_linea["LUBRICANTES"] == (1, 35000.0) and por_linea["CASCOS"] == (1, 30000.0)
    assert por_linea["TECNIRED"] == (0, 0.0)
    assert r["reglas"]["comision_bono_umbral_pct"] == 95.0 and len(r["reglas"]["comision_lineas"]) == 6


async def test_the_rules_in_force_change_what_is_paid(sesion):
    await _mundo(sesion)
    sesion.add_all([
        ParametroMetodologia(
            id=uuid.uuid4(), clave="cumplimiento_base", vigente_desde=FEBRERO, valor="sin_hmcl"),
        ParametroMetodologia(  # starts after the settled month: must not apply
            id=uuid.uuid4(), clave="comision_bono_umbral_pct", vigente_desde=datetime.date(2097, 3, 1),
            valor="120"),
    ])
    await sesion.flush()

    ana = _por_cedula(await _calcular(sesion))["100"]

    assert _pagos(ana) == {"CASCOS": 30000, "TECNIRED": 25000}
    assert (ana["comision"], ana["total_a_pagar"]) == (14400.0, 69400.0)


async def test_an_inactive_line_is_shown_but_not_paid_and_the_threshold_gates_it(sesion):
    await _mundo(sesion)
    sesion.add_all([
        ParametroMetodologia(
            id=uuid.uuid4(), clave="comision_lineas", vigente_desde=FEBRERO,
            valor=[{"linea": "LUBRICANTES", "pct_meta": "21", "bono": "35000", "activo": False},
                   {"linea": "CASCOS", "pct_meta": "6", "bono": "30000", "activo": True}]),
        ParametroMetodologia(
            id=uuid.uuid4(), clave="comision_bono_umbral_pct", vigente_desde=FEBRERO, valor="100"),
    ])
    await sesion.flush()

    r = await _calcular(sesion)
    ana, beto = _por_cedula(r)["100"], _por_cedula(r)["200"]

    lub = ana["bonos"][0]
    assert (lub["cumple"], lub["activo"], lub["bono_pagado"]) == (True, False, 0) and ana["bono_total"] == 0
    assert _pagos(beto) == {"CASCOS": 30000}                      # exactly 100 %: the gate is inclusive
    assert [x["linea"] for x in r["reglas"]["comision_lineas"]] == ["LUBRICANTES", "CASCOS"]


async def test_the_summary_switch_gives_the_same_answer(sesion, monkeypatch):
    await _mundo(sesion)
    await resumen.reconstruir_todo(sesion)

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = await _calcular(sesion)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    desde_resumen = await _calcular(sesion)

    assert desde_resumen.pop("usando_resumen") is True and en_vivo.pop("usando_resumen") is False
    desde_resumen.pop("datos_actualizados_en"), en_vivo.pop("datos_actualizados_en")
    assert desde_resumen == en_vivo
    assert en_vivo["resumen"]["bonos_total"] == 65000.0


# --- Presupuestos month detail -----------------------------------------------------------------


async def test_the_budget_detail_shows_the_minimums_of_the_default_rules(sesion):
    await _mundo(sesion)

    d = await presupuestos.detalle_mes(sesion, FEBRERO)

    assert d["umbral_bono_pct"] == 95.0
    assert [(x["linea"], x["pct_meta"], x["bono"]) for x in d["lineas_bono"]] == [
        ("LUBRICANTES", 21.0, 35000), ("CASCOS", 6.0, 30000), ("ACCESORIOS", 3.0, 25000),
        ("LLANTAS", 1.0, 25000), ("BATERIAS", 1.0, 25000), ("TECNIRED", 6.0, 25000)]
    por_cedula = {x["cedula"]: x["minimos"] for x in d["lineas"]}
    assert por_cedula["100"]["CASCOS"] == 57_000 and por_cedula["200"]["CASCOS"] == 28_500
    assert por_cedula["100"]["LUBRICANTES"] == 199_500 and por_cedula["200"]["LUBRICANTES"] == 99_750
    assert por_cedula["200"]["LLANTAS"] == 4_750
    assert d["totales_minimos"]["CASCOS"] == 85_500 and d["totales_minimos"]["LUBRICANTES"] == 299_250


async def test_the_budget_detail_uses_the_rules_of_that_month(sesion):
    _, norte = await _mundo(sesion)
    marzo = datetime.date(2097, 3, 1)
    await _presupuesto(sesion, marzo, 1, norte, {"100": 1_000_000})
    sesion.add_all([
        ParametroMetodologia(
            id=uuid.uuid4(), clave="comision_lineas", vigente_desde=FEBRERO,
            valor=[{"linea": "CASCOS", "pct_meta": "5", "bono": "30000", "activo": True},
                   {"linea": "LLANTAS", "pct_meta": "1", "bono": "1", "activo": False}]),
        ParametroMetodologia(
            id=uuid.uuid4(), clave="comision_bono_umbral_pct", vigente_desde=FEBRERO, valor="90"),
        ParametroMetodologia(  # March goes back to the defaults
            id=uuid.uuid4(), clave="comision_lineas", vigente_desde=marzo, valor=[
                {"linea": "LUBRICANTES", "pct_meta": "21", "bono": "35000", "activo": True}]),
        ParametroMetodologia(
            id=uuid.uuid4(), clave="comision_bono_umbral_pct", vigente_desde=marzo, valor="95"),
    ])
    await sesion.flush()

    feb = await presupuestos.detalle_mes(sesion, FEBRERO)
    mar = await presupuestos.detalle_mes(sesion, marzo)

    assert [x["linea"] for x in feb["lineas_bono"]] == ["CASCOS"] and feb["umbral_bono_pct"] == 90.0
    assert {x["cedula"]: x["minimos"] for x in feb["lineas"]} == {
        "100": {"CASCOS": 45_000}, "200": {"CASCOS": 22_500}} and feb["totales_minimos"] == {"CASCOS": 67_500}
    assert [x["linea"] for x in mar["lineas_bono"]] == ["LUBRICANTES"] and mar["umbral_bono_pct"] == 95.0
    assert mar["totales_minimos"] == {"LUBRICANTES": 199_500}
