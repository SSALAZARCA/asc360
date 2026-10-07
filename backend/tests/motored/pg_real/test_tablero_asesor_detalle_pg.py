"""
KPI's, Asesores tab, single-asesor detail, against a real Postgres (opt-in).

World (year 2097, computed by hand). Two stores, Norte (s1) and Sur (s2), and four asesores of the master:
- Ana (s1) sells Jan 1000, Feb 600 + 400 (to Tecnired clients T1 and T2), Mar 700. Budgets 1000 / 1000 / 800.
- Beto (s1) sells Jan 500, Feb 300 (to T1), Mar 900. Budgets 500 / 600 / 600.
- Cami (s2) sells Jan 200, Feb 200, Mar 100. Budgets 400 / 200 / 400.
- Dora (s2): in the master only (no sales, no budget).
Every invoice has its own number, so Ana has 4 invoices (ticket 2700 / 4 = 675).
Sales over the period: Ana 2700, Beto 1700, Cami 500; March cumplimiento: Ana 0.875, Beto 1.5, Cami 0.25.
"""
import datetime
import uuid
from decimal import Decimal

import pytest

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import festivos_colombia as festivos
from app.motored.services import kpi_resumen
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.ingesta.ventas import normalizar_vendedor
from tests.motored.pg_real.codigos_co import codigo_co_unico
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401

D = Decimal
MESES = ["2097-01", "2097-02", "2097-03"]


