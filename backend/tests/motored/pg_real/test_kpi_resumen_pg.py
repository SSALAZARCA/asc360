"""
KPI summary build/refresh (odd/motored-kpis-resumenes, R2) against a real
Postgres (opt-in, database migrated to head).

A small world (2 stores, Jan-Mar 2097, vendors, accented and unrecognized lines,
HMCL / Tecnired / plain clients, an ANULADO carga, multi-line invoices, an
inventory cut with costs, nulls, negatives and a master-price fallback) is built
once per test. The summary rows are compared with aggregates computed in PYTHON
from the same seed tuples (never with the SQL under test). The rebuild covers the
whole database, so every comparison is scoped to the world's two stores.
Every test rolls back.
"""
import asyncio
import datetime
import os
import uuid
from collections import defaultdict
from decimal import Decimal as D

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.kpi_resumen import (
    KpiClienteMes, KpiCostoReferencia, KpiFacturaFirma, KpiInventarioCorte, KpiResumenEstado, KpiVentaMes,
)
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.schemas.cliente_tecnired import normalizar_nit
from app.motored.services import kpi_resumen as k
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2097, 12, 28)
HMCL, HMCL_X, VIEJO_NIT = "900723988", "900883086", "811000111"


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


def _carga(tipo, estado="APLICADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado=estado,
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)


