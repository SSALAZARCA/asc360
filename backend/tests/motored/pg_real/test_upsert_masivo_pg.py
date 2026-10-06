"""
Upserts masivos (`venta_mensual`, `inventario_snapshot`) contra un Postgres real.

Reproduce el 500 de produccion (2026-10-03): una unica sentencia con >32 767
parametros reventaba en asyncpg. Corre solo con `MOTORED_TEST_PG_URL`.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.ingesta import inventario, ventas

from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

N_VENTAS = 15_000
N_INVENTARIO = 25_000


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _mundo(db, n_sucursales, n_referencias):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    sucursales = [
        Sucursal(
            id=uuid.uuid4(), nombre=f"S{i} {uuid.uuid4().hex[:6]}",
            sic=f"SIC-{i}", codigo_co=codigo_co_unico())
        for i in range(n_sucursales)]
    db.add_all([proveedor, *sucursales])
    await db.flush()
    referencias = [
        Referencia(
            id=uuid.uuid4(), codigo=f"R-{i}-{uuid.uuid4().hex[:6]}", proveedor_id=proveedor.id,
            unidad_empaque=1, precio_normal=Decimal("100"))
        for i in range(n_referencias)]
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="VALIDADO",
        nombre_archivo="v.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
    db.add_all([*referencias, carga])
    await db.flush()
    return sucursales, referencias, carga


async def test_aplicar_ventas_supera_el_limite_de_parametros(sesion):
    sucursales, referencias, carga = await _mundo(sesion, 1, 90)
    totales = {}
    for ref in referencias:
        for anio in range(2018, 2027):
            for mes in range(1, 13):
                for origen in ("MOSTRADOR", "TALLER"):
                    totales[(sucursales[0].id, ref.id, anio, mes, origen)] = Decimal("5")
    totales = dict(list(totales.items())[:N_VENTAS])
    assert len(totales) == N_VENTAS

    await ventas.aplicar(sesion, totales, carga.id)
    await sesion.flush()

    cuenta = (await sesion.execute(
        select(func.count()).select_from(VentaMensual).where(VentaMensual.carga_id == carga.id)
    )).scalar_one()
    assert cuenta == N_VENTAS


async def test_aplicar_inventario_supera_el_limite_de_parametros(sesion):
    sucursales, referencias, carga = await _mundo(sesion, 250, 100)
    consolidado = {
        (s.id, r.id): Decimal("3") for s in sucursales for r in referencias}
    assert len(consolidado) == N_INVENTARIO

    await inventario.aplicar(sesion, consolidado, datetime.date(2026, 9, 15), carga.id)
    await sesion.flush()

    cuenta = (await sesion.execute(
        select(func.count()).select_from(InventarioSnapshot)
        .where(InventarioSnapshot.carga_id == carga.id)
    )).scalar_one()
    assert cuenta == N_INVENTARIO
