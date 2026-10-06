"""
Cost fallback to `referencia.precio_normal` in the LIVE KPI queries (odd/motored-
kpis-resumenes, C1) against a real Postgres (opt-in).

Rule: the unit cost of a referencia is the median positive cost of the latest
non-annulled inventory cut; with none, `precio_normal` (> 0); else it has no cost.

World (store s1, 2097-01, inventory cut in 2099): A has inventory cost 100 (and a
master price 999 that must be ignored), B is absent from the inventory (master 40),
C has neither, D is in the inventory with a NULL cost (master 10).
Sales (REPUESTOS): A 1 x 500, B 2 x 300, C 1 x 100, D 3 x 90.
Cost of sales: 1x100 + 2x40 + 3x10 = 210, of which 80 + 30 = 110 is estimated.
Inventory at cost: A 1x100, D 4 x 10 (master), C 1 uncosted -> 140, 1 master line, 1 uncosted.
"""
import datetime
import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.codigos_co import codigo_co_unico
from tests.motored.pg_real.test_tablero_asesores_pg import URL, _carga, pytestmark, sesion  # noqa: F401

CORTE = datetime.date(2099, 12, 29)


class Mundo:
    pass


async def _mundo(db):
    w, sfx = Mundo(), uuid.uuid4().hex[:6].upper()
    prov = Proveedor(id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
                     dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    w.s1 = Sucursal(
        id=uuid.uuid4(), nombre=f"S1 {sfx}", sic=f"S1-{sfx}",
        codigo_co=codigo_co_unico())
    db.add_all([prov, w.s1])
    await db.flush()
    refs = {c: Referencia(id=uuid.uuid4(), codigo=f"{c}-{sfx}", proveedor_id=prov.id, unidad_empaque=1,
                          precio_normal=D(precio) if precio else None, linea_comercial="REPUESTOS")
            for c, precio in (("A", "999"), ("B", "40"), ("C", None), ("D", "10"))}
    db.add_all(refs.values())
    c_venta, c_inv = _carga("VENTAS", "APLICADO"), _carga("INVENTARIO", "APLICADO")
    db.add_all([c_venta, c_inv])
    await db.flush()
    for i, (ref, cant, bruto) in enumerate((("A", 1, 500), ("B", 2, 300), ("C", 1, 100), ("D", 3, 90))):
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=c_venta.id, fecha=datetime.date(2097, 1, 10), anio=2097, mes=1,
            sucursal_id=w.s1.id, referencia_id=refs[ref].id, origen="VENTA", cantidad=D(cant), vendedor="ANA",
            vendedor_norm="ANA", valor_bruto=D(bruto), valor_descuentos=D(0), cliente_factura="Taller X",
            nro_documento=f"F{i}-{sfx}"))
    for ref, costo, existencia, bodega in (("A", "100", 1, "B1"), ("D", None, 4, "B1"), ("C", None, 1, "B1")):
        db.add(InventarioDetalle(
            id=uuid.uuid4(), carga_id=c_inv.id, fecha_corte=CORTE, sucursal_id=w.s1.id,
            referencia_id=refs[ref].id, bodega=bodega, existencia=D(existencia),
            costo_unitario=D(costo) if costo else None))
    await db.flush()
    return w


async def _filtro(db, w, meses=("2097-01",)):
    return await q.cargar_filtro(db, list(meses), t.HMCL_INCLUIR, [w.s1.id])


async def test_the_margin_block_prices_missing_references_with_the_master_price(sesion):
    w = await _mundo(sesion)

    tablero = await q.calcular_tablero(sesion, "2097-01", "2097-01", t.HMCL_INCLUIR, sucursal_ids=[w.s1.id])

    costo = tablero["total"]["costo"]
    assert costo["costo_venta"] == 210.0 and costo["costo_estimado"] == 110.0
    assert costo["pct_costo_estimado"] == pytest.approx(110 / 210)
    assert costo["venta_con_costo"] == 890.0  # C has no cost from either source
    assert costo["pct_venta_con_costo"] == pytest.approx(890 / 990)


async def test_the_cube_carries_the_estimated_part_of_the_cost(sesion):
    w = await _mundo(sesion)

    cubo = await q.consultar_cubo(sesion, await _filtro(sesion, w), CORTE, t.DIM_SUCURSAL)

    assert sum(f.costo for f in cubo) == D("210") and sum(f.costo_estimado for f in cubo) == D("110")
    assert sum(f.venta for f in cubo if f.con_costo) == D("890")


async def test_the_inventory_valuation_falls_back_to_the_master_price(sesion):
    w = await _mundo(sesion)

    (fila,) = await qk.consultar_inventario(sesion, await _filtro(sesion, w), CORTE)

    assert (fila.valor, fila.sin_costo, fila.costo_maestro) == (D("140"), 1, 1)


async def test_the_cost_of_sales_uses_the_same_combined_unit_cost(sesion):
    w = await _mundo(sesion)

    costo, _dias = await qk.consultar_costo_venta(sesion, await _filtro(sesion, w), CORTE)

    assert costo == {str(w.s1.id): D("210")}


async def test_the_inventory_blocks_expose_the_master_priced_lines(sesion):
    w = await _mundo(sesion)

    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion, w))

    tienda = r["inventario"]["tiendas"][str(w.s1.id)]
    assert tienda["lineas_sin_costo"] == 1 and tienda["lineas_costo_maestro"] == 1
    assert r["inventario"]["red"]["lineas_costo_maestro"] == 1
    assert r["tiendas"][0]["costo"]["pct_costo_estimado"] == pytest.approx(110 / 210)


async def test_without_any_cost_source_nothing_is_estimated(sesion):
    w = await _mundo(sesion)
    vendidas = select(VentaDetalle.referencia_id).where(VentaDetalle.sucursal_id == w.s1.id)
    for ref in (await sesion.execute(select(Referencia).where(Referencia.id.in_(vendidas)))).scalars():
        ref.precio_normal = None
    await sesion.flush()

    tablero = await q.calcular_tablero(sesion, "2097-01", "2097-01", t.HMCL_INCLUIR, sucursal_ids=[w.s1.id])

    costo = tablero["total"]["costo"]
    assert costo["costo_venta"] == 100.0 and costo["costo_estimado"] == 0.0 and costo["pct_costo_estimado"] == 0.0
