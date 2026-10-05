"""
KPI's (B5) against a real Postgres (opt-in): distinct Tecnired clients, the
top-5 Tecnired clients with `razon_social`, and inventory days per store.

World (year 2097, inventory cut-off in 2099). Tecnired sales (all REPUESTOS, qty 1
unless noted): T1 s1 01=1000, s1 02=500, s2 03=200 (written with a trailing dot);
T2 s2 02=300 (no razon_social); T3 s1 03=100; T4 s1 04=90 (qty 2); T5 s2 04=80;
T6 s1 05=70 (qty 3); T7 s2 06=60. Not counted: T8 in an ANULADA load, T9 on an
unrecognized line, T10 in month 07. A non-Tecnired client buys 1000 of ACCESORIOS
(no cost) in s1 month 05.
Cost per reference (median of the positive costs of the latest cut-off): R1 = 200
(100, 300 and 200), R2 = none. Cost of sales, months 04..06 (91 days): s1 = (2 + 3)
x 200 = 1000, s2 = (1 + 1) x 200 = 400. Inventory at cost: s1 = 10x100 + 5x300 = 2500
(+2 lines without cost), s2 = 20x200 = 4000, s3 = nothing with cost (+1 line without).
"""
import datetime
import uuid
from decimal import Decimal

import pytest

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.test_tablero_asesores_pg import URL, _carga, pytestmark, sesion  # noqa: F401

D = Decimal
CORTE = datetime.date(2099, 12, 29)
MESES = [f"2097-0{m}" for m in range(1, 7)]


class Mundo:
    pass


async def _mundo(db, con_inventario=True):
    w, sfx = Mundo(), uuid.uuid4().hex[:6].upper()
    prov = Proveedor(id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
                     dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
    w.s = [Sucursal(id=uuid.uuid4(), nombre=f"S{i} {sfx}", sic=f"S{i}-{sfx}") for i in (1, 2, 3)]
    db.add_all([prov, *w.s])
    await db.flush()
    refs = {c: Referencia(id=uuid.uuid4(), codigo=f"{c}-{sfx}", proveedor_id=prov.id, unidad_empaque=1,
                          precio_normal=None, linea_comercial=lin)
            for c, lin in (("R1", "REPUESTOS"), ("R2", "ACCESORIOS"), ("R3", "NO APLICA"))}
    db.add_all(refs.values())
    c_venta, c_anulada = _carga("VENTAS", "APLICADO"), _carga("VENTAS", "ANULADO")
    c_inv, c_inv_anulada = _carga("INVENTARIO", "APLICADO"), _carga("INVENTARIO", "ANULADO")
    db.add_all([c_venta, c_anulada, c_inv, c_inv_anulada])
    await db.flush()
    nits = {f"T{i}": "7" + str(uuid.uuid4().int)[:8] for i in range(1, 11)}
    w.nits = nits
    for clave, nit in nits.items():
        db.add(ClienteTecnired(id=uuid.uuid4(), nit=nit, razon_social=None if clave == "T2" else f"Taller {clave}"))
    ventas = [
        ("T1", 0, "R1", 1, 1, 1000, ""), ("T1", 0, "R1", 2, 1, 500, ""), ("T1", 1, "R1", 3, 1, 200, "."),
        ("T2", 1, "R1", 2, 1, 300, ""), ("T3", 0, "R1", 3, 1, 100, ""), ("T4", 0, "R1", 4, 2, 90, ""),
        ("T5", 1, "R1", 4, 1, 80, ""), ("T6", 0, "R1", 5, 3, 70, ""), ("T7", 1, "R1", 6, 1, 60, ""),
        ("T9", 0, "R3", 2, 1, 999, ""), ("T10", 0, "R1", 7, 1, 888, ""),
    ]
    for cliente, suc, ref, mes, cant, valor, sufijo in ventas:
        _venta(db, w, c_venta, nits[cliente] + sufijo, suc, refs[ref], mes, cant, valor)
    _venta(db, w, c_anulada, nits["T8"], 0, refs["R1"], 2, 1, 777)
    _venta(db, w, c_venta, "Taller X", 0, refs["R2"], 5, 5, 1000)
    if con_inventario:
        _inventario(db, w, c_inv, c_inv_anulada, refs)
    await db.flush()
    return w


def _venta(db, w, carga, cliente, suc, ref, mes, cant, valor):
    db.add(VentaDetalle(
        id=uuid.uuid4(), carga_id=carga.id, fecha=datetime.date(2097, mes, 10), anio=2097, mes=mes,
        sucursal_id=w.s[suc].id, referencia_id=ref.id, origen="MOSTRADOR", cantidad=D(cant),
        vendedor="V", vendedor_norm="V", valor_bruto=D(valor), valor_descuentos=D(0), cliente_factura=cliente,
        nro_documento=uuid.uuid4().hex[:10]))


def _inventario(db, w, c_inv, c_anulada, refs):
    def inv(carga, suc, ref, corte, existencia, costo, bodega):
        db.add(InventarioDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha_corte=corte, sucursal_id=w.s[suc].id,
            referencia_id=refs[ref].id, bodega=bodega, existencia=D(existencia),
            costo_unitario=None if costo is None else D(costo)))
    inv(c_inv, 0, "R1", CORTE, 10, 100, "B1"), inv(c_inv, 0, "R1", CORTE, 5, 300, "B2")
    inv(c_inv, 0, "R2", CORTE, 4, None, "B1"), inv(c_inv, 0, "R2", CORTE, 3, 0, "B2")
    inv(c_inv, 1, "R1", CORTE, 20, 200, "B1"), inv(c_inv, 2, "R2", CORTE, 7, None, "B1")
    inv(c_inv, 0, "R1", datetime.date(2099, 12, 1), 1000, 9, "B1")  # older cut-off
    inv(c_anulada, 0, "R1", datetime.date(2099, 12, 30), 1000, 9, "B1")  # annulled load


