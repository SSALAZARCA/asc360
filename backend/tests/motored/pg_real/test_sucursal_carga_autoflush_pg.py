"""
Sucursales upload with the production session settings, against a real
Postgres (opt-in, `MOTORED_TEST_PG_URL` on a database migrated with
`alembic -c alembic_motored.ini upgrade head`). Each test runs inside a
transaction rolled back at the end (`commit()` becomes `flush()`).

Production sessions run with `autoflush=False` (`database.py`). A file that
creates a store and gives it a secondary bodega used to write the
`bodega` row before the new store's INSERT: `bodega_sucursal_id_fkey`
failed and the owner saw "Otra carga modificó estos registros".
"""
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

USER_ID = None  # `auditoria_maestro.usuario_id` is a real FK to `usuario`


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(
        motor, expire_on_commit=False, autoflush=False
    )
    async with fabrica() as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


def _fila(codigo, nombre, principal, secundarias):
    return {
        "codigo_co": codigo, "nombre": nombre,
        "bodega_principal": principal, "bodegas_secundarias": secundarias,
    }


async def _subir(db, filas):
    resultado = await _resolver_y_procesar_carga(
        db, "sucursal", filas, USER_ID
    )
    assert resultado.ok is True, resultado.errores
    await db.flush()


def _sufijo():
    return uuid.uuid4().hex[:4].upper()


async def test_new_store_takes_a_moved_and_a_new_secondary(sesion):
    s = _sufijo()
    co_x = "X" + str(int(s[:2], 16) % 100).zfill(2)
    co_y = "Y" + str(int(s[2:], 16) % 100).zfill(2)
    x, y = f"TIENDA X {s}", f"TIENDA Y {s}"
    p, q, mover, nueva = (f"{c}{s}" for c in ("BP", "BQ", "MC", "BT"))
    await _subir(sesion, [_fila(co_x, x, p, mover)])

    await _subir(sesion, [
        _fila(co_x, x, p, ""),
        _fila(co_y, y, q, f"{mover}, {nueva}"),
    ])

    id_y = (await sesion.execute(
        select(Sucursal.id).where(Sucursal.nombre == y)
    )).scalar_one()
    bodegas = {
        b.codigo: (b.sucursal_id, b.bodega_principal)
        for b in (await sesion.execute(
            select(Bodega).where(Bodega.codigo.in_([mover, nueva]))
        )).scalars()
    }
    assert bodegas == {mover: (id_y, q), nueva: (id_y, q)}
