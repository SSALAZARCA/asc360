"""
Store code C.O. (`sucursal.codigo_co`) against a real Postgres.

Runs only with `MOTORED_TEST_PG_URL` pointing at a database migrated with
`alembic -c alembic_motored.ini upgrade head`. Each test works inside a
transaction rolled back at the end (`commit()` is degraded to `flush()`).

The UNIQUE constraint is DEFERRABLE INITIALLY DEFERRED, so it only fires
at COMMIT, which these tests never reach: `SET CONSTRAINTS ... IMMEDIATE`
forces the check where a test needs it.

Covers what the doubles cannot: the constraint itself (deferred, NULLs on
many rows), two stores swapping their (code, name) pairs in one upload
(the C.O. is the key, so it is a swap of names), and the service queries
on real rows. `test_sucursal_clave_co_pg.py` covers renames and the first
upload of codes.
"""
import os
import random
import string
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.sucursal import Sucursal
from app.motored.services import maestros

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

USER_ID = None  # `auditoria_maestro.usuario_id` is a real FK to `usuario`
_INMEDIATA = text("SET CONSTRAINTS uq_sucursal_codigo_co IMMEDIATE")


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


def _sufijo():
    return uuid.uuid4().hex[:6].upper()


async def _codigos_libres(sesion, cuantos):
    """Well-formed codes that no saved store holds."""
    usados = set((await sesion.execute(
        select(Sucursal.codigo_co).where(Sucursal.codigo_co.isnot(None))
    )).scalars().all())
    libres = []
    while len(libres) < cuantos:
        codigo = random.choice(string.ascii_uppercase) + (
            f"{random.randint(0, 99):02d}"
        )
        if codigo not in usados and codigo not in libres:
            libres.append(codigo)
    return libres


async def _crear(sesion, nombre, codigo_co=None):
    sucursal = Sucursal(id=uuid.uuid4(), nombre=nombre, codigo_co=codigo_co)
    sesion.add(sucursal)
    await sesion.flush()
    return sucursal


async def _codigo_de(sesion, nombre):
    return (await sesion.execute(
        select(Sucursal.codigo_co).where(Sucursal.nombre == nombre)
    )).scalar_one()


async def test_the_constraint_is_unique_and_deferred(sesion):
    fila = (await sesion.execute(text(
        "SELECT contype::text, condeferrable, condeferred FROM pg_constraint "
        "WHERE conname = 'uq_sucursal_codigo_co'"
    ))).one()

    assert tuple(fila) == ("u", True, True)


async def test_two_stores_with_one_code_fail_at_the_check(sesion):
    (codigo,) = await _codigos_libres(sesion, 1)
    await _crear(sesion, f"CO A {_sufijo()}", codigo)
    await _crear(sesion, f"CO B {_sufijo()}", codigo)

    with pytest.raises(IntegrityError, match="uq_sucursal_codigo_co"):
        async with sesion.begin_nested():
            await sesion.execute(_INMEDIATA)


async def test_many_stores_without_a_code_are_allowed(sesion):
    await _crear(sesion, f"SIN CO A {_sufijo()}")
    await _crear(sesion, f"SIN CO B {_sufijo()}")

    await sesion.execute(_INMEDIATA)


async def test_crud_check_names_the_store_holding_the_code(sesion):
    (codigo,) = await _codigos_libres(sesion, 1)
    duena = await _crear(sesion, f"DUENA {_sufijo()}", codigo)

    with pytest.raises(maestros.CodigoCoEnUsoError, match=duena.nombre):
        await maestros.validar_codigo_co_libre(sesion, None, codigo)
    await maestros.validar_codigo_co_libre(sesion, duena.id, codigo)


async def test_upload_swaps_two_code_name_pairs_in_one_file(sesion):
    primero, segundo = await _codigos_libres(sesion, 2)
    nombre_a, nombre_b = f"SWAP A {_sufijo()}", f"SWAP B {_sufijo()}"
    await _crear(sesion, nombre_a, primero)
    await _crear(sesion, nombre_b, segundo)

    resultado = await _resolver_y_procesar_carga(
        sesion, "sucursal",
        [{"nombre": nombre_a, "codigo_co": segundo.lower()},
         {"nombre": nombre_b, "codigo_co": f" {primero} "}],
        USER_ID,
    )

    assert resultado.ok is True
    await sesion.flush()
    await sesion.execute(_INMEDIATA)
    assert await _codigo_de(sesion, nombre_a) == segundo
    assert await _codigo_de(sesion, nombre_b) == primero


async def test_upload_rejects_a_code_and_a_name_of_different_stores(
    sesion,
):
    usado, libre = await _codigos_libres(sesion, 2)
    duena = await _crear(sesion, f"DUENA {_sufijo()}", usado)

    resultado = await _resolver_y_procesar_carga(
        sesion, "sucursal", [{"nombre": duena.nombre, "codigo_co": libre}],
        USER_ID,
    )

    assert resultado.ok is False
    assert f"'{usado}'" in resultado.errores[0].motivo
    assert await _codigo_de(sesion, duena.nombre) == usado


async def test_upload_blank_cell_is_a_row_error(sesion):
    (codigo,) = await _codigos_libres(sesion, 1)
    tienda = await _crear(sesion, f"GUARDA {_sufijo()}", codigo)

    resultado = await _resolver_y_procesar_carga(
        sesion, "sucursal",
        [{"nombre": tienda.nombre, "codigo_co": "", "ciudad": "Cali"}],
        USER_ID,
    )

    assert resultado.ok is False
    assert await _codigo_de(sesion, tienda.nombre) == codigo