async def _filtro(db, meses=MESES, modo="incluir", sucursales=None):
    return await q.cargar_filtro(db, meses, modo, sucursales)


async def test_the_distinct_tecnired_clients_follow_the_filter(sesion):
    w = await _mundo(sesion)

    total, por_mes = await qk.consultar_clientes_tecnired(sesion, await _filtro(sesion))
    # T1 buys in 3 months, T8 (annulled), T9 (unrecognized line) and T10 (month 07) do not count.
    assert total == 7
    assert por_mes == {"2097-01": 1, "2097-02": 2, "2097-03": 2, "2097-04": 2, "2097-05": 1, "2097-06": 1}
    assert (await qk.consultar_clientes_tecnired(sesion, await _filtro(sesion, ["2097-01", "2097-03"])))[0] == 2
    por_tienda = await qk.consultar_clientes_tecnired(sesion, await _filtro(sesion, sucursales=[w.s[1].id]))
    assert por_tienda[0] == 4  # T1, T2, T5, T7 sell in s2
    assert (await qk.consultar_clientes_tecnired(sesion, await _filtro(sesion, modo="solo")))[0] == 0


async def test_the_top_5_tecnired_clients_carry_the_razon_social(sesion):
    w = await _mundo(sesion)

    top = await qk.consultar_top_tecnired(sesion, await _filtro(sesion))

    assert [f.nit for f in top] == [w.nits[c] for c in ("T1", "T2", "T3", "T4", "T5")]
    assert [f.venta for f in top] == [D(1700), D(300), D(100), D(90), D(80)]  # T1's trailing dot normalized
    assert top[0].razon_social == "Taller T1" and top[1].razon_social is None
    solo_s2 = await qk.consultar_top_tecnired(sesion, await _filtro(sesion, sucursales=[w.s[1].id]))
    assert [f.venta for f in solo_s2] == [D(300), D(200), D(80), D(60)]


