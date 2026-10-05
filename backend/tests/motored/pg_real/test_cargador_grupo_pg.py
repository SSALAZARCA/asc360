"""
Motored associated stores (`sucursal.principal_id`) in the corrida, against
a real Postgres (opt-in).

Runs only with `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) pointing at
a database migrated with `alembic -c alembic_motored.ini upgrade head`. Each
test works inside a transaction that is rolled back at the end.

Only the principal gets a pedido; its lines sum the whole group frozen on
the corrida (an inactive associated store included). A later change to the
association never changes an old corrida, and a corrida frozen before the
groups existed reads each store alone.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import codigos
from app.motored.services.corridas import reproduccion as rp
from app.motored.services.corridas import servicio as sv
from app.motored.services.corridas.codigos import ErrorCorrida
from tests.motored.pg_real.test_corrida_pg import (
    CORTE,
    PATRON,
    _guardar,
    _inventario,
    _lineas,
    _sembrar,
    _sucursal,
    _ventas,
)

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

ASOCIADA_VENTAS = (1, 2, 3, 4, 5, 6)


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _asociar(db, datos, activa=False):
    """A point associated to UNO (closed by default), with history in
    every source."""
    cuatro = _sucursal("CUATRO", activa=activa, principal_id=datos.uno.id)
    await _guardar(db, cuatro)
    cargas = datos.cargas
    await _guardar(
        db,
        *_ventas(cuatro, datos.patron, ASOCIADA_VENTAS, cargas.ventas),
        _inventario(cuatro, datos.patron, 5, cargas.inventario),
        BackorderLinea(
            id=uuid.uuid4(), fecha_corte=datetime.date(2026, 9, 18),
            sucursal_id=cuatro.id, referencia_id=datos.patron.id,
            numero_pedido="P-4", estado="BACKORDER",
            cantidad_pendiente=Decimal(3), carga_id=cargas.backorder.id),
        DemandaPerdida(
            id=uuid.uuid4(), fecha=datetime.date(2026, 4, 10),
            sucursal_id=cuatro.id, referencia_id=datos.patron.id,
            cantidad_solicitada=Decimal(2), origen="EXCEL",
            carga_id=cargas.perdida.id),
        FacturaProveedorLinea(
            id=uuid.uuid4(), prefijo_rh="RH", numero_rh=2,
            fecha_factura=datetime.date(2026, 9, 10),
            sucursal_id=cuatro.id, referencia_id=datos.patron.id,
            cantidad=Decimal(10), valor_total=Decimal(100),
            carga_id=cargas.facturas.id))
    return cuatro


async def _crear(db, **kwargs):
    return await sv.crear_corrida(
        db, fecha_corte=CORTE, hoy=CORTE, **kwargs)


async def _calcular(db, corrida):
    estado = await sv.calcular_corrida(db, corrida.id)
    await db.refresh(corrida)
    return estado


async def _cambiar_principal(db, sucursal, principal_id):
    await db.execute(
        update(Sucursal).where(Sucursal.id == sucursal.id)
        .values(principal_id=principal_id))
    await db.flush()


async def _patron(db, corrida, datos):
    (linea,) = await _lineas(db, corrida.id, datos.uno.id)
    return linea


def _ventas_de(linea):
    return tuple(
        getattr(linea, f"venta_m{i}") for i in range(6, 0, -1))


def _sumadas():
    return tuple(
        Decimal(a + b) for a, b in zip(PATRON, ASOCIADA_VENTAS))


async def test_the_principal_pedido_sums_its_inactive_associated_store(
        sesion):
    datos = await _sembrar(sesion)
    cuatro = await _asociar(sesion, datos)

    corrida = await _crear(sesion)
    assert await _calcular(sesion, corrida) == "BORRADOR"

    tiendas = (await sesion.execute(
        select(CorridaSucursal.sucursal_id)
        .where(CorridaSucursal.corrida_id == corrida.id))).scalars().all()
    assert cuatro.id not in tiendas and corrida.sucursales_total == 3
    assert corrida.seleccion_datos["grupos"] == {
        str(datos.uno.id): [str(cuatro.id)]}
    linea = await _patron(sesion, corrida, datos)
    assert _ventas_de(linea) == _sumadas()
    assert linea.perdida_m5 == Decimal(2)
    assert (linea.inventario, linea.transito, linea.backorder) == (
        Decimal(32), Decimal(80), Decimal(3))
    assert await _lineas(sesion, corrida.id, cuatro.id) == []
    assert (await rp.reproducir(sesion, corrida.id)).identico is True


async def test_an_active_associated_store_gets_no_pedido_of_its_own(
        sesion):
    datos = await _sembrar(sesion)
    cuatro = await _asociar(sesion, datos, activa=True)

    corrida = await _crear(sesion)
    await _calcular(sesion, corrida)

    assert corrida.sucursales_total == 3
    assert await _lineas(sesion, corrida.id, cuatro.id) == []
    linea = await _patron(sesion, corrida, datos)
    assert _ventas_de(linea) == _sumadas()


async def test_an_explicit_associated_store_is_rejected(sesion):
    datos = await _sembrar(sesion)
    cuatro = await _asociar(sesion, datos)

    with pytest.raises(ErrorCorrida) as error:
        await _crear(sesion, sucursal_ids=[cuatro.id])

    assert error.value.codigo == codigos.E_CORRIDA_SUCURSAL_INVALIDA
    principal = datos.uno.nombre.strip()
    assert (
        f"La tienda {cuatro.nombre.strip()} está asociada a {principal}: "
        f"su pedido se calcula en {principal}") in error.value.mensaje


async def test_a_later_association_change_keeps_the_frozen_group(sesion):
    datos = await _sembrar(sesion)
    cuatro = await _asociar(sesion, datos)
    corrida = await _crear(sesion)

    await _cambiar_principal(sesion, cuatro, None)
    await _calcular(sesion, corrida)

    linea = await _patron(sesion, corrida, datos)
    assert _ventas_de(linea) == _sumadas()
    assert linea.inventario == Decimal(32)
    await _cambiar_principal(sesion, cuatro, datos.dos.id)
    assert (await rp.reproducir(sesion, corrida.id)).identico is True


async def test_an_old_corrida_without_a_frozen_group_reads_single_stores(
        sesion):
    datos = await _sembrar(sesion)
    await _asociar(sesion, datos)
    corrida = await _crear(sesion)
    seleccion = dict(corrida.seleccion_datos)
    seleccion.pop("grupos")
    await sesion.execute(
        update(Corrida).where(Corrida.id == corrida.id)
        .values(seleccion_datos=seleccion))
    await sesion.refresh(corrida)

    await _calcular(sesion, corrida)

    linea = await _patron(sesion, corrida, datos)
    assert _ventas_de(linea) == tuple(Decimal(v) for v in PATRON)
    assert (linea.inventario, linea.transito, linea.backorder) == (
        Decimal(27), Decimal(70), Decimal(0))
    assert (await rp.reproducir(sesion, corrida.id)).identico is True