class Mundo:
    """Seed rows kept in Python so the expectations never touch the SQL under test."""

    async def crear(self, db, historico=False):
        sfx = uuid.uuid4().hex[:8].upper()
        self.tec = "7" + str(uuid.uuid4().int)[:8]
        prov = Proveedor(
            id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
            dias_empaque_default=4, dias_transito_default=5, dias_seguridad_default=D("3"))
        self.s1 = Sucursal(id=uuid.uuid4(), nombre=f"Uno {sfx}", sic=f"U-{sfx}")
        self.s2 = Sucursal(id=uuid.uuid4(), nombre=f"Dos {sfx}", sic=f"D-{sfx}")
        db.add_all([prov, self.s1, self.s2])
        await db.flush()
        self.refs = {}
        for clave, linea, precio in [
            ("R1", " repuestos ", None), ("R2", "Accesorios", "10"), ("R3", "Llantas", "80"),
            ("R4", "NO APLICA", None), ("R5", "BATERÍAS", None), ("R6", None, "5"), ("R7", "motos", "7"),
        ]:
            self.refs[clave] = Referencia(
                id=uuid.uuid4(), codigo=f"{clave}-{sfx}", proveedor_id=prov.id, unidad_empaque=1,
                precio_normal=D(precio) if precio else None, linea_comercial=linea)
        db.add_all(self.refs.values())
        self.c_venta, self.c_mar = _carga("VENTAS"), _carga("VENTAS")
        self.c_anulada, self.c_inv = _carga("VENTAS", "ANULADO"), _carga("INVENTARIO")
        self.c_inv_anulada = _carga("INVENTARIO", "ANULADO")
        db.add_all([self.c_venta, self.c_mar, self.c_anulada, self.c_inv, self.c_inv_anulada])
        db.add(ClienteTecnired(id=uuid.uuid4(), nit=self.tec))
        if historico:
            db.add_all([
                ParametroMetodologia(
                    id=uuid.uuid4(), clave="hmcl_nits", valor=[VIEJO_NIT], vigente_desde=datetime.date(2090, 1, 1)),
                ParametroMetodologia(
                    id=uuid.uuid4(), clave="lineas_comerciales", valor=["MOTOS", "REPUESTOS"],
                    vigente_desde=datetime.date(2090, 1, 1)),
            ])
        await db.flush()
        self.historico = historico
        self.lineas = []
        for fila in [
            (self.s1, "R1", "ANA", "Taller X", 1, 5, "A1", 2, 1000, 100, "MOSTRADOR", self.c_venta),
            (self.s1, "R2", "ANA", "Taller X", 1, 5, "A1", 1, 500, 0, "MOSTRADOR", self.c_venta),
            (self.s1, "R3", "ANA", HMCL, 2, 5, "A2", 1, 400, 40, "CRM", self.c_venta),
            (self.s1, "R3", "BETO", f"{self.tec}.", 2, 6, "B1", 3, 900, 90, " mostrador ", self.c_venta),
            (self.s1, "R4", "ANA", "Taller X", 2, 6, "A4", 1, 1000, 200, "MOSTRADOR", self.c_venta),
            (self.s2, "R1", "ANA", "Taller X", 1, 5, "A1", 1, 300, 0, "VENTA", self.c_venta),
            (self.s2, "R5", "CARLA", "900883086.0", 2, 7, "C1", 2, 600, 60, "VENTA", self.c_venta),
            (self.s2, "R6", "SIN MAESTRO", "Cliente Y", 2, 8, "E1", 1, 5000, 0, "VENTA", self.c_venta),
            (self.s1, "R7", "ANA", VIEJO_NIT, 1, 9, "M1", 1, 50, 0, "VENTA", self.c_venta),
            (self.s1, "R1", "FANTASMA", "Taller X", 1, 10, "X1", 1, 99999, 0, "VENTA", self.c_anulada),
            (self.s1, "R1", "ANA", "Taller X", 3, 3, "A7", 1, 10, 0, "VENTA", self.c_mar),
        ]:
            await self.linea(db, *fila)
        await self._inventario(db)
        await db.flush()
        return self

    async def linea(self, db, suc, ref, vend, cli, mes, dia, nro, cant, bruto, desc, origen, carga):
        fila = dict(
            suc=suc.id, ref=ref, vend=vend, cli=cli, fecha=datetime.date(2097, mes, dia), nro=nro, cant=D(cant),
            bruto=D(bruto), desc=D(desc), origen=origen, carga=carga.id, anulada=carga is self.c_anulada)
        self.lineas.append(fila)
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=fila["fecha"], anio=2097, mes=mes, sucursal_id=suc.id,
            referencia_id=self.refs[ref].id, origen=origen, cantidad=fila["cant"], vendedor=vend,
            vendedor_norm=vend, valor_bruto=fila["bruto"], valor_descuentos=fila["desc"],
            cliente_factura=cli, nro_documento=f"{nro}-{self.s1.nombre}"))

    async def _inventario(self, db):
        def inv(carga, suc, ref, costo, exist, corte=CORTE, bodega="B1"):
            db.add(InventarioDetalle(
                id=uuid.uuid4(), carga_id=carga.id, fecha_corte=corte, sucursal_id=suc.id,
                referencia_id=self.refs[ref].id, bodega=bodega, existencia=D(exist),
                costo_unitario=D(costo) if costo is not None else None))

        inv(self.c_inv, self.s1, "R1", "100", 2, bodega="B1")
        inv(self.c_inv, self.s1, "R1", "300", 1, bodega="B2")
        inv(self.c_inv, self.s1, "R1", None, 1, bodega="B3")  # no cost, no master price: uncosted
        inv(self.c_inv, self.s1, "R2", "50", 1)
        inv(self.c_inv, self.s1, "R1", "5000", 1, corte=datetime.date(2097, 12, 1), bodega="B4")  # old cut
        inv(self.c_inv, self.s2, "R3", None, 3)  # master price 80 -> 240
        inv(self.c_inv, self.s2, "R6", "-5", 1)  # negative -> master price 5
        inv(self.c_inv_anulada, self.s1, "R5", "999", 1, corte=datetime.date(2097, 12, 30))
        self.costos = {"R1": (D("200"), "inventario"), "R2": (D("50"), "inventario"), "R3": (D("80"), "maestro"),
                       "R6": (D("5"), "maestro"), "R7": (D("7"), "maestro")}
        self.inventario = {self.s1.id: (D("550"), 1, 0), self.s2.id: (D("245"), 0, 2)}

    # -- expectations, computed in Python -------------------------------------------------------

    def _reglas(self):
        lineas = set(t.LINEAS) | ({"MOTOS"} if self.historico else set())
        nits = {HMCL, HMCL_X} | ({VIEJO_NIT} if self.historico else set())
        return lineas, nits

    def esperado(self, sucursales=None):
        """(venta_mes, firmas, clientes) expected from the seed tuples (ANULADO excluded)."""
        lineas_ok, nits = self._reglas()
        venta, firmas, clientes = {}, defaultdict(int), defaultdict(D)
        facturas = defaultdict(set)
        for f in self.lineas:
            if f["anulada"] or (sucursales and f["suc"] not in sucursales):
                continue
            mes = f["fecha"].replace(day=1)
            raw = self.refs[f["ref"]].linea_comercial
            linea = t.texto_de_linea(raw) if raw else None
            linea = linea if linea in lineas_ok else None
            cliente = normalizar_nit(f["cli"])
            nit = cliente if cliente in nits or cliente == self.tec else None
            costo, fuente = self.costos.get(f["ref"], (None, None))
            llave = (mes, f["suc"], f["vend"], linea, nit, f["origen"].strip().upper() == "MOSTRADOR", costo is not None)
            acc = venta.setdefault(llave, [D(0)] * 4 + [0, D(0), D(0)])
            neto = f["bruto"] - f["desc"]
            total = f["cant"] * costo if costo is not None else D(0)
            for i, v in enumerate((neto, f["bruto"], f["desc"], f["cant"], 1, total,
                                   total if fuente == "maestro" else D(0))):
                acc[i] += v
            facturas[(mes, f["suc"], f["vend"], nit, f["nro"])].update([linea] if linea else [])
            if linea:
                clientes[(mes, f["suc"], f["vend"], cliente, linea)] += neto
        for (mes, suc, vend, nit, _nro), lineas in facturas.items():
            firmas[(mes, suc, vend, nit, tuple(sorted(lineas)))] += 1
        return {k_: tuple(v) for k_, v in venta.items()}, dict(firmas), dict(clientes)


