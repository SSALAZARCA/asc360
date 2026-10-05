"""
KPI's, pestanas Ventas y Tiendas contra un Postgres real (opt-in): el cumplimiento
de la COMPANIA y de las tiendas se mide con la venta total (todos los vendedores).

Sobre el mundo de `test_tablero_kpis_cumplimiento_pg` se agregan ventas de vendedores
que no son asesores con presupuesto:
- RESTO (no esta en el maestro): ene 70 en Sur y abr 5 en Sur.
- COMERCIALES: feb 30 en Sur. OTROS (cargo sin regla): ene 20 en Norte.
- Ana vende 700 en abril, mes sin ningun presupuesto.
Presupuestos: ene 1200 (Ana, Norte) + 800 (Beto, Sur) + 300 (Cami, Sur); feb 1000 (Ana) + 500
(Beto), ambos Norte; mar 300 (Cami, Sur). Total 4100; Norte tiene presupuesto ene-feb y Sur ene y mar.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.motored.models.referencia import Referencia
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_kpis as k
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401
from tests.motored.pg_real.test_tablero_kpis_cumplimiento_pg import _filtro, _mundo

D = Decimal
MESES_CON_ABRIL = ["2097-01", "2097-02", "2097-03", "2097-04"]


async def _mundo_compania(db):
    sfx, norte, sur = await _mundo(db)
    ref = (await db.execute(select(Referencia).where(Referencia.codigo == f"R-{sfx}"))).scalar_one()
    carga_id = (await db.execute(select(VentaDetalle.carga_id).where(VentaDetalle.referencia_id == ref.id))).scalars().first()

    def persona(nombre, cargo):
        db.add(Vendedor(
            id=uuid.uuid4(), nombre=f"{nombre} {sfx}", nombre_norm=normalizar_vendedor(f"{nombre} {sfx}"),
            cargo=cargo, cedula=None, activo=True))

    persona("Coco", "ASESOR COMERCIAL DE SERVICIO POSVENTA")
    persona("Bodo", "BODEGUERO")

    def venta(vend, nro, mes, monto, tienda):
        nombre = f"{vend} {sfx}"
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga_id, fecha=datetime.date(2097, mes, 5), anio=2097, mes=mes,
            sucursal_id=tienda.id, referencia_id=ref.id, origen="MOSTRADOR", cantidad=D(1),
            vendedor=nombre, vendedor_norm=normalizar_vendedor(nombre), valor_bruto=D(monto),
            valor_descuentos=D(0), cliente_factura="Taller X", nro_documento=f"{nro}-{sfx}"))

    venta("Fantasma", "F1", 1, 70, sur)
    venta("Fantasma", "F2", 4, 5, sur)
    venta("Coco", "C1", 2, 30, sur)
    venta("Bodo", "O1", 1, 20, norte)
    venta("Ana", "A5", 4, 700, norte)
    await db.flush()
    return norte, sur


def _grupos(compania):
    return {g["grupo"]: g["venta"] for g in compania["por_grupo"]}


async def test_la_compania_mide_toda_la_venta_contra_todo_el_presupuesto_en_meses_con_presupuesto(sesion):
    await _mundo_compania(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, meses=MESES_CON_ABRIL))

    c = r["cumplimiento"]["compania"]
    # Jan 2140 + Feb 1430 + Mar 900; April (no budget) is out of both sides.
    assert (c["venta"], c["presupuesto"], c["meses_con_presupuesto"]) == (4470.0, 4100, 3)
    assert c["pct"] == pytest.approx(4470 / 4100) and c["semaforo"] == k.VERDE
    assert r["cumplimiento"]["red"]["venta_cumplimiento"] == 3300.0  # asesores with budget only


async def test_la_compania_reparte_la_venta_por_grupo_y_suma_el_medidor(sesion):
    await _mundo_compania(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, meses=MESES_CON_ABRIL))

    c = r["cumplimiento"]["compania"]
    assert _grupos(c) == {
        "Asesores de repuestos": 4350.0, "Comerciales": 30.0, "Otros roles de posventa": 20.0,
        "Resto de compañía": 70.0}
    assert sum(g["venta"] for g in c["por_grupo"]) == c["venta"]
    assert (c["asesores"]["presupuesto"], c["asesores"]["venta_cumplimiento"]) == (4100, 3300.0)


async def test_la_compania_con_base_sin_hmcl_descuenta_la_venta_hmcl(sesion):
    await _mundo_compania(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, base=t.CUMPLIMIENTO_SIN_HMCL))

    assert r["cumplimiento"]["compania"]["venta"] == 3970.0  # the 500 sold to an HMCL client is out


async def test_el_filtro_de_tiendas_acota_la_venta_y_el_presupuesto_de_la_compania(sesion):
    _, sur = await _mundo_compania(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, sucursales=[sur.id], meses=MESES_CON_ABRIL))

    c = r["cumplimiento"]["compania"]
    # Budgets assigned to Sur: Jan 1100 and Mar 300; only Sur sales of those months: Beto 400 + RESTO 70.
    assert (c["venta"], c["presupuesto"], c["meses_con_presupuesto"]) == (470.0, 1400, 2)
    assert _grupos(c)["Resto de compañía"] == 70.0 and _grupos(c)["Comerciales"] == 0.0


async def test_ventas_y_tiendas_miden_la_tienda_con_su_venta_total(sesion):
    norte, sur = await _mundo_compania(sesion)
    filtro = await _filtro(sesion, meses=MESES_CON_ABRIL)

    for r in (await k.calcular_kpis_ventas(sesion, filtro), await k.calcular_kpis_tiendas(sesion, filtro)):
        por_tienda = {f["sucursal_id"]: f for f in r["cumplimiento"]["tiendas"]}
        # Norte (budget Jan-Feb): Jan 1670 + Feb 800 against 2700; Sur (Jan, Mar): Jan 470 against 1400.
        assert (por_tienda[str(norte.id)]["venta_cumplimiento"], por_tienda[str(norte.id)]["presupuesto"]) == (2470.0, 2700)
        assert (por_tienda[str(sur.id)]["venta_cumplimiento"], por_tienda[str(sur.id)]["presupuesto"]) == (470.0, 1400)
        assert r["cumplimiento"]["conteos"]["tiendas"] == {k.VERDE: 1, k.AMBAR: 0, k.VIOLETA: 1}


async def test_la_pestana_asesores_conserva_el_cumplimiento_por_asesor(sesion):
    await _mundo_compania(sesion)

    r = await k.calcular_kpis_asesores(sesion, await _filtro(sesion, meses=MESES_CON_ABRIL))

    assert set(r["cumplimiento"]) == {"asesores", "conteos", "advertencias"}
    ana = next(f for f in r["cumplimiento"]["asesores"] if f["cedula"] == "100")
    assert (ana["presupuesto"], ana["venta_cumplimiento"]) == (2200, 2300.0)
