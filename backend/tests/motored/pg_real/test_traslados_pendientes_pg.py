"""
Pending transfers against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`;
odd/tasks/motored-traslados-pendientes.md, T2).

One outer transaction rolled back at the end (savepoint sessions), so the
service's `commit()` leaves nothing behind. The database may hold real loads:
ours are applied in 2097 (the latest snapshot wins), with fresh stores and
document numbers, and every assertion looks only at those.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.sucursal import Sucursal
from app.motored.models.traslado import TrasladoConfirmacion, TrasladoLinea
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.services import informe_publico as publico
from app.motored.services import traslados_pendientes as tp
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
HOY = datetime.date(2097, 10, 9)
UTC = datetime.timezone.utc


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


def _carga(dia, estado="APLICADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo="TRASLADOS", origen="EXCEL", estado=estado,
        nombre_archivo="t.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1,
        aplicado_en=datetime.datetime(2097, 10, dia, 7, 0, tzinfo=UTC))


@pytest.fixture
async def mundo(fabrica):
    sfx = uuid.uuid4().hex[:6]
    async with fabrica() as db:
        cali = Sucursal(id=uuid.uuid4(), nombre=f"Cali {sfx}",
                        codigo_co=codigo_co_unico())
        pasto = Sucursal(id=uuid.uuid4(), nombre=f"Pasto {sfx}",
                         codigo_co=codigo_co_unico())
        origen = Sucursal(id=uuid.uuid4(), nombre=f"Medellin {sfx}",
                          codigo_co=codigo_co_unico())
        db.add_all([cali, pasto, origen])
        await db.flush()
        sur = Sucursal(id=uuid.uuid4(), nombre=f"Cali Sur {sfx}",
                       codigo_co=codigo_co_unico(), principal_id=cali.id)
        db.add(sur)
        # snapshot 1 (day 8), the latest (day 9) and an annulled newer one (day 10)
        c1, c2, anulada = _carga(8), _carga(9), _carga(10, "ANULADO")
        db.add_all([c1, c2, anulada])
        await db.flush()
        n = {k: f"79-{sfx}{i}" for i, k in enumerate(
            ("gone", "stay", "dup", "sur", "pasto", "annulled"))}

        def linea(carga, doc, bod, destino, fecha, ref="R1", cant=1, org=origen):
            db.add(TrasladoLinea(
                id=uuid.uuid4(), carga_id=carga.id, nro_documento=doc,
                fecha=fecha, bodega_salida=bod, sucursal_salida_id=org.id,
                bodega_entrada="BE", sucursal_entrada_id=destino.id,
                referencia_codigo=ref, descripcion=f"desc {ref}",
                cantidad=D(cant)))

        d = datetime.date
        linea(c1, n["gone"], "BA1", cali, d(2097, 9, 1))        # received since
        linea(c1, n["stay"], "BA1", cali, d(2097, 9, 2))
        linea(c2, n["stay"], "BA1", cali, d(2097, 9, 2), ref="R1", cant=2)
        linea(c2, n["stay"], "BA1", cali, d(2097, 9, 4), ref="R2", cant=3)
        linea(c2, n["dup"], "BA1", cali, d(2097, 10, 1))        # same doc,
        linea(c2, n["dup"], "BB2", pasto, d(2097, 10, 1))       # two origins
        linea(c2, n["sur"], "BA1", sur, d(2097, 10, 5))         # rolls up to Cali
        linea(c2, n["pasto"], "BA1", pasto, d(2097, 10, 6))
        linea(anulada, n["annulled"], "BA1", cali, d(2097, 10, 7))

        cedula = f"7{int(sfx, 16) % 10**8:08d}"
        usuario = Usuario(
            id=uuid.uuid4(), nombre=f"Ana {sfx}", role=MotoredRole.ASESOR_MOSTRADOR,
            activo=True, status="approved", cedula=cedula, cedula_aprobada=True,
            telegram_id=int(str(uuid.uuid4().int)[:9]))
        coord = Usuario(
            id=uuid.uuid4(), nombre=f"Coord {sfx}", role=MotoredRole.COMPRAS,
            activo=True, status="approved", email=f"c{sfx}@x.co",
            hashed_password="x")
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
    m.c1, m.c2, m.anulada = c1, c2, anulada
    m.usuario, m.coord, m.token, m.cedula = usuario, coord, link.token, cedula
    return m


def _por_clave(items, n):
    mios = set(n.values())
    return {(i["documento"], i["bodega_salida"]): i
            for i in items if i["documento"] in mios}


async def test_the_snapshot_is_the_latest_applied_non_annulled_load(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        assert (await tp.carga_vigente(db))[0] == mundo.c2.id
        items = _por_clave(await tp.pendientes(db, hoy=HOY), n)

    # the transfer missing from the newest load is gone (received in the ERP)
    assert (n["gone"], "BA1") not in items
    assert n["annulled"] not in {k[0] for k in items}
    assert set(items) == {(n["stay"], "BA1"), (n["dup"], "BA1"),
                          (n["dup"], "BB2"), (n["sur"], "BA1"),
                          (n["pasto"], "BA1")}


async def test_grouping_totals_and_rollup(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        items = _por_clave(await tp.pendientes(db, hoy=HOY), n)

    stay = items[(n["stay"], "BA1")]
    assert stay["fecha"] == datetime.date(2097, 9, 2) and stay["dias"] == 37
    assert stay["refs"] == 2 and stay["unidades"] == 5.0 and stay["num_lineas"] == 2
    assert [(ln["referencia"], ln["cantidad"]) for ln in stay["lineas"]] == [
        ("R1", 2.0), ("R2", 3.0)]
    assert stay["estado"] == "SIN_CONFIRMAR" and stay["aviso_erp"] is False
    assert items[(n["dup"], "BA1")]["sucursal_id"] == mundo.cali.id
    assert items[(n["dup"], "BB2")]["sucursal_id"] == mundo.pasto.id
    assert items[(n["sur"], "BA1")]["sucursal_id"] == mundo.cali.id
    assert items[(n["sur"], "BA1")]["llega"] == mundo.cali.nombre
    assert stay["sale"].startswith("Medellin")


async def test_filtering_by_store_and_no_snapshot(mundo, fabrica):
    n = mundo.n
    async with mundo.fabrica() as db:
        de_pasto = _por_clave(await tp.pendientes(db, [mundo.pasto.id], hoy=HOY), n)
        # an associated store id resolves to its principal
        de_cali = _por_clave(await tp.pendientes(db, [mundo.sur.id], hoy=HOY), n)
    assert set(de_pasto) == {(n["dup"], "BB2"), (n["pasto"], "BA1")}
    assert (n["stay"], "BA1") in de_cali and (n["pasto"], "BA1") not in de_cali


async def test_annulling_the_latest_load_restores_the_previous_snapshot(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        carga = await db.get(CargaArchivo, mundo.c2.id)
        carga.estado = "ANULADO"
        await db.flush()
        assert (await tp.carga_vigente(db))[0] == mundo.c1.id
        items = _por_clave(await tp.pendientes(db, hoy=HOY), n)
    assert set(items) == {(n["gone"], "BA1"), (n["stay"], "BA1")}


async def test_confirm_logs_history_and_can_be_corrected(mundo):
    n = mundo.n
    actor = tp.Actor(nombre="Coord", usuario_id=mundo.coord.id)
    async with mundo.fabrica() as db:
        item = await tp.confirmar(
            db, n["stay"], "BA1", "NO_HA_LLEGADO", actor, "web")
        assert item["estado"] == "NO_HA_LLEGADO" and item["aviso_erp"] is False
        await tp.confirmar(db, n["stay"], "BA1", "RECIBIDO", actor, "web")
    async with mundo.fabrica() as db:
        items = _por_clave(await tp.pendientes(db, hoy=HOY), n)
        assert items[(n["stay"], "BA1")]["estado"] == "RECIBIDO"
        assert items[(n["stay"], "BA1")]["aviso_erp"] is True
        assert items[(n["stay"], "BA1")]["confirmado_por"] == "Coord"
        # the same document from another origin is a different transfer
        assert items[(n["dup"], "BA1")]["estado"] == "SIN_CONFIRMAR"
        h = await tp.historial(db, n["stay"], "BA1")
        assert [x["estado"] for x in h] == ["RECIBIDO", "NO_HA_LLEGADO"]
        assert await tp.historial(db, n["stay"], "BB2") == []


async def test_confirm_validations(mundo):
    n = mundo.n
    actor = tp.Actor(nombre="Coord")
    async with mundo.fabrica() as db:
        for doc, bod, estado, codigo in [
            (n["gone"], "BA1", "RECIBIDO", 404),      # left the snapshot
            (n["annulled"], "BA1", "RECIBIDO", 404),  # only in an annulled load
            (n["dup"], "ZZ", "RECIBIDO", 404),        # no such origin
            (n["stay"], "BA1", "LLEGO", 422),
            ("", "BA1", "RECIBIDO", 422),
        ]:
            with pytest.raises(tp.PendienteError) as exc:
                await tp.confirmar(db, doc, bod, estado, actor, "web")
            assert exc.value.status_code == codigo


async def test_confirm_over_an_existing_state_row_does_not_fail(mundo):
    n = mundo.n
    actor = tp.Actor(nombre="Coord", usuario_id=mundo.coord.id)
    async with mundo.fabrica() as db:
        db.add(TrasladoConfirmacion(
            id=uuid.uuid4(), nro_documento=n["stay"], bodega_salida="BA1",
            estado="NO_HA_LLEGADO", actualizado_por_nombre="Otra",
            actualizado_en=datetime.datetime.now(UTC)))
        await db.flush()
        item = await tp.confirmar(db, n["stay"], "BA1", "RECIBIDO", actor, "link")
        assert item["estado"] == "RECIBIDO"
    async with mundo.fabrica() as db:
        filas = (await db.execute(select(TrasladoConfirmacion).where(
            TrasladoConfirmacion.nro_documento == n["stay"]))).scalars().all()
        assert [(f.estado, f.actualizado_por_nombre) for f in filas] == [
            ("RECIBIDO", "Coord")]


async def test_public_list_confirm_and_cedula_check(mundo):
    n = mundo.n
    async with mundo.fabrica() as db:
        bloque = await publico.traslados_del_asesor(db, mundo.token, mundo.cedula)
        mios = _por_clave(bloque["items"], n)
        # her store is Cali (via Cali Sur): Pasto's transfers are not hers
        assert (n["sur"], "BA1") in mios and (n["pasto"], "BA1") not in mios
        assert (n["dup"], "BB2") not in mios
        item = await publico.confirmar_traslado(
            db, mundo.token, mundo.cedula, n["sur"], "BA1", "RECIBIDO")
        assert item["estado"] == "RECIBIDO" and item["sucursal_id"] == mundo.cali.id
        with pytest.raises(publico.InformeError) as exc:
            await publico.confirmar_traslado(
                db, mundo.token, mundo.cedula, n["pasto"], "BA1", "RECIBIDO")
        assert exc.value.status_code == 404
        for llamada in (
            publico.traslados_del_asesor(db, mundo.token, "00000"),
            publico.confirmar_traslado(
                db, mundo.token, "00000", n["sur"], "BA1", "RECIBIDO"),
        ):
            with pytest.raises(publico.InformeError) as exc:
                await llamada
            assert exc.value.status_code == 401
    async with mundo.fabrica() as db:
        h = await tp.historial(db, n["sur"], "BA1")
        assert h[0]["canal"] == "link" and h[0]["por"].startswith("Ana")