async def _leer(db, sucursales):
    ids = list(sucursales)
    venta = {
        (r.anio_mes, r.sucursal_id, r.vendedor_norm, r.linea_norm, r.nit_especial, r.es_mostrador, r.con_costo):
        (r.venta, r.bruto, r.descuentos, r.cantidad, r.lineas, r.costo, r.costo_estimado)
        for r in (await db.execute(select(KpiVentaMes).where(KpiVentaMes.sucursal_id.in_(ids)))).scalars()}
    firmas = {
        (r.anio_mes, r.sucursal_id, r.vendedor_norm, r.nit_especial, tuple(r.firma)): r.n_facturas
        for r in (await db.execute(select(KpiFacturaFirma).where(KpiFacturaFirma.sucursal_id.in_(ids)))).scalars()}
    clientes = {
        (r.anio_mes, r.sucursal_id, r.vendedor_norm, r.cliente_norm, r.linea_norm): r.venta
        for r in (await db.execute(select(KpiClienteMes).where(KpiClienteMes.sucursal_id.in_(ids)))).scalars()}
    return venta, firmas, clientes


def _ids(mundo):
    return {mundo.s1.id, mundo.s2.id}


async def test_the_full_rebuild_equals_the_raw_aggregates(sesion):
    mundo = await Mundo().crear(sesion)

    await k.reconstruir_todo(sesion)

    esperado = mundo.esperado()
    assert await _leer(sesion, _ids(mundo)) == esperado
    venta = esperado[0]
    mar = (datetime.date(2097, 3, 1), mundo.s1.id, "ANA", "REPUESTOS", None, False, True)
    assert venta[mar][0] == D("10") and venta[mar][5] == D("200")  # master or inventory cost per unit
    hmcl = (datetime.date(2097, 2, 1), mundo.s1.id, "ANA", "LLANTAS", HMCL, False, True)
    assert venta[hmcl][5] == D("80") and venta[hmcl][6] == D("80")  # R3: master price, estimated


async def test_unrecognized_lines_and_nits_collapse_without_configuration_history(sesion):
    mundo = await Mundo().crear(sesion)

    await k.reconstruir_todo(sesion)

    venta, firmas, clientes = await _leer(sesion, _ids(mundo))
    assert (datetime.date(2097, 1, 1), mundo.s1.id, "ANA", None, None, False, True) in venta  # MOTOS -> NULL, plain NIT
    assert not any(llave[3] == "MOTOS" for llave in venta)
    assert not any(c[4] is None for c in clientes)  # only recognized lines in kpi_cliente_mes
    assert (datetime.date(2097, 1, 1), mundo.s1.id, "ANA", None, ()) in {(f[0], f[1], f[2], f[3], f[4]) for f in firmas}


