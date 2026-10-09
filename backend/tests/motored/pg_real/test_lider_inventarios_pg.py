"""
LIDER_INVENTARIOS against a real Postgres (opt-in): the migrated
`motored_role` enum accepts the value, and a web user with that role keeps
the web-credentials CHECK (email and password required).

Runs only with `MOTORED_TEST_PG_URL`; each test is rolled back.
"""
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.usuario import MotoredRole, Usuario

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def test_the_enum_has_the_new_value(sesion):
    valores = (await sesion.execute(
        text("SELECT unnest(enum_range(NULL::motored_role))::text")
    )).scalars().all()

    assert "LIDER_INVENTARIOS" in valores


async def test_a_lider_user_round_trips(sesion):
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Lider",
        email=f"l-{uuid.uuid4().hex[:8]}@x.com", hashed_password="h",
        role=MotoredRole.LIDER_INVENTARIOS, activo=True,
        status="approved",
    )
    sesion.add(usuario)
    await sesion.flush()

    leido = (await sesion.execute(
        select(Usuario.role).where(Usuario.id == usuario.id)
    )).scalar_one()
    assert leido is MotoredRole.LIDER_INVENTARIOS


async def test_the_role_still_requires_web_credentials(sesion):
    sesion.add(Usuario(
        id=uuid.uuid4(), nombre="Sin clave", email=None,
        hashed_password=None, role=MotoredRole.LIDER_INVENTARIOS,
        activo=True, status="approved",
    ))

    with pytest.raises(IntegrityError):
        await sesion.flush()
