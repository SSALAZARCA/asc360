"""
Migration `c6e1f8a2d953` (`sucursal.codigo_co` NOT NULL) against a real
Postgres migrated to head. Each test runs the migration's own downgrade
and upgrade inside one transaction rolled back at the end (Postgres DDL
is transactional), so the database stays at head.
"""
import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

_ARCHIVO = (
    Path(__file__).resolve().parents[3] / "alembic_motored" / "versions"
    / "c6e1f8a2d953_codigo_co_obligatorio.py"
)
_NULLABLE = text(
    "SELECT is_nullable FROM information_schema.columns "
    "WHERE table_name = 'sucursal' AND column_name = 'codigo_co'"
)
_INSERT = text(
    "INSERT INTO sucursal (id, nombre, codigo_co, dias_seguridad, activa) "
    "VALUES (:id, :nombre, :codigo, 2.5, true)"
)


def _migracion():
    spec = importlib.util.spec_from_file_location("codigo_co_req", _ARCHIVO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _correr(conexion, paso):
    contexto = MigrationContext.configure(conexion)
    with Operations.context(contexto):
        paso()


@pytest.fixture
async def conexion():
    motor = create_async_engine(URL)
    async with motor.connect() as con:
        transaccion = await con.begin()
        yield con
        await transaccion.rollback()
    await motor.dispose()


async def _nullable(con):
    return (await con.execute(_NULLABLE)).scalar_one()


async def test_head_requires_the_code(conexion):
    assert await _nullable(conexion) == "NO"
    with pytest.raises(IntegrityError, match="codigo_co"):
        await conexion.execute(_INSERT, {
            "id": uuid.uuid4(), "nombre": f"SIN CO {uuid.uuid4().hex}",
            "codigo": None,
        })


async def test_downgrade_then_upgrade_on_a_clean_table(conexion):
    modulo = _migracion()

    await conexion.run_sync(_correr, modulo.downgrade)
    assert await _nullable(conexion) == "YES"

    await conexion.run_sync(_correr, modulo.upgrade)
    assert await _nullable(conexion) == "NO"


async def test_upgrade_stops_when_a_store_has_no_code(conexion):
    modulo = _migracion()
    await conexion.run_sync(_correr, modulo.downgrade)
    nombre = f"SIN CO {uuid.uuid4().hex[:6]}"
    await conexion.execute(_INSERT, {
        "id": uuid.uuid4(), "nombre": nombre, "codigo": None,
    })

    with pytest.raises(RuntimeError) as error:
        await conexion.run_sync(_correr, modulo.upgrade)

    assert "Hay 1 sucursal sin Código C.O." in str(error.value)
    assert nombre in str(error.value)
    assert await _nullable(conexion) == "YES"