async def test_every_historical_configuration_value_stays_recognized(sesion):
    mundo = await Mundo().crear(sesion, historico=True)

    await k.reconstruir_todo(sesion)

    venta, _firmas, _clientes = await _leer(sesion, _ids(mundo))
    assert (datetime.date(2097, 1, 1), mundo.s1.id, "ANA", "MOTOS", VIEJO_NIT, False, True) in venta
    assert (await _leer(sesion, _ids(mundo))) == mundo.esperado()


async def test_costs_and_inventory_use_the_master_price_as_a_fallback(sesion):
    mundo = await Mundo().crear(sesion)

    await k.reconstruir_todo(sesion)

    costos = {
        r.referencia_id: (r.costo_unitario, r.fuente, r.fecha_corte)
        for r in (await sesion.execute(select(KpiCostoReferencia))).scalars()
        if r.referencia_id in {mundo.refs[c].id for c in mundo.refs}}
    assert costos == {mundo.refs[c].id: (v[0], v[1], CORTE) for c, v in mundo.costos.items()}
    inventario = {
        r.sucursal_id: (r.valor, r.lineas_sin_costo, r.lineas_costo_maestro, r.fecha_corte)
        for r in (await sesion.execute(
            select(KpiInventarioCorte).where(KpiInventarioCorte.sucursal_id.in_(list(_ids(mundo))))))
        .scalars()}
    assert inventario == {s: (v[0], v[1], v[2], CORTE) for s, v in mundo.inventario.items()}


async def test_a_second_rebuild_changes_nothing(sesion):
    mundo = await Mundo().crear(sesion)
    await k.reconstruir_todo(sesion)
    primera = await _leer(sesion, _ids(mundo))

    await k.reconstruir_todo(sesion)

    assert await _leer(sesion, _ids(mundo)) == primera == mundo.esperado()


async def test_refreshing_one_period_only_touches_that_store_and_month(sesion):
    mundo = await Mundo().crear(sesion)
    await k.reconstruir_todo(sesion)
    antes = await _leer(sesion, _ids(mundo))
    ids_antes = {
        r.id: (r.anio_mes, r.sucursal_id) for r in
        (await sesion.execute(select(KpiVentaMes).where(KpiVentaMes.sucursal_id.in_(list(_ids(mundo)))))).scalars()}
    await mundo.linea(sesion, mundo.s1, "R2", "LUIS", "Cliente Z", 3, 9, "N1", 1, 70, 0, "VENTA", mundo.c_mar)
    await mundo.linea(sesion, mundo.s2, "R2", "LUIS", "Cliente Z", 2, 9, "N2", 1, 30, 0, "VENTA", mundo.c_venta)
    await sesion.flush()

    await k.refrescar_periodos(sesion, {(mundo.s1.id, 2097, 3)})

    despues = await _leer(sesion, _ids(mundo))
    mar = datetime.date(2097, 3, 1)
    for tabla_antes, tabla_despues in zip(antes, despues):
        quedan = {k_: v for k_, v in tabla_antes.items() if k_[0] != mar or k_[1] != mundo.s1.id}
        assert {k_: v for k_, v in tabla_despues.items() if k_[0] != mar or k_[1] != mundo.s1.id} == quedan
    # The refreshed period equals the raw aggregates (with the new line) and s2/Feb is still stale.
    esperado = mundo.esperado()
    for i, tabla in enumerate(despues):
        assert {k_: v for k_, v in tabla.items() if k_[0] == mar and k_[1] == mundo.s1.id} == {
            k_: v for k_, v in esperado[i].items() if k_[0] == mar and k_[1] == mundo.s1.id}
    ids_despues = {
        r.id for r in
        (await sesion.execute(select(KpiVentaMes).where(KpiVentaMes.sucursal_id.in_(list(_ids(mundo)))))).scalars()}
    assert {i for i, (m, s) in ids_antes.items() if (m, s) != (mar, mundo.s1.id)} <= ids_despues
    # The s2/Feb line added above is not in the summary until its own period is refreshed.
    assert not any(v[0] == D("30") for k_, v in despues[0].items() if k_[1] == mundo.s2.id and k_[3] == "ACCESORIOS")