async def test_the_ventas_block_has_the_tecnired_clients_average_and_top(sesion):
    w = await _mundo(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion))

    tec = r["tecnired"]
    assert tec["venta"] == 2400.0 and tec["clientes"] == 7
    assert tec["venta_por_cliente"] == pytest.approx(2400 / 7)
    assert tec["pct"] == pytest.approx(2400 / 3400)
    assert tec["por_mes"]["2097-02"] == {"venta": 800.0, "clientes": 2}
    assert tec["por_linea"]["REPUESTOS"] == 2400.0
    assert [f["nit"] for f in tec["top5"]][:2] == [w.nits["T1"], w.nits["T2"]]
    assert [f["razon_social"] for f in tec["top5"]][:2] == ["Taller T1", w.nits["T2"]]


async def test_the_cost_of_sales_uses_the_last_3_months_and_the_median_cost(sesion):
    w = await _mundo(sesion)

    costo, dias = await qk.consultar_costo_venta(sesion, await _filtro(sesion), CORTE)

    assert dias == 91  # 2097-04, 05 and 06
    assert costo == {str(w.s[0].id): D(1000), str(w.s[1].id): D(400)}  # R2 has no cost: contributes nothing
    corto, _ = await qk.consultar_costo_venta(sesion, await _filtro(sesion, ["2097-02", "2097-06"]), CORTE)
    assert corto == costo  # the window ends at the last selected month, whatever else is selected


async def test_the_inventory_is_valued_at_the_latest_cutoff_and_counts_lines_without_cost(sesion):
    w = await _mundo(sesion)

    filas = {f.sucursal_id: f for f in await qk.consultar_inventario(
        sesion, await _filtro(sesion, sucursales=[s.id for s in w.s]), CORTE)}

    assert {k_: (f.valor, f.sin_costo) for k_, f in filas.items()} == {
        str(w.s[0].id): (D(2500), 2), str(w.s[1].id): (D(4000), 0), str(w.s[2].id): (D(0), 1)}
    solo = await qk.consultar_inventario(sesion, await _filtro(sesion, sucursales=[w.s[0].id]), CORTE)
    assert [f.sucursal_id for f in solo] == [str(w.s[0].id)]


async def test_the_tiendas_block_has_the_inventory_days_per_store(sesion):
    w = await _mundo(sesion)

    # Scoped to this world's stores so rows already in the database cannot change the totals.
    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion, sucursales=[s.id for s in w.s]))

    por_tienda = {f["sucursal_id"]: f for f in r["tiendas"]}
    s1, s2 = por_tienda[str(w.s[0].id)]["dias_inventario"], por_tienda[str(w.s[1].id)]["dias_inventario"]
    assert (s1["valor_inventario"], s1["dias"]) == (2500.0, pytest.approx(227.5))
    assert s1["costo_venta_diario"] == pytest.approx(1000 / 91) and s1["lineas_sin_costo"] == 2
    assert s2["dias"] == pytest.approx(910.0) and s2["fecha_corte"] == "2099-12-29"
    inv = r["inventario"]
    assert inv["fecha_corte"] == "2099-12-29" and inv["dias_ventana"] == 91
    assert inv["red"]["valor_inventario"] == 6500.0 and inv["red"]["dias"] == pytest.approx(6500 * 91 / 1400)
    assert inv["tiendas"][str(w.s[2].id)]["dias"] is None  # store 3: no sales and no costed stock


async def test_without_inventory_loaded_the_days_are_empty(sesion):
    w = await _mundo(sesion, con_inventario=False)

    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion, sucursales=[s.id for s in w.s]))

    assert r["inventario"]["fecha_corte"] is None and r["inventario"]["tiendas"] == {}
    assert all(f["dias_inventario"] is None for f in r["tiendas"])

