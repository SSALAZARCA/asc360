"""
Motored aviso de antiguedad contra un Postgres real (opt-in).

Corre solo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`.

Cubre lo que los dobles no pueden: la clave unica real de
`aviso_antiguedad_enviado` (reservar es atomico, incluso con dos conexiones
a la vez), el tick completo con cargas y usuarios reales (un solo envio por
(dato, umbral, vencimiento), aunque el tick corra dos veces) y que solo los
usuarios COMPRAS activos con Telegram reciben el aviso.
"""
import asyncio
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.aviso_antiguedad_enviado import (
    AvisoAntiguedadEnviado,
)
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import avisos_antiguedad as av

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

BOGOTA = timezone(timedelta(hours=-5))
VENCE = date(2026, 10, 3)
AHORA = datetime(2026, 10, 2, 16, 30, tzinfo=BOGOTA)


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


async def _cuantos(db, tipo):
    return await db.scalar(
        select(func.count()).select_from(AvisoAntiguedadEnviado)
        .where(AvisoAntiguedadEnviado.dataset == tipo))


async def test_reservar_es_unico_y_liberar_permite_reintentar(sesion):
    tipo = "t" + uuid.uuid4().hex[:8]

    primero = await av.reservar(sesion, tipo, "VISPERA", VENCE, AHORA)
    segundo = await av.reservar(sesion, tipo, "VISPERA", VENCE, AHORA)
    otro_umbral = await av.reservar(sesion, tipo, "DIA", VENCE, AHORA)

    assert (primero, segundo, otro_umbral) == (True, False, True)
    await av.liberar(sesion, tipo, "VISPERA", VENCE)
    assert await av.reservar(sesion, tipo, "VISPERA", VENCE, AHORA) is True
    assert await _cuantos(sesion, tipo) == 2


async def test_dos_conexiones_a_la_vez_solo_una_gana():
    tipo = "c" + uuid.uuid4().hex[:8]
    motor = create_async_engine(URL)

    async def intentar():
        async with AsyncSession(motor) as db:
            ganada = await av.reservar(db, tipo, "DIA", VENCE, AHORA)
            await db.commit()
            return ganada

    try:
        resultados = await asyncio.gather(*[intentar() for _ in range(4)])
        assert sorted(resultados) == [False, False, False, True]
    finally:
        async with AsyncSession(motor) as db:
            await db.execute(delete(AvisoAntiguedadEnviado).where(
                AvisoAntiguedadEnviado.dataset == tipo))
            await db.commit()
        await motor.dispose()


def _usuario(rol, telegram_id, activo=True, status="approved"):
    sufijo = uuid.uuid4().hex[:8]
    return Usuario(
        id=uuid.uuid4(), nombre=f"u{sufijo}", email=f"{sufijo}@x.test",
        hashed_password="x", role=rol, activo=activo, status=status,
        telegram_id=telegram_id)


async def _sembrar_inventario(db, desde):
    db.add(CargaArchivo(
        id=uuid.uuid4(), tipo="INVENTARIO", origen="EXCEL",
        estado="APLICADO", nombre_archivo="i.xlsx",
        hash_sha256=uuid.uuid4().hex * 2, ruta_objeto="r", bytes=1,
        periodo_desde=desde, periodo_hasta=desde))
    await db.flush()


async def test_el_tick_envia_una_vez_solo_a_compras_activos_con_telegram(
        sesion):
    base = 7_000_000_000 + uuid.uuid4().int % 1_000_000
    sesion.add_all([
        _usuario(MotoredRole.COMPRAS, base),
        _usuario(MotoredRole.COMPRAS, base + 1, activo=False),
        _usuario(MotoredRole.COMPRAS, base + 2, status="pending"),
        _usuario(MotoredRole.COMPRAS, None),
        _usuario(MotoredRole.CONSULTA, base + 3),
    ])
    await _sembrar_inventario(sesion, date(2026, 9, 26))
    enviados = []

    async def enviar(chat, texto):
        enviados.append((chat, texto))
        return True

    primero = await av.procesar_avisos(sesion, AHORA, enviar)
    segundo = await av.procesar_avisos(sesion, AHORA, enviar)

    assert (primero, segundo) == (1, 0)
    assert enviados[0][0] == base
    assert len(enviados) == 1
    assert "inventario" in enviados[0][1] and "03/10" in enviados[0][1]