async def test_an_annulled_carga_drops_out_when_its_period_is_refreshed(sesion):
    mundo = await Mundo().crear(sesion)
    await k.reconstruir_todo(sesion)
    mar = datetime.date(2097, 3, 1)
    assert any(llave[0] == mar for llave in (await _leer(sesion, _ids(mundo)))[0])

    mundo.c_mar.estado = "ANULADO"
    await sesion.flush()
    await k.refrescar_periodos(sesion, {(mundo.s1.id, 2097, 3)})

    for tabla in await _leer(sesion, _ids(mundo)):
        assert not any(llave[0] == mar for llave in tabla)


async def test_state_row_tracks_dirty_and_the_last_full_rebuild(sesion):
    await Mundo().crear(sesion)
    await sesion.execute(delete(KpiResumenEstado))
    assert await k.estado(sesion) is None

    await k.marcar_sucio(sesion)
    sucio = await k.estado(sesion)
    await k.reconstruir_todo(sesion)
    limpio = await k.estado(sesion)
    await k.marcar_sucio(sesion)

    assert sucio.sucio is True and sucio.ultima_reconstruccion_total is None
    assert limpio.sucio is False and limpio.ultima_reconstruccion_total is not None and limpio.version == 1
    assert limpio.actualizado_en is not None and limpio.reconstruyendo is False
    assert (await k.estado(sesion)).sucio is True


async def test_rebuilding_costs_reprices_the_sales_without_a_full_rebuild(sesion):
    mundo = await Mundo().crear(sesion)
    await k.reconstruir_todo(sesion)
    for fila in (await sesion.execute(
            select(InventarioDetalle).where(InventarioDetalle.referencia_id == mundo.refs["R2"].id))).scalars():
        fila.costo_unitario = D("60")
    await sesion.flush()

    await k.reconstruir_costos(sesion)

    mundo.costos["R2"] = (D("60"), "inventario")
    assert await _leer(sesion, _ids(mundo)) == mundo.esperado()


