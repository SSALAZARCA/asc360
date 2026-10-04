"""
KPI's (B4) contra un Postgres real (opt-in): cumplimiento del presupuesto de
punta a punta (ventas + versiones de presupuesto + maestro de vendedores).

El mundo (anio 2097, calculado a mano) tiene dos tiendas, Norte (s1) y Sur (s2):
- Ana (cedula `100.0` en el maestro, presupuesto `100`): ventas ene 1000 + 500 a
  un cliente HMCL, feb 800, mar 900 (sin presupuesto en marzo).
- Beto (cedula `1.200`, presupuesto `1200`): vende ene 400 y feb 600; su
  presupuesto pasa de Sur (enero) a Norte (febrero).
- Cami (cedula 300): solo presupuesto (Sur, enero y marzo), sin ventas.
- Dani (sin cedula, vende 100 en enero) y Eli (cedula 400, vende 50, sin presupuesto).
Presupuestos de enero: la version 1 (Ana 9999) queda anulada por la version 2.
"""
import datetime
import uuid
from decimal import Decimal

import pytest

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401

D = Decimal
MESES = ["2097-01", "2097-02", "2097-03"]


async def _mundo(db):
    sfx = uuid.uuid4().hex[:8].upper()
    prov = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
        dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    norte = Sucursal(id=uuid.uuid4(), nombre=f"Norte {sfx}", sic=f"N-{sfx}")
    sur = Sucursal(id=uuid.uuid4(), nombre=f"Sur {sfx}", sic=f"S-{sfx}")
    db.add_all([prov, norte, sur])
    await db.flush()
    ref = Referencia(
        id=uuid.uuid4(), codigo=f"R-{sfx}", proveedor_id=prov.id, unidad_empaque=1, precio_normal=D("1"),
        linea_comercial="REPUESTOS")
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="APLICADO", nombre_archivo="x.xlsx",
        hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
    db.add_all([ref, carga])
    await db.flush()

    def persona(nombre, cedula, cargo="ASESOR DE REPUESTOS"):
        v = Vendedor(
            id=uuid.uuid4(), nombre=f"{nombre} {sfx}", nombre_norm=normalizar_vendedor(f"{nombre} {sfx}"),
            cargo=cargo, cedula=cedula, activo=True)
        db.add(v)
        return v

    for nombre, cedula in [("Ana", "100.0"), ("Beto", "1.200"), ("Cami", "300"), ("Dani", None), ("Eli", "400")]:
        persona(nombre, cedula)

    def venta(vend, nro, mes, monto, tienda, cliente="Taller X"):
        nombre = f"{vend} {sfx}"
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=datetime.date(2097, mes, 5), anio=2097, mes=mes,
            sucursal_id=tienda.id, referencia_id=ref.id, origen="MOSTRADOR", cantidad=D(1),
            vendedor=nombre, vendedor_norm=normalizar_vendedor(nombre), valor_bruto=D(monto),
            valor_descuentos=D(0), cliente_factura=cliente, nro_documento=f"{nro}-{sfx}"))

    venta("Ana", "A1", 1, 1000, norte)
    venta("Ana", "A2", 1, 500, norte, cliente="900723988")  # HMCL
    venta("Ana", "A3", 2, 800, norte)
    venta("Ana", "A4", 3, 900, norte)
    venta("Beto", "B1", 1, 400, sur)
    venta("Beto", "B2", 2, 600, sur)  # sells at Sur, but his February budget belongs to Norte
    venta("Dani", "D1", 1, 100, norte)
    venta("Eli", "E1", 1, 50, norte)

    def version(mes, numero, lineas):
        v = PresupuestoVersion(id=uuid.uuid4(), mes=datetime.date(2097, mes, 1), version=numero, origen="MANUAL")
        db.add(v)
        return v, lineas

    for v, lineas in [
        version(1, 1, [("100", norte, 9999)]),
        version(1, 2, [("100", norte, 1200), ("1200", sur, 800), ("300", sur, 300)]),
        version(2, 1, [("100", norte, 1000), ("1200", norte, 500)]),
        version(3, 1, [("300", sur, 300)]),
    ]:
        await db.flush()
        db.add_all([
            PresupuestoLinea(id=uuid.uuid4(), version_id=v.id, cedula=ced, sucursal_id=tienda.id, monto=monto)
            for ced, tienda, monto in lineas])
    await db.flush()
    return sfx, norte, sur


