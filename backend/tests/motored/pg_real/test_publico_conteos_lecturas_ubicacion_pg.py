"""
Inventory counts, per-reading location against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head;
odd/motored-conteos-inventario, WU13b; design §7).

Readings that carry their own `ubicacion_codigo` land there (a missing
location is created as 'PAREJA'), the per-location summary follows, and
two batches racing to create the same new location create it once. The
race runs on two real connections with committed data, cleaned up after.
"""
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.sucursal import Sucursal
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import ubicaciones
from tests.motored.pg_real.codigos_co import codigo_co_unico
from tests.motored.pg_real.test_conteos_api_pg import (  # noqa: F401
    URL, pytestmark,
)
from tests.motored.pg_real import test_publico_conteos_lecturas_pg as lect

# The shared harness, the running conteo and the pair, as fixtures here.
fabrica = lect.fabrica
_app_lista = lect._app_lista
abierto = lect.abierto
pareja = lect.pareja
_sin_cache = lect._sin_cache
_enviar, _filas, _item = lect._enviar, lect._filas, lect._item
_pedir, _resumen, _ubicar = lect._pedir, lect._resumen, lect._ubicar


async def _lugares(fabrica, mundo):
    async with fabrica() as db:
        filas = (await db.execute(
            select(UbicacionInventario.codigo, UbicacionInventario.id,
                   UbicacionInventario.origen)
            .where(UbicacionInventario.sucursal_id
                   == mundo.conteo.sucursal_id))).all()
    return {codigo: (ident, origen) for codigo, ident, origen in filas}


async def _actual(mundo):
    r = await _pedir(mundo, "GET", "/lecturas/recientes")
    assert r.status_code == 200, r.text
    return r.json()["ubicacion_actual"]["codigo"]


async def test_readings_land_in_their_stamped_locations(pareja, fabrica):
    ref_a, ref_b = pareja.ref_a.codigo, pareja.ref_b.codigo
    lote = [
        _item(ref_a, "2", ubicacion_codigo="UBI-B2",
              leida_en="2026-10-09T10:00:00+00:00"),
        _item(ref_b, ubicacion_codigo="a3",
              leida_en="2026-10-09T10:01:00+00:00"),
        _item(ref_a, leida_en="2026-10-09T10:02:00+00:00"),
        _item(ref_b, "4", ubicacion_codigo="b2",
              leida_en="2026-10-09T10:03:00+00:00")]

    resultado = await _enviar(pareja, lote)

    assert resultado["aceptadas"] == [i["id"] for i in lote]
    lugares = await _lugares(fabrica, pareja)
    assert lugares["B2"][1] == "PAREJA"
    por_id = {str(f.id): f.ubicacion_id
              for f in await _filas(fabrica, pareja)}
    a3, b2 = lugares["A3"][0], lugares["B2"][0]
    assert [por_id[i["id"]] for i in lote] == [b2, a3, a3, b2]
    assert await _actual(pareja) == "B2"
    assert await _resumen(pareja) == {
        ref_a.upper(): Decimal("2"), ref_b: Decimal("4")}
    await _ubicar(pareja, "A3")
    assert await _resumen(pareja) == {
        ref_a.upper(): Decimal("1"), ref_b: Decimal("1")}


async def test_an_inactive_stamp_rejects_only_its_reading(pareja, fabrica):
    async with fabrica() as db:
        db.add(UbicacionInventario(
            id=uuid.uuid4(), sucursal_id=pareja.conteo.sucursal_id,
            codigo="C9", nombre="Cerrada", origen="LIDER", activa=False))
        await db.commit()
    mala = _item(pareja.ref_a.codigo, ubicacion_codigo="C9")
    buena = _item(pareja.ref_a.codigo)

    resultado = await _enviar(pareja, [mala, buena])

    assert resultado["aceptadas"] == [buena["id"]]
    assert resultado["rechazadas"] == [
        {"id": mala["id"], "motivo": "UBICACION_INACTIVA"}]
    assert len(await _filas(fabrica, pareja)) == 1


async def _tienda(motor):
    ident = uuid.uuid4()
    async with AsyncSession(motor) as db:
        sucursal = Sucursal(
            id=ident, nombre=f"S {uuid.uuid4().hex[:8]}",
            codigo_co=codigo_co_unico(), bodega_principal="B01",
            activa=True)
        db.add(sucursal)
        await db.commit()
    return ident


async def _limpiar(motor, sucursal_id):
    async with AsyncSession(motor) as db:
        await db.execute(delete(UbicacionInventario).where(
            UbicacionInventario.sucursal_id == sucursal_id))
        await db.execute(delete(Sucursal).where(
            Sucursal.id == sucursal_id))
        await db.commit()


async def test_two_racing_batches_create_a_new_location_once():
    motor = create_async_engine(URL)
    sucursal_id = await _tienda(motor)
    try:
        async with AsyncSession(motor) as uno, AsyncSession(motor) as dos:
            primero = await ubicaciones.ubicar(uno, sucursal_id, {"Z7"})
            # The second batch's INSERT waits on the first's row lock.
            segundo = asyncio.ensure_future(
                ubicaciones.ubicar(dos, sucursal_id, {"Z7", "Z8"}))
            await asyncio.sleep(0.3)
            assert not segundo.done()
            await uno.commit()
            lugares = await segundo
            await dos.commit()
        assert lugares["Z7"].ubicacion_id == primero["Z7"].ubicacion_id
        assert lugares["Z8"].ubicacion_id is not None
        async with AsyncSession(motor) as db:
            codigos = (await db.scalars(
                select(UbicacionInventario.codigo).where(
                    UbicacionInventario.sucursal_id == sucursal_id))).all()
        assert sorted(codigos) == ["Z7", "Z8"]
    finally:
        await _limpiar(motor, sucursal_id)
        await motor.dispose()