async def test_the_rebuild_holds_the_advisory_lock_until_the_transaction_ends(sesion):
    await Mundo().crear(sesion)
    await k.reconstruir_todo(sesion)
    otro = create_async_engine(URL)
    try:
        async with AsyncSession(otro) as db2:
            ocupado = (await db2.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": k.LOCK_KEY})).scalar()
        await sesion.rollback()
        async with AsyncSession(otro) as db2:
            libre = (await db2.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": k.LOCK_KEY})).scalar()
    finally:
        await otro.dispose()

    assert ocupado is False and libre is True


async def test_blank_clients_are_kept_like_the_live_query_counts_them(sesion):
    """`cliente_factura` is NOT NULL, but a blank one normalizes to '': the live client count
    treats it as one more client, so the summary keeps it (and never aborts the rebuild)."""
    mundo = await Mundo().crear(sesion)
    await mundo.linea(sesion, mundo.s1, "R1", "ANA", "   ", 1, 11, "B1", 1, 70, 0, "VENTA", mundo.c_venta)
    await sesion.execute(text("UPDATE venta_detalle SET cliente_factura = '' WHERE cliente_factura = '   '"))
    await sesion.flush()

    await k.reconstruir_todo(sesion)

    venta, _firmas, clientes = await _leer(sesion, _ids(mundo))
    ene = datetime.date(2097, 1, 1)
    assert clientes[(ene, mundo.s1.id, "ANA", "", "REPUESTOS")] == D("70")
    assert venta[(ene, mundo.s1.id, "ANA", "REPUESTOS", None, False, True)][0] == D("70")  # blank client's sale counted
    filtro = t.filtro_de_meses(["2097-01", "2097-02", "2097-03"], t.HMCL_INCLUIR, _ids(mundo))
    en_vivo = {f.clave: f.clientes for f in await q.consultar_clientes(sesion, filtro, dimension=t.DIM_TOTAL)}
    assert en_vivo[t.CLAVE_TOTAL] == len({c[3] for c in clientes})


async def test_the_unit_cost_equals_the_live_cost_even_with_a_fractional_median(sesion):
    mundo = await Mundo().crear(sesion)
    for costo, bodega in (("100.01", "B7"), ("100.02", "B8")):
        sesion.add(InventarioDetalle(
            id=uuid.uuid4(), carga_id=mundo.c_inv.id, fecha_corte=CORTE, sucursal_id=mundo.s2.id,
            referencia_id=mundo.refs["R4"].id, bodega=bodega, existencia=D(1), costo_unitario=D(costo)))
    await mundo.linea(sesion, mundo.s2, "R4", "ANA", "Taller X", 1, 12, "Q1", 3, 900, 0, "VENTA", mundo.c_venta)
    await sesion.flush()

    await k.reconstruir_todo(sesion)

    vivo = q._subconsulta_costos(CORTE)
    en_vivo = {r.referencia_id: r.costo_unitario for r in (await sesion.execute(select(vivo))).all()}
    resumen = {
        r.referencia_id: r.costo_unitario for r in (await sesion.execute(
            select(KpiCostoReferencia).where(KpiCostoReferencia.fuente == "inventario"))).scalars()}
    assert resumen == en_vivo and resumen[mundo.refs["R4"].id] == D("100.0150")
    costo = (await sesion.execute(
        select(func.sum(KpiVentaMes.costo)).where(
            KpiVentaMes.sucursal_id == mundo.s2.id, KpiVentaMes.anio_mes == datetime.date(2097, 1, 1),
            KpiVentaMes.linea_norm.is_(None), KpiVentaMes.vendedor_norm == "ANA"))).scalar()
    assert costo == D("300.045000")  # 3 x 100.015 -- no rounding drift in the stored cost


async def test_without_an_inventory_cut_the_master_price_prices_everything(sesion):
    mundo = await Mundo().crear(sesion)
    mundo.c_inv.estado = "ANULADO"
    await sesion.flush()

    await k.reconstruir_todo(sesion)

    hoy = datetime.date.today()
    costos = {
        r.referencia_id: (r.costo_unitario, r.fuente, r.fecha_corte)
        for r in (await sesion.execute(select(KpiCostoReferencia))).scalars()
        if r.referencia_id in {v.id for v in mundo.refs.values()}}
    assert costos == {mundo.refs[c].id: (D(p), "maestro", hoy) for c, p in
                      (("R2", "10"), ("R3", "80"), ("R6", "5"), ("R7", "7"))}
    assert not (await sesion.execute(
        select(KpiInventarioCorte).where(KpiInventarioCorte.sucursal_id.in_(list(_ids(mundo)))))).scalars().all()
    venta = (await _leer(sesion, _ids(mundo)))[0]
    r1 = (datetime.date(2097, 1, 1), mundo.s1.id, "ANA", "REPUESTOS", None, True, False)
    assert venta[r1][5] == D(0) and venta[r1][6] == D(0)  # R1 has no master price: uncosted
    llantas = (datetime.date(2097, 2, 1), mundo.s1.id, "ANA", "LLANTAS", HMCL, False, True)
    assert venta[llantas][5] == D("80") == venta[llantas][6]


async def test_inventory_lines_are_valued_at_cost_then_master_price_else_uncosted(sesion):
    mundo = await Mundo().crear(sesion)
    for ref, costo, bodega in (("R7", "0", "B9"), ("R4", "0", "B9"), ("R2", None, "B10")):
        sesion.add(InventarioDetalle(
            id=uuid.uuid4(), carga_id=mundo.c_inv.id, fecha_corte=CORTE, sucursal_id=mundo.s2.id,
            referencia_id=mundo.refs[ref].id, bodega=bodega, existencia=D(2),
            costo_unitario=D(costo) if costo is not None else None))
    await sesion.flush()

    await k.reconstruir_todo(sesion)

    fila = (await sesion.execute(
        select(KpiInventarioCorte).where(KpiInventarioCorte.sucursal_id == mundo.s2.id))).scalar_one()
    # base 245 (R3 240 + R6 5) + R7 0-cost -> 2 x 7 + R4 uncosted + R2 null -> 2 x 10
    assert (fila.valor, fila.lineas_sin_costo, fila.lineas_costo_maestro) == (D("279"), 1, 4)