async def _filtro(db, base=None, sucursales=None, meses=MESES):
    filtro = await q.cargar_filtro(db, meses, "incluir", sucursales)
    if base:
        filtro = filtro._replace(reglas=filtro.reglas._replace(cumplimiento_base=base))
    return filtro


def _asesor(resultado, cedula):
    return next(f for f in resultado["cumplimiento"]["asesores"] if f["cedula"] == cedula)


async def test_cumplimiento_de_asesores_con_base_con_hmcl(sesion):
    sfx, norte, sur = await _mundo(sesion)

    r = await k.calcular_kpis_asesores(sesion, await _filtro(sesion))

    ana = _asesor(r, "100")
    # Months with budget are Jan and Feb: 1500 + 800 over 1200 (latest version) + 1000; March (900) is left out.
    assert (ana["presupuesto"], ana["venta_cumplimiento"], ana["meses_con_presupuesto"]) == (2200, 2300.0, 2)
    assert ana["cumplimiento_pct"] == pytest.approx(2300 / 2200) and ana["estado"] == k.CUMPLE
    assert ana["nombre"] == f"Ana {sfx}" and ana["clave"].startswith("P:") and ana["sucursal_id"] == str(norte.id)
    beto = _asesor(r, "1200")
    assert (beto["presupuesto"], beto["venta_cumplimiento"]) == (1300, 1000.0)
    assert beto["cumplimiento_pct"] == pytest.approx(1000 / 1300) and beto["semaforo"] == k.AMBAR
    assert beto["sucursal_id"] == str(norte.id)  # the store of his latest budget month


async def test_el_asesor_con_presupuesto_sin_ventas_y_el_que_no_tiene_presupuesto(sesion):
    sfx, _, sur = await _mundo(sesion)

    r = await k.calcular_kpis_asesores(sesion, await _filtro(sesion))

    cami = _asesor(r, "300")
    assert (cami["nombre"], cami["venta_cumplimiento"], cami["presupuesto"]) == (f"Cami {sfx}", 0.0, 600)
    assert (cami["cumplimiento_pct"], cami["semaforo"], cami["meses_con_presupuesto"]) == (0.0, k.VIOLETA, 2)
    eli = _asesor(r, "400")
    assert (eli["estado"], eli["cumplimiento_pct"], eli["nombre"]) == (k.SIN_PRESUPUESTO, None, f"Eli {sfx}")
    dani = next(f for f in r["cumplimiento"]["asesores"] if f["cedula"] is None)
    assert (dani["estado"], dani["nombre"]) == (k.SIN_PRESUPUESTO, f"Dani {sfx}")
    assert r["cumplimiento"]["advertencias"] == {"personas_sin_cedula": 1, "venta_sin_cedula": 100.0}
    assert r["cumplimiento"]["conteos"]["asesores"] == {
        k.VERDE: 1, k.AMBAR: 1, k.VIOLETA: 1, k.SIN_PRESUPUESTO: 2}
    assert r["filas"] and r["total"]["venta"]["total"] > 0  # the tablero stays in the response


async def test_la_cedula_con_puntos_o_decimal_del_maestro_cruza_con_el_presupuesto(sesion):
    await _mundo(sesion)

    r = await k.calcular_kpis_asesores(sesion, await _filtro(sesion, meses=["2097-01"]))

    assert _asesor(r, "100")["venta_cumplimiento"] == 1500.0  # "100.0" in the master, "100" in the budget
    assert _asesor(r, "1200")["venta_cumplimiento"] == 400.0  # "1.200" in the master, "1200" in the budget
    assert _asesor(r, "100")["presupuesto"] == 1200  # version 2 replaces version 1 (9999)


async def test_con_base_sin_hmcl_se_descuenta_la_venta_hmcl_aunque_el_modo_sea_incluir(sesion):
    await _mundo(sesion)

    r = await k.calcular_kpis_asesores(sesion, await _filtro(sesion, base=t.CUMPLIMIENTO_SIN_HMCL))

    ana = _asesor(r, "100")
    assert ana["venta_cumplimiento"] == 1800.0 and ana["semaforo"] == k.AMBAR  # 1000 + 800 over 2200 = 81.8 %


