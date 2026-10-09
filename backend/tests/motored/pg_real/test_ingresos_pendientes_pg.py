"""
Pending invoice ingresos against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`,
database migrated to head; odd/tasks/motored-ingresos-pendientes.md, P1).

One outer transaction rolled back at the end (savepoint sessions), so the
service's `commit()` leaves nothing behind. The database may hold real rows:
the ingreso window starts in 1900 (earlier than any real ingreso, so it is
ours), the invoices are dated 2097 with fresh numbers and stores, and every
assertion looks only at those, never at the totals of the whole database.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.factura_confirmacion_ingreso import (
    FacturaConfirmacionIngreso,
    FacturaConfirmacionIngresoHistorial,
)
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.services import informe_publico as publico
from app.motored.services import ingresos_pendientes as ip
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
HOY = datetime.date(2097, 10, 8)
DESDE = datetime.date(1900, 1, 1)


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        yield async_sessionmaker(
            bind=conexion, class_=AsyncSession, expire_on_commit=False,
            autoflush=False, join_transaction_mode="create_savepoint")
        await transaccion.rollback()
    await motor.dispose()


def _carga(tipo, estado="APLICADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado=estado,
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)


@pytest.fixture
async def mundo(fabrica):
    sfx = uuid.uuid4().hex[:6]
    async with fabrica() as db:
        cali = Sucursal(id=uuid.uuid4(), nombre=f"Cali {sfx}", sic=f"S1-{sfx}",
                        codigo_co=codigo_co_unico())
        pasto = Sucursal(id=uuid.uuid4(), nombre=f"Pasto {sfx}", sic=f"S2-{sfx}",
                         codigo_co=codigo_co_unico())
        db.add_all([cali, pasto])
        await db.flush()
        sur = Sucursal(id=uuid.uuid4(), nombre=f"Cali Sur {sfx}", sic=f"S3-{sfx}",
                       codigo_co=codigo_co_unico(), principal_id=cali.id)
        prov = Proveedor(
            id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
            dias_empaque_default=4, dias_transito_default=5,
            dias_seguridad_default=D("3"))
        db.add_all([sur, prov])
        await db.flush()
        ref = Referencia(id=uuid.uuid4(), codigo=f"R-{sfx}", proveedor_id=prov.id,
                         unidad_empaque=1, precio_normal=None, linea_comercial="X")
        ref2 = Referencia(id=uuid.uuid4(), codigo=f"Q-{sfx}", proveedor_id=prov.id,
                          unidad_empaque=1, precio_normal=None, linea_comercial="X")
        db.add_all([ref, ref2])
        fact, ingr, anulada = (_carga("FACTURAS_PEDIDOS"), _carga("INGRESOS_FACTURAS"),
                               _carga("FACTURAS_PEDIDOS", "ANULADO"))
        ingr_anulado = _carga("INGRESOS_FACTURAS", "ANULADO")
        db.add_all([fact, ingr, anulada, ingr_anulado])
        await db.flush()

        def linea(numero, fecha, cant, valor, suc, carga=fact, prefijo="RH", r=None):
            db.add(FacturaProveedorLinea(
                id=uuid.uuid4(), prefijo_rh=prefijo, numero_rh=numero,
                fecha_factura=fecha, sucursal_id=suc.id, referencia_id=(r or ref).id,
                cantidad=D(cant), valor_total=D(valor), carga_id=carga.id))

        d = datetime.date
        base = 900000000 + int(sfx, 16) % 1000000 * 10
        n = {k: base + i for i, k in enumerate(
            ("pend", "ingresada", "antes", "anulada", "nc", "credit", "multi", "sur", "pasto"))}
        linea(n["pend"], d(2097, 10, 3), 2, 100, cali)
        linea(n["ingresada"], d(2097, 10, 3), 1, 10, cali)
        linea(n["antes"], d(1899, 8, 15), 1, 10, cali)       # before the window
        linea(n["anulada"], d(2097, 10, 3), 1, 10, cali, carga=anulada)
        linea(n["nc"], d(2097, 10, 1), 4, 400, cali)
        linea(n["nc"], d(2097, 10, 2), -1, -100, cali, r=ref2)
        linea(n["credit"], d(2097, 10, 1), 1, 50, cali)
        linea(n["credit"], d(2097, 10, 2), -1, -50, cali, r=ref2)
        linea(n["multi"], d(2097, 10, 6), 1, 1, cali)
        linea(n["multi"], d(2097, 10, 2), 1, 1, cali, r=ref2)
        linea(n["sur"], d(2097, 10, 4), 1, 5, sur)            # rolls up to Cali
        linea(n["pasto"], d(2097, 10, 5), 3, 30, pasto)
        db.add(IngresoFactura(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=n["ingresada"],
            fecha_ingreso=DESDE, valor_neto=D(10), carga_id=ingr.id))
        # An ingreso of an ANULADO carga neither closes nor sets the window.
        db.add(IngresoFactura(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=n["pend"],
            fecha_ingreso=datetime.date(2097, 1, 1), valor_neto=D(1),
            carga_id=ingr_anulado.id))

        cedula = f"7{int(sfx, 16) % 10**8:08d}"
        usuario = Usuario(
            id=uuid.uuid4(), nombre=f"Ana {sfx}", role=MotoredRole.ASESOR_MOSTRADOR,
            activo=True, status="approved", cedula=cedula, cedula_aprobada=True,
            telegram_id=int(str(uuid.uuid4().int)[:9]))
        coord = Usuario(
            id=uuid.uuid4(), nombre=f"Coord {sfx}", role=MotoredRole.COMPRAS,
            activo=True, status="approved", email=f"c{sfx}@x.co", hashed_password="x")
        db.add_all([usuario, coord])
        await db.flush()
        db.add(Vendedor(
            id=uuid.uuid4(), nombre=f"Ana {sfx}", nombre_norm=f"ANA {sfx}".upper(),
            cargo="ASESOR DE REPUESTOS", sucursal_id=sur.id, cedula=cedula,
            usuario_id=usuario.id))
        link = ReporteAsesorLink(
            id=uuid.uuid4(), usuario_id=usuario.id, cedula=cedula,
            token=uuid.uuid4().hex + uuid.uuid4().hex)
        db.add(link)
        await db.commit()

    class M:
        pass
    m = M()
    m.fabrica, m.cali, m.pasto, m.sur, m.n = fabrica, cali, pasto, sur, n
    m.usuario, m.coord, m.token, m.cedula = usuario, coord, link.token, cedula
    return m


async def test_the_rule_on_real_data(mundo):
    async with mundo.fabrica() as db:
        assert await ip.verificable_desde(db) == DESDE
        items = await ip.pendientes(db, hoy=HOY)
    n = mundo.n
    nuestras = set(n.values())
    por_doc = {i["numero_rh"]: i for i in items if i["numero_rh"] in nuestras}
    assert set(por_doc) == {n["pend"], n["nc"], n["multi"], n["sur"], n["pasto"]}
    assert por_doc[n["pend"]]["unidades"] == 2 and por_doc[n["pend"]]["dias"] == 5
    assert por_doc[n["nc"]]["unidades"] == 3 and por_doc[n["nc"]]["valor"] == 300
    assert por_doc[n["multi"]]["fecha"] == datetime.date(2097, 10, 2)
    assert por_doc[n["sur"]]["sucursal_id"] == mundo.cali.id
    fechas = [i["fecha"] for i in items]
    assert fechas == sorted(fechas)  # oldest first, whatever else is loaded


async def test_nothing_verifiable_without_live_ingresos(fabrica):
    async with fabrica() as db:
        # Real ingresos may exist: void them inside this rolled-back transaction.
        await db.execute(update(CargaArchivo).where(
            CargaArchivo.tipo == "INGRESOS_FACTURAS").values(estado="ANULADO"))
        carga = _carga("INGRESOS_FACTURAS", "ANULADO")
        db.add(carga)
        await db.flush()
        db.add(IngresoFactura(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=1,
            fecha_ingreso=HOY, valor_neto=D(1), carga_id=carga.id))
        await db.flush()
        assert await ip.verificable_desde(db) is None
        assert await ip.pendientes(db, hoy=HOY) == []


async def test_confirm_logs_history_and_can_be_corrected(mundo):
    n = mundo.n
    actor = ip.Actor(nombre="Coord", usuario_id=mundo.coord.id)
    async with mundo.fabrica() as db:
        item = await ip.confirmar(db, f"RH {n['pend']}", mundo.cali.id, "NO_HA_LLEGADO", actor, "web")
        assert item["estado"] == "NO_HA_LLEGADO"
        # an associated store id resolves to its principal
        await ip.confirmar(db, f"RH {n['pend']}", mundo.sur.id, "LLEGO", actor, "web")
    async with mundo.fabrica() as db:
        items = {i["numero_rh"]: i for i in await ip.pendientes(db, hoy=HOY)}
        assert items[n["pend"]]["estado"] == "LLEGO"
        assert items[n["pend"]]["confirmado_por"] == "Coord"
        h = await ip.historial(db, ("RH", n["pend"]), mundo.cali.id)
        assert [x["estado"] for x in h] == ["LLEGO", "NO_HA_LLEGADO"]
        assert (await db.execute(select(FacturaConfirmacionIngresoHistorial))).scalars().all()


async def test_confirm_validations(mundo):
    n = mundo.n
    actor = ip.Actor(nombre="Coord")
    async with mundo.fabrica() as db:
        for factura, tienda, estado, codigo in [
            (f"RH {n['ingresada']}", mundo.cali.id, "LLEGO", 409),   # already ingresada
            (f"RH {n['pasto']}", mundo.cali.id, "LLEGO", 409),       # another store's
            (f"RH {n['credit']}", mundo.cali.id, "LLEGO", 409),      # fully credited
            ("xx", mundo.cali.id, "LLEGO", 422),
            (f"RH {n['pend']}", mundo.cali.id, "TAL", 422),
        ]:
            with pytest.raises(ip.PendienteError) as exc:
                await ip.confirmar(db, factura, tienda, estado, actor, "web")
            assert exc.value.status_code == codigo


async def test_public_confirm_and_payload(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        item = await publico.confirmar_pendiente(
            db, mundo.token, mundo.cedula, f"RH {n['sur']}", "LLEGO")
        assert item["sucursal_id"] == mundo.cali.id and item["estado"] == "LLEGO"
        # her store is Cali (via Cali Sur); Pasto's invoice is not hers
        with pytest.raises(publico.InformeError) as exc:
            await publico.confirmar_pendiente(
                db, mundo.token, mundo.cedula, f"RH {n['pasto']}", "LLEGO")
        assert exc.value.status_code == 409
        with pytest.raises(publico.InformeError) as exc:
            await publico.confirmar_pendiente(
                db, mundo.token, "00000", f"RH {n['pend']}", "LLEGO")
        assert exc.value.status_code == 401
    async with mundo.fabrica() as db:
        h = await ip.historial(db, ("RH", n["sur"]), mundo.cali.id)
        assert h[0]["canal"] == "link" and h[0]["por"].startswith("Ana")
        bloque = await ip.para_asesor(db, await ip.tiendas_de_asesor(db, None, mundo.cedula))
    assert bloque["verificable_desde"] == DESDE
    nuestras = {i["numero_rh"]: i for i in bloque["items"] if i["numero_rh"] in set(n.values())}
    assert n["pasto"] not in nuestras and n["sur"] in nuestras
    assert [i["numero_rh"] for i in nuestras.values() if i["estado"] == "LLEGO"] == [n["sur"]]


async def test_confirm_over_an_existing_state_row_does_not_fail(mundo):
    """The state row appears between the pending check and the write (a racing
    asesor): the upsert updates it, leaves ONE row and logs both answers."""
    n = mundo.n
    actor = ip.Actor(nombre="Coord", usuario_id=mundo.coord.id)
    async with mundo.fabrica() as db:
        db.add(FacturaConfirmacionIngreso(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=n["pend"],
            sucursal_id=mundo.cali.id, estado="NO_HA_LLEGADO",
            actualizado_por_nombre="Otra", actualizado_en=datetime.datetime.now(datetime.timezone.utc)))
        await db.flush()
        item = await ip.confirmar(db, f"RH {n['pend']}", mundo.cali.id, "LLEGO", actor, "link")
        assert item["estado"] == "LLEGO"
    async with mundo.fabrica() as db:
        filas = (await db.execute(select(FacturaConfirmacionIngreso).where(
            FacturaConfirmacionIngreso.numero_rh == n["pend"]))).scalars().all()
        assert [(f.estado, f.actualizado_por_nombre) for f in filas] == [("LLEGO", "Coord")]