class Mundo:
    async def crear(self, db):
        sfx = self.sfx = uuid.uuid4().hex[:8].upper()
        self.cedulas = {n: str(uuid.uuid4().int)[:10] for n in ("ana", "beto", "cami", "dora")}
        self.t1, self.t2 = "8" + str(uuid.uuid4().int)[:8], "8" + str(uuid.uuid4().int)[:8]
        prov = Proveedor(
            id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
            dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
        self.norte = Sucursal(id=uuid.uuid4(), nombre=f"Norte {sfx}", sic=f"N-{sfx}", codigo_co=codigo_co_unico())
        self.sur = Sucursal(id=uuid.uuid4(), nombre=f"Sur {sfx}", sic=f"S-{sfx}", codigo_co=codigo_co_unico())
        db.add_all([prov, self.norte, self.sur])
        await db.flush()
        ref = self.ref = Referencia(
            id=uuid.uuid4(), codigo=f"R-{sfx}", proveedor_id=prov.id, unidad_empaque=1, precio_normal=D("1"),
            linea_comercial="REPUESTOS")
        carga = self.carga = CargaArchivo(
            id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="APLICADO", nombre_archivo="x.xlsx",
            hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
        db.add_all([
            ref, carga, ClienteTecnired(id=uuid.uuid4(), nit=self.t1, razon_social="Taller Uno"),
            ClienteTecnired(id=uuid.uuid4(), nit=self.t2)])
        for nombre, tienda in [("ana", self.norte), ("beto", self.norte), ("cami", self.sur), ("dora", self.sur)]:
            nom = f"{nombre.title()} {sfx}"
            db.add(Vendedor(
                id=uuid.uuid4(), nombre=nom, nombre_norm=normalizar_vendedor(nom), cargo="ASESOR DE REPUESTOS",
                cedula=self.cedulas[nombre], sucursal_id=tienda.id, activo=True))
        await db.flush()

        def venta(quien, nro, mes, monto, tienda, cliente="Taller X"):
            nom = f"{quien.title()} {sfx}"
            db.add(VentaDetalle(
                id=uuid.uuid4(), carga_id=carga.id, fecha=datetime.date(2097, mes, 5), anio=2097, mes=mes,
                sucursal_id=tienda.id, referencia_id=ref.id, origen="MOSTRADOR", cantidad=D(1), vendedor=nom,
                vendedor_norm=normalizar_vendedor(nom), valor_bruto=D(monto), valor_descuentos=D(0),
                cliente_factura=cliente, nro_documento=f"{nro}-{sfx}"))

        venta("ana", "A1", 1, 1000, self.norte)
        venta("ana", "A2", 2, 600, self.norte, self.t1)
        venta("ana", "A3", 2, 400, self.norte, self.t2)
        venta("ana", "A4", 3, 700, self.norte)
        venta("beto", "B1", 1, 500, self.norte)
        venta("beto", "B2", 2, 300, self.norte, self.t1)
        venta("beto", "B3", 3, 900, self.norte)
        venta("cami", "C1", 1, 200, self.sur)
        venta("cami", "C2", 2, 200, self.sur)
        venta("cami", "C3", 3, 100, self.sur)

        presupuestos = {
            1: [("ana", self.norte, 1000), ("beto", self.norte, 500), ("cami", self.sur, 400)],
            2: [("ana", self.norte, 1000), ("beto", self.norte, 600), ("cami", self.sur, 200)],
            3: [("ana", self.norte, 800), ("beto", self.norte, 600), ("cami", self.sur, 400)],
        }
        for mes, lineas in presupuestos.items():
            version = PresupuestoVersion(id=uuid.uuid4(), mes=datetime.date(2097, mes, 1), version=1, origen="MANUAL")
            db.add(version)
            await db.flush()
            db.add_all([
                PresupuestoLinea(
                    id=uuid.uuid4(), version_id=version.id, cedula=self.cedulas[quien], sucursal_id=tienda.id,
                    monto=monto)
                for quien, tienda, monto in lineas])
        await db.flush()
        return self


async def _detalle(db, mundo, quien, meses=MESES, sucursales=None, modo="incluir"):
    filtro = await q.cargar_filtro(db, meses, modo, sucursales)
    return await k.calcular_kpis_asesor_detalle(db, filtro, mundo.cedulas[quien])


async def test_the_detail_of_ana_matches_the_hand_computed_world(sesion):
    mundo = await Mundo().crear(sesion)

    r = await _detalle(sesion, mundo, "ana")

    assert r["asesor"] == {
        "cedula": mundo.cedulas["ana"], "nombre": f"Ana {mundo.sfx}", "cargo": "ASESOR DE REPUESTOS",
        "tienda": f"Norte {mundo.sfx}", "sucursal_id": str(mundo.norte.id)}
    assert r["puestos"] == {
        "cumplimiento": {"puesto": 2, "de": 3}, "venta": {"puesto": 1, "de": 3}, "tecnired": {"puesto": 1, "de": 3}}
    assert (r["cumplimiento_mes"]["venta"], r["cumplimiento_mes"]["presupuesto"]) == (700.0, 800)
    assert r["cumplimiento_mes"]["pct"] == pytest.approx(0.875) and r["cumplimiento_mes"]["semaforo"] == k.AMBAR
    assert r["cumplimiento_mes"]["red_pct"] == pytest.approx(1700 / 1800)
    assert [p["pct"] for p in r["tendencia"]] == [pytest.approx(1.0), pytest.approx(1.0), pytest.approx(0.875)]
    comision = r["comision"]
    assert (comision["tramo"], comision["comision"], comision["venta_base"]) == ("BASE", 7.0, 700.0)
    assert (comision["sig"]["tramo"], comision["sig"]["falta"], comision["sig"]["meta"]) == ("PRO", 20.0, 720.0)
    assert comision["fecha_datos"] == "2097-03-05"
    assert comision["dias_habiles_restantes"] == festivos.dias_habiles(
        datetime.date(2097, 3, 6), datetime.date(2097, 3, 31))
    assert (comision["falta_100"], comision["falta_compuerta"]) == (100.0, 60)
    assert comision["siguiente_tramo"]["nombre"] == "PRO" and comision["venta_hmcl"] is None
    assert [x["nombre"] for x in comision["tramos"]] == ["BASE", "PRO", "ELITE"]
    assert all(set(x) == {"nombre", "desde_pct", "tasa_pct"} for x in comision["tramos"])
    tiles = {x["id"]: x for x in r["tiles"]}
    assert tiles["venta"]["valor"] == 2700.0 and tiles["venta"]["ref"] == pytest.approx(4900 / 3)
    assert tiles["ticket"]["valor"] == pytest.approx(675) and tiles["facturas"]["valor"] == 4
    assert tiles["clientes_unicos"]["valor"] == 3  # Taller X, T1 and T2
    assert tiles["pct_tecnired"]["valor"] == pytest.approx(1000 / 2700)
    assert r["tecnired"]["clientes"] == 2 and r["tecnired"]["top"] == [
        {"cliente": "Taller Uno", "nit": mundo.t1, "venta": 600.0}, {"cliente": mundo.t2, "nit": mundo.t2, "venta": 400.0}]
    assert sorted(r["strip"]["otros"]) == [pytest.approx(0.25), pytest.approx(1.5)]
    assert r["comparacion"]["tienda"]["asesores"] == 2
    assert r["comparacion"]["venta_mes"]["tienda"] == pytest.approx(800)
    assert r["comparacion"]["cumplimiento_mes"]["tienda"] == pytest.approx((0.875 + 1.5) / 2)


async def test_the_last_sale_date_follows_the_store_filter_and_the_last_month(sesion):
    mundo = await Mundo().crear(sesion)
    nom = f"Dora {mundo.sfx}"
    sesion.add(VentaDetalle(
        id=uuid.uuid4(), carga_id=mundo.carga.id, fecha=datetime.date(2097, 3, 20), anio=2097, mes=3,
        sucursal_id=mundo.sur.id, referencia_id=mundo.ref.id, origen="MOSTRADOR", cantidad=D(1), vendedor=nom,
        vendedor_norm=normalizar_vendedor(nom), valor_bruto=D(50), valor_descuentos=D(0),
        cliente_factura="Taller X", nro_documento=f"D1-{mundo.sfx}"))
    await sesion.flush()

    todas = await _detalle(sesion, mundo, "ana")
    solo_norte = await _detalle(sesion, mundo, "ana", sucursales=[mundo.norte.id])
    solo_febrero = await _detalle(sesion, mundo, "ana", meses=["2097-01", "2097-02"])

    assert todas["comision"]["fecha_datos"] == "2097-03-20"
    assert solo_norte["comision"]["fecha_datos"] == "2097-03-05"
    assert solo_febrero["comision"]["fecha_datos"] == "2097-02-05"


async def test_an_asesor_of_the_master_without_sales_has_an_empty_detail_and_an_unknown_one_is_none(sesion):
    mundo = await Mundo().crear(sesion)

    dora = await _detalle(sesion, mundo, "dora")
    filtro = await q.cargar_filtro(sesion, MESES, "incluir", None)

    assert dora["asesor"]["nombre"] == f"Dora {mundo.sfx}" and dora["asesor"]["tienda"] == f"Sur {mundo.sfx}"
    assert dora["puestos"]["venta"] == {"puesto": None, "de": 3}
    assert dora["tecnired"] == {"venta": 0.0, "pct": None, "red_pct": pytest.approx(1300 / 4900), "clientes": 0, "top": []}
    assert await k.calcular_kpis_asesor_detalle(sesion, filtro, "99999999999") is None


async def test_the_store_filter_limits_what_counts_as_in_scope(sesion):
    mundo = await Mundo().crear(sesion)

    assert await _detalle(sesion, mundo, "ana", sucursales=[mundo.sur.id]) is None
    assert (await _detalle(sesion, mundo, "dora", sucursales=[mundo.sur.id]))["asesor"]["tienda"] == f"Sur {mundo.sfx}"
    cami = await _detalle(sesion, mundo, "cami", sucursales=[mundo.sur.id])
    assert cami["puestos"]["venta"] == {"puesto": 1, "de": 1}


async def _opciones(db, meses=MESES, sucursales=None, modo="incluir"):
    return (await k.calcular_opciones_asesores(db, await q.cargar_filtro(db, meses, modo, sucursales)))["asesores"]


async def test_the_asesor_options_list_who_sold_with_the_most_sales_first(sesion):
    mundo = await Mundo().crear(sesion)
    propias = set(mundo.cedulas.values())

    todas = await _opciones(sesion)
    sur = await _opciones(sesion, sucursales=[mundo.sur.id])

    assert [a["cedula"] for a in todas if a["cedula"] in propias] == [
        mundo.cedulas["ana"], mundo.cedulas["beto"], mundo.cedulas["cami"]]  # Dora sold nothing
    assert [a["cedula"] for a in sur if a["cedula"] in propias] == [mundo.cedulas["cami"]]
    ana = next(a for a in todas if a["cedula"] == mundo.cedulas["ana"])
    assert ana == {
        "cedula": mundo.cedulas["ana"], "nombre": f"Ana {mundo.sfx}", "tienda": f"Norte {mundo.sfx}",
        "sucursal_id": str(mundo.norte.id), "venta": 2700.0}
    assert [a["venta"] for a in todas] == sorted((a["venta"] for a in todas), reverse=True)
    assert [a["cedula"] for a in await _opciones(sesion, meses=["2097-03"]) if a["cedula"] in propias] == [
        mundo.cedulas["beto"], mundo.cedulas["ana"], mundo.cedulas["cami"]]


@pytest.mark.parametrize("modo", [t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO])
async def test_the_asesor_options_are_identical_from_the_summary_and_live(sesion, monkeypatch, modo):
    mundo = await Mundo().crear(sesion)
    await kpi_resumen.reconstruir_todo(sesion)
    casos = [
        (meses, tiendas)
        for meses in (tuple(MESES), ("2097-02",), ("2097-01", "2097-03"))
        for tiendas in (None, (mundo.norte.id,), (mundo.sur.id,))
    ]

    async def todo():
        return {c: await _opciones(sesion, list(c[0]), c[1] and list(c[1]), modo) for c in casos}

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = await todo()
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)

    assert await todo() == en_vivo


@pytest.mark.parametrize("modo", [t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO])
async def test_the_detail_is_identical_from_the_summary_and_live(sesion, monkeypatch, modo):
    mundo = await Mundo().crear(sesion)
    await kpi_resumen.reconstruir_todo(sesion)
    casos = [
        (quien, meses, tiendas)
        for quien in ("ana", "beto", "cami", "dora")
        for meses in (tuple(MESES), ("2097-02",), ("2097-01", "2097-03"))
        for tiendas in (None, (mundo.norte.id,))
    ]

    async def todo():
        return {
            c: _sin_frescura(await _detalle(sesion, mundo, c[0], list(c[1]), c[2] and list(c[2]), modo)) for c in casos}

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = await todo()
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    desde_resumen = await todo()

    assert desde_resumen == en_vivo
    if modo != t.HMCL_SOLO:  # the world has no HMCL client: `solo` leaves nothing to compare
        assert any(v is not None and v["tecnired"]["top"] for v in desde_resumen.values())


def _sin_frescura(r):
    return None if r is None else {k_: v for k_, v in r.items() if k_ not in ("usando_resumen", "datos_actualizados_en")}
