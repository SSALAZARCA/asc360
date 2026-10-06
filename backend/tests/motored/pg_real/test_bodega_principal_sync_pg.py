"""
Sucursales upload: the principal bodega's own record, against a real
Postgres (opt-in, `MOTORED_TEST_PG_URL` on a database migrated with
`alembic -c alembic_motored.ini upgrade head`). Each test runs inside a
transaction rolled back at the end (`commit()` becomes `flush()`).

The owner's scenario: store A16 had principal BA071 and secondaries BA161,
BC111 and BD011. The next file makes BA161 A16's principal, moves BA071 to
the new store A07 as its principal, makes BC111 the principal of the new
store C11 and BD011 the principal of the new store D01, whose secondary is
MCD01. After the upload, ingest (`construir_cache` +
`_resolver_sucursal_de_bodega`) must resolve every code to its new store,
whatever the order of the rows.
"""
import os
import random
import string
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.services.ingesta import resolucion

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

USER_ID = None  # `auditoria_maestro.usuario_id` is a real FK to `usuario`
# Store name -> its code (C.O.), the key the upload matches stores by.
_CODIGOS = {}


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    # Same session settings as production (`database.py`): autoflush off.
    fabrica = async_sessionmaker(
        motor, expire_on_commit=False, autoflush=False
    )
    async with fabrica() as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


async def _codigo_de(db, nombre):
    """The C.O. of the store `nombre`: the same on every upload, and one
    no saved store holds the first time."""
    if nombre not in _CODIGOS:
        usados = set((await db.execute(
            select(Sucursal.codigo_co).where(Sucursal.codigo_co.isnot(None))
        )).scalars().all()) | set(_CODIGOS.values())
        codigo = None
        while codigo is None or codigo in usados:
            codigo = random.choice(string.ascii_uppercase) + (
                f"{random.randint(0, 99):02d}"
            )
        _CODIGOS[nombre] = codigo
    return _CODIGOS[nombre]


async def _subir(db, filas):
    filas = [
        {**fila, "codigo_co": await _codigo_de(db, fila["nombre"])}
        for fila in filas
    ]
    resultado = await _resolver_y_procesar_carga(
        db, "sucursal", filas, USER_ID
    )
    assert resultado.ok is True, resultado.errores
    await db.flush()


def _fila(nombre, principal, secundarias):
    return {
        "nombre": nombre, "bodega_principal": principal,
        "bodegas_secundarias": secundarias,
    }


async def _id_de(db, nombre):
    return (await db.execute(
        select(Sucursal.id).where(Sucursal.nombre == nombre)
    )).scalar_one()


async def _resueltas(db, codigos):
    """code -> the store ingest resolves it to, through the same cache
    ingest builds (`construir_cache` follows each bodega chain with
    `_resolver_sucursal_de_bodega`)."""
    cache = await resolucion.construir_cache(db)
    return {
        codigo: resolucion.resolver_sucursal_por_codigo_o_nombre(
            cache, codigo, None
        )
        for codigo in codigos
    }


@pytest.mark.parametrize("orden", [1, -1])
async def test_owner_scenario_resolves_every_code_to_its_new_store(
    sesion, orden,
):
    s = uuid.uuid4().hex[:5].upper()
    a16, a07, c11, d01 = (f"{n} {s}" for n in ("A16", "A07", "C11", "D01"))
    ba071, ba161, bc111, bd011, mcd01 = (
        f"{c}{s}" for c in ("BA071", "BA161", "BC111", "BD011", "MCD01")
    )
    await _subir(sesion, [
        _fila(a16, ba071, f"{ba161}, {bc111}, {bd011}"),
    ])

    await _subir(sesion, [
        _fila(a16, ba161, ""),
        _fila(a07, ba071, ""),
        _fila(c11, bc111, ""),
        _fila(d01, bd011, mcd01),
    ][::orden])

    resueltas = await _resueltas(
        sesion, [ba071, ba161, bc111, bd011, mcd01]
    )
    assert resueltas == {
        ba071: await _id_de(sesion, a07),
        ba161: await _id_de(sesion, a16),
        bc111: await _id_de(sesion, c11),
        bd011: await _id_de(sesion, d01),
        mcd01: await _id_de(sesion, d01),
    }


async def test_the_principal_record_is_created_as_the_root(sesion):
    s = uuid.uuid4().hex[:5].upper()
    nombre, principal = f"NUEVA {s}", f"P{s}"

    await _subir(sesion, [_fila(nombre, principal, "")])

    bodega = (await sesion.execute(
        select(Bodega).where(Bodega.codigo == principal)
    )).scalar_one()
    assert (bodega.sucursal_id, bodega.bodega_principal) == (
        await _id_de(sesion, nombre), None
    )
