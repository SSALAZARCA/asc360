"""
usuario.cedula against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`,
database migrated to head; odd/motored-reporte-diario-asesor, T1).

The partial unique index `uq_usuario_cedula_aprobada` allows any number of
PENDING rows with one cédula but only ONE approved row, and the service
check reads the real tables. Every test rolls back.
"""
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.services import cedula_usuario

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


def _cedula():
    return str(uuid.uuid4().int)[:12]


def _asesor(cedula, aprobada):
    return Usuario(
        id=uuid.uuid4(), nombre=f"Asesor {uuid.uuid4().hex[:6]}",
        role=MotoredRole.ASESOR_MOSTRADOR, activo=True, status="approved",
        cedula=cedula, cedula_aprobada=aprobada,
    )


def _vendedor(cedula, activo=True):
    sufijo = uuid.uuid4().hex[:10].upper()
    return Vendedor(
        id=uuid.uuid4(), nombre=f"Vend {sufijo}",
        nombre_norm=f"VEND {sufijo}", cargo="ASESOR", cedula=cedula,
        activo=activo,
    )


async def test_the_partial_unique_index_exists(sesion):
    definicion = (await sesion.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname = 'uq_usuario_cedula_aprobada'"))).scalar_one()

    assert "UNIQUE" in definicion
    assert "WHERE cedula_aprobada" in definicion


async def test_cedula_aprobada_defaults_to_false(sesion):
    usuario_id = uuid.uuid4()
    await sesion.execute(text(
        "INSERT INTO usuario (id, nombre, role, activo, status) "
        "VALUES (:id, 'Sin flag', 'ASESOR_MOSTRADOR', true, 'pending')"),
        {"id": usuario_id})

    valor = (await sesion.execute(text(
        "SELECT cedula_aprobada FROM usuario WHERE id = :id"),
        {"id": usuario_id})).scalar_one()

    assert valor is False


async def test_pending_duplicates_are_allowed(sesion):
    cedula = _cedula()
    sesion.add_all([
        _asesor(cedula, False), _asesor(cedula, False),
        _asesor(cedula, True),
    ])

    await sesion.flush()


async def test_two_approved_rows_with_one_cedula_are_refused(sesion):
    cedula = _cedula()
    sesion.add_all([_asesor(cedula, True), _asesor(cedula, True)])

    with pytest.raises(IntegrityError, match="uq_usuario_cedula_aprobada"):
        await sesion.flush()


async def test_service_approves_against_the_real_master(sesion):
    cedula = _cedula()
    usuario = _asesor(cedula, False)
    sesion.add_all([usuario, _vendedor(cedula)])
    await sesion.flush()

    await cedula_usuario.aprobar(sesion, usuario)

    assert usuario.cedula_aprobada is True


async def test_service_ignores_an_inactive_vendedor(sesion):
    cedula = _cedula()
    usuario = _asesor(cedula, False)
    sesion.add_all([usuario, _vendedor(cedula, activo=False)])
    await sesion.flush()

    with pytest.raises(cedula_usuario.CedulaInvalida):
        await cedula_usuario.aprobar(sesion, usuario)


async def test_service_names_the_other_approved_holder(sesion):
    cedula = _cedula()
    duena = _asesor(cedula, True)
    impostor = _asesor(cedula, False)
    sesion.add_all([duena, impostor, _vendedor(cedula)])
    await sesion.flush()

    with pytest.raises(cedula_usuario.CedulaDuplicada, match=duena.nombre):
        await cedula_usuario.aprobar(sesion, impostor)
