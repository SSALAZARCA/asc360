"""
reporte_asesor_link against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`,
database migrated to head; odd/motored-reporte-diario-asesor, T3a).

The partial unique index `uq_reporte_asesor_link_activo` allows any number
of REVOKED links per usuario but only ONE active one; `generar_link`
revokes the old one first, so regenerating never trips it. Every test
rolls back.
"""
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import reporte_asesor_link as servicio

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(
        motor, expire_on_commit=False, autoflush=False)
    async with fabrica() as db:
        yield db
        await db.rollback()
    await motor.dispose()


def _asesor():
    return Usuario(
        id=uuid.uuid4(), nombre=f"Asesor {uuid.uuid4().hex[:6]}",
        role=MotoredRole.ASESOR_MOSTRADOR, activo=True, status="approved",
        cedula=str(uuid.uuid4().int)[:12], cedula_aprobada=True,
        telegram_id=int(str(uuid.uuid4().int)[:9]),
    )


def _link(usuario, **extra):
    return ReporteAsesorLink(
        id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
        token=uuid.uuid4().hex + uuid.uuid4().hex, **extra)


async def _activos(sesion, usuario_id) -> int:
    stmt = select(ReporteAsesorLink).where(
        ReporteAsesorLink.usuario_id == usuario_id,
        ReporteAsesorLink.revocado_en.is_(None))
    return len((await sesion.execute(stmt)).scalars().all())


async def test_the_partial_unique_index_exists(sesion):
    definicion = (await sesion.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname = 'uq_reporte_asesor_link_activo'"))).scalar_one()

    assert "UNIQUE" in definicion
    assert "WHERE (revocado_en IS NULL)" in definicion


async def test_defaults_for_a_new_link(sesion):
    usuario = _asesor()
    sesion.add(usuario)
    await sesion.flush()
    link = _link(usuario)
    sesion.add(link)
    await sesion.flush()

    fila = (await sesion.execute(text(
        "SELECT intentos_fallidos, bloqueado_hasta, creado_en "
        "FROM reporte_asesor_link WHERE id = :id"),
        {"id": link.id})).one()

    assert fila.intentos_fallidos == 0
    assert fila.bloqueado_hasta is None
    assert fila.creado_en is not None


async def test_two_active_links_for_one_usuario_are_refused(sesion):
    usuario = _asesor()
    sesion.add(usuario)
    await sesion.flush()
    sesion.add_all([_link(usuario), _link(usuario)])

    with pytest.raises(
            IntegrityError, match="uq_reporte_asesor_link_activo"):
        await sesion.flush()


async def test_revoked_links_do_not_count(sesion):
    usuario = _asesor()
    sesion.add(usuario)
    await sesion.flush()
    sesion.add_all([
        _link(usuario, revocado_en=text("now()")),
        _link(usuario, revocado_en=text("now()")),
        _link(usuario),
    ])

    await sesion.flush()

    assert await _activos(sesion, usuario.id) == 1


async def test_a_token_is_unique(sesion):
    uno, otro = _asesor(), _asesor()
    sesion.add_all([uno, otro])
    await sesion.flush()
    repetido = _link(uno)
    copia = _link(otro)
    copia.token = repetido.token
    sesion.add_all([repetido, copia])

    with pytest.raises(IntegrityError, match="uq_reporte_asesor_link_token"):
        await sesion.flush()


async def test_generar_twice_leaves_one_active_link(sesion):
    usuario = _asesor()
    sesion.add(usuario)
    await sesion.flush()

    primero = await servicio.generar_link(sesion, usuario, None)
    await sesion.flush()
    segundo = await servicio.generar_link(sesion, usuario, None)
    await sesion.flush()

    assert await _activos(sesion, usuario.id) == 1
    assert (await servicio.link_activo(sesion, usuario.id)).id == segundo.id
    await sesion.refresh(primero)
    assert primero.motivo_revocacion == "regenerado"


async def test_deleting_the_usuario_cascades(sesion):
    usuario = _asesor()
    sesion.add(usuario)
    await sesion.flush()
    sesion.add(_link(usuario))
    await sesion.flush()

    await sesion.execute(
        text("DELETE FROM usuario WHERE id = :id"), {"id": usuario.id})

    assert await _activos(sesion, usuario.id) == 0
