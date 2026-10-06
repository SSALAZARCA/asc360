"""
Motored "Inicio" against a real Postgres (opt-in).

Runs only with `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) pointing
at a database migrated with `alembic -c alembic_motored.ini upgrade head`.
One connection inside a transaction rolled back at the end
(`join_transaction_mode="create_savepoint"`), so the database stays clean.

Covers what the fakes cannot: the real SQL of the sections, the preflight
facts and limits read from a seeded database, and that each section runs
on its own savepoint (a failed one does not poison the next).
"""
import datetime
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services import inicio
from tests.motored.pg_real.test_corrida_pg import CORTE, _guardar, _sembrar

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

FUTURO = datetime.datetime(2099, 1, 1, 12, 0)


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


def _corrida(proveedor, codigo, minutos, **campos):
    return Corrida(
        id=uuid.uuid4(), codigo=codigo, proveedor_id=proveedor.id,
        fecha_corte=CORTE, estado=campos.pop("estado", "BORRADOR"),
        created_at=FUTURO + datetime.timedelta(minutes=minutos), **campos)


def _tienda(corrida, sucursal, orden, estado_pedido):
    return CorridaSucursal(
        corrida_id=corrida.id, sucursal_id=sucursal.id, orden=orden,
        estado="OK", estado_pedido=estado_pedido)


async def _sembrar_corridas(db, datos):
    """The latest real corrida has two of three tiendas in BORRADOR; a
    newer scenario and a newer annulled corrida must be ignored."""
    sufijo = uuid.uuid4().hex[:6]
    real = _corrida(datos.hmcl, f"PED-T-{sufijo}", 0)
    escenario = _corrida(
        datos.hmcl, f"ESC-T-{sufijo}", 5, es_escenario=True)
    anulada = _corrida(datos.hmcl, f"PED-A-{sufijo}", 10, estado="ANULADA")
    await _guardar(db, real, escenario, anulada)
    await _guardar(
        db,
        _tienda(real, datos.uno, 1, "BORRADOR"),
        _tienda(real, datos.dos, 2, "BORRADOR"),
        _tienda(real, datos.tres, 3, "CERRADO"),
        _tienda(escenario, datos.uno, 1, "BORRADOR"),
        _tienda(anulada, datos.uno, 1, "BORRADOR"))
    return real


async def test_admin_gets_the_staleness_list_and_the_borrador_count(
        fabrica):
    async with fabrica() as db:
        datos = await _sembrar(db)
        real = await _sembrar_corridas(db, datos)

        respuesta = await inicio.construir_inicio(db, "ADMIN", CORTE)

    secciones = respuesta["secciones"]
    assert secciones["pedidos_borrador"] == {
        "disponible": True, "corrida_id": str(real.id),
        "codigo": real.codigo, "tiendas": 2, "total": 3}
    datos_vencer = secciones["datos_por_vencer"]
    assert datos_vencer["disponible"] is True
    por_tipo = {d["tipo"]: d for d in datos_vencer["datos"]}
    assert list(por_tipo) == [
        "INVENTARIO", "BACKORDER", "FACTURAS_PEDIDOS", "INGRESOS_FACTURAS",
        "VENTAS"]
    assert por_tipo["INVENTARIO"]["fecha"] == "2026-09-19"
    assert por_tipo["INVENTARIO"]["antiguedad_dias"] == 2
    assert por_tipo["BACKORDER"]["fecha"] == "2026-09-18"
    assert por_tipo["FACTURAS_PEDIDOS"]["fecha"] == "2026-09-19"
    assert por_tipo["VENTAS"]["fecha"] == "2026-09-14"
    for tipo in ("INVENTARIO", "BACKORDER"):
        assert por_tipo[tipo]["limite_dias"] > 0
        assert por_tipo[tipo]["estado"] in ("al_dia", "por_vencer")
    assert secciones["detractores_sin_gestionar"]["disponible"] is True


async def test_compras_sees_the_latest_sent_corrida(fabrica):
    async with fabrica() as db:
        datos = await _sembrar(db)
        real = await _sembrar_corridas(db, datos)
        enviada = _corrida(datos.hmcl, f"PED-E-{uuid.uuid4().hex[:6]}", -5)
        await _guardar(db, enviada)
        await _guardar(
            db,
            _tienda(enviada, datos.uno, 1, "ENVIADO"),
            _tienda(enviada, datos.dos, 2, "CERRADO"))

        respuesta = await inicio.construir_inicio(db, "COMPRAS", CORTE)

    secciones = respuesta["secciones"]
    assert secciones["ultimo_pedido_enviado"] == {
        "disponible": True, "corrida_id": str(enviada.id),
        "codigo": enviada.codigo, "enviadas": 1, "total": 2}
    assert secciones["pedidos_borrador"]["codigo"] == real.codigo


async def test_a_failed_query_does_not_poison_the_next_section(
        fabrica, monkeypatch):
    async def _rota(ctx):
        await ctx.db.execute(
            Corrida.__table__.select().where(
                Corrida.__table__.c.codigo.op("~")("(")))
        return {}

    monkeypatch.setitem(inicio.CONSTRUCTORES, "pedidos_borrador", _rota)
    async with fabrica() as db:
        await _sembrar(db)

        respuesta = await inicio.construir_inicio(db, "SERVICIO_CLIENTE",
                                                  CORTE)
        admin = await inicio.construir_inicio(db, "ADMIN", CORTE)

    assert respuesta["secciones"]["encuestas_mes"]["disponible"] is True
    assert admin["secciones"]["pedidos_borrador"] == {"disponible": False}
    assert admin["secciones"]["datos_por_vencer"]["disponible"] is True
    assert admin["secciones"]["detractores_sin_gestionar"][
        "disponible"] is True
