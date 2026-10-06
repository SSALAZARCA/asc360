"""
`errores_integridad.describir` on real asyncpg errors (Postgres migrated
to head): the constraint name and SQLSTATE come from the driver, not from
the message text. Each test rolls back.
"""
import os
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services import errores_integridad
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(
        motor, expire_on_commit=False, autoflush=False
    )
    async with fabrica() as db:
        yield db
        await db.rollback()
    await motor.dispose()


def _sucursal(nombre):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, codigo_co=codigo_co_unico(),
    )


async def test_a_repeated_store_name_names_its_key(sesion):
    nombre = f"DOBLE {uuid.uuid4().hex[:6]}"
    sesion.add(_sucursal(nombre))
    await sesion.flush()
    sesion.add(_sucursal(nombre))

    with pytest.raises(IntegrityError) as error:
        await sesion.flush()

    assert errores_integridad.describir(error.value, "prueba") == (
        "23505", "sucursal_nombre_key"
    )


async def test_a_bodega_of_a_missing_store_names_its_foreign_key(sesion):
    sesion.add(Bodega(
        id=uuid.uuid4(), codigo=f"FK{uuid.uuid4().hex[:6]}",
        sucursal_id=uuid.uuid4(),
    ))

    with pytest.raises(IntegrityError) as error:
        await sesion.flush()

    violacion = errores_integridad.describir(error.value, "prueba")
    assert violacion == ("23503", "bodega_sucursal_id_fkey")
    assert errores_integridad.respuesta(violacion).status_code == 500