async def test_el_modo_hmcl_excluir_no_cambia_el_cumplimiento_con_hmcl(sesion):
    await _mundo(sesion)
    filtro = (await _filtro(sesion))._replace(modo_hmcl=t.HMCL_EXCLUIR)

    r = await k.calcular_kpis_asesores(sesion, filtro)

    assert _asesor(r, "100")["venta_cumplimiento"] == 2300.0  # still counts the HMCL line
    ana_fila = next(f for f in r["filas"] if f["nombre"].startswith("Ana"))
    assert ana_fila["venta"]["hmcl"] == 0.0  # while the tablero honors the mode


async def test_cumplimiento_por_tienda_con_un_asesor_reasignado_entre_tiendas(sesion):
    _, norte, sur = await _mundo(sesion)

    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion))

    por_id = {f["sucursal_id"]: f for f in r["cumplimiento"]["tiendas"]}
    n, s = por_id[str(norte.id)], por_id[str(sur.id)]
    # Norte: Ana Jan 1200 + Ana Feb 1000 + Beto Feb 500; sales credited per month by the budget store.
    assert (n["presupuesto"], n["venta_cumplimiento"]) == (2700, 1500.0 + 800.0 + 600.0)
    assert n["cumplimiento_pct"] == pytest.approx(2900 / 2700) and n["cumple"] is True
    # Sur: Beto Jan 800 + Cami Jan 300 + Cami Mar 300; only Beto's January sales (400).
    assert (s["presupuesto"], s["venta_cumplimiento"], s["semaforo"]) == (1400, 400.0, k.VIOLETA)
    assert (n["asesores_con_presupuesto"], s["asesores_con_presupuesto"]) == (2, 2)
    red = r["cumplimiento"]["red"]
    assert (red["presupuesto"], red["venta_cumplimiento"]) == (4100, 3300.0)
    assert red["semaforo"] == k.AMBAR and r["cumplimiento"]["conteos"]["tiendas"] == {
        k.VERDE: 1, k.AMBAR: 0, k.VIOLETA: 1}
    fila_norte = next(f for f in r["tiendas"] if f["sucursal_id"] == str(norte.id))
    assert fila_norte["cumplimiento"] == n and fila_norte["venta"]["total"] > 0


async def test_una_tienda_con_presupuesto_y_sin_ventas_aparece_en_el_cumplimiento(sesion):
    _, norte, sur = await _mundo(sesion)

    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion, meses=["2097-03"]))

    ids_con_ventas = {f["sucursal_id"] for f in r["tiendas"]}
    assert ids_con_ventas == {str(norte.id)}  # nobody at Sur sold in March
    sur_cumplimiento = next(f for f in r["cumplimiento"]["tiendas"] if f["sucursal_id"] == str(sur.id))
    assert (sur_cumplimiento["presupuesto"], sur_cumplimiento["venta_cumplimiento"]) == (300, 0.0)
    assert sur_cumplimiento["cumplimiento_pct"] == 0.0


async def test_el_filtro_de_tiendas_acota_los_presupuestos_y_no_la_venta_del_asesor(sesion):
    _, norte, sur = await _mundo(sesion)

    r = await k.calcular_kpis_asesores(sesion, await _filtro(sesion, sucursales=[sur.id]))

    cedulas = {f["cedula"] for f in r["cumplimiento"]["asesores"] if f["presupuesto"]}
    assert cedulas == {"1200", "300"}  # only budgets assigned to Sur: Beto (January) and Cami
    beto = _asesor(r, "1200")
    assert (beto["presupuesto"], beto["venta_cumplimiento"]) == (800, 400.0)
    assert set(r["cumplimiento"]) == {"asesores", "conteos", "advertencias"}  # the asesores view trims the block


async def test_la_pestana_ventas_trae_el_medidor_de_la_red_y_las_tiendas(sesion):
    _, norte, sur = await _mundo(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion))

    c = r["cumplimiento"]
    assert set(c) == {"red", "tiendas", "conteos"}
    assert (c["red"]["presupuesto"], c["red"]["venta_cumplimiento"]) == (4100, 3300.0)
    assert {f["sucursal_id"] for f in c["tiendas"]} == {str(norte.id), str(sur.id)}
