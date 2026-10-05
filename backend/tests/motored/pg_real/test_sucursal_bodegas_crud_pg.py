"""
Sucursales form (CRUD): a store's bodegas, against a real Postgres
(opt-in, `MOTORED_TEST_PG_URL` on a database migrated with
`alembic -c alembic_motored.ini upgrade head`). Each test runs inside a
transaction rolled back at the end.

The save mirrors the route (`api/maestros.py`): the store is created or
updated, then `bodegas_secundarias.guardar_de_sucursal` saves its
secondaries and syncs its principal's record. Ingest (`construir_cache`)
must then resolve every code to the store, including after a
principal/secondary swap done in ONE save.
"""
import os
import random
import string
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import SucursalCreate, SucursalUpdate
from app.motored.services import bodegas_secundarias, maestros
from app.motored.services.ingesta import resolucion

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

USER_ID = None  # `auditoria_maestro.usuario_id` is a real FK to `usuario`


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _codigo_co_libre(db):
    usados = set((await db.execute(
        select(Sucursal.codigo_co).where(Sucursal.codigo_co.isnot(None))
    )).scalars().all())
    codigo = None
    while codigo is None or codigo in usados:
        codigo = random.choice(string.ascii_uppercase) + (
            f"{random.randint(0, 99):02d}"
        )
    return codigo


async def _crear(db, nombre, principal, secundarias):
    sucursal = await maestros.create_sucursal(db, SucursalCreate(
        nombre=nombre, codigo_co=await _codigo_co_libre(db),
        bodega_principal=principal,
    ), USER_ID)
    await bodegas_secundarias.guardar_de_sucursal(
        db, sucursal, secundarias, USER_ID
    )
    await db.flush()
    return sucursal


async def _resueltas(db, codigos):
    cache = await resolucion.construir_cache(db)
    return {
        codigo: resolucion.resolver_sucursal_por_codigo_o_nombre(
            cache, codigo, None
        )
        for codigo in codigos
    }


async def _estado(db, codigo):
    bodega = (await db.execute(
        select(Bodega).where(Bodega.codigo == codigo)
    )).scalar_one()
    return bodega.sucursal_id, bodega.bodega_principal


async def test_swap_in_one_save_resolves_both_codes_to_the_store(sesion):
    s = uuid.uuid4().hex[:5].upper()
    ba071, ba161 = f"BA071{s}", f"BA161{s}"
    tienda = await _crear(sesion, f"QUILICHAO {s}", ba071, [ba161])

    await maestros.update_sucursal(
        sesion, tienda, SucursalUpdate(bodega_principal=ba161), USER_ID
    )
    await bodegas_secundarias.guardar_de_sucursal(
        sesion, tienda, [ba071.lower()], USER_ID
    )
    await sesion.flush()

    assert await _estado(sesion, ba161) == (tienda.id, None)
    assert await _estado(sesion, ba071) == (tienda.id, ba161)
    assert await _resueltas(sesion, [ba071, ba161]) == {
        ba071: tienda.id, ba161: tienda.id,
    }


async def test_removed_secondary_is_released(sesion):
    s = uuid.uuid4().hex[:5].upper()
    principal, secundaria = f"BP{s}", f"MC{s}"
    tienda = await _crear(sesion, f"TIENDA {s}", principal, [secundaria])

    await bodegas_secundarias.guardar_de_sucursal(
        sesion, tienda, [], USER_ID
    )
    await sesion.flush()

    assert await _estado(sesion, secundaria) == (None, None)
    assert await _resueltas(sesion, [principal]) == {principal: tienda.id}


async def test_code_of_another_store_is_rejected_naming_it(sesion):
    s = uuid.uuid4().hex[:5].upper()
    otra = await _crear(sesion, f"PASTO {s}", f"BP{s}", [f"MC{s}"])
    tienda = await _crear(sesion, f"CALI {s}", f"BC{s}", [])

    with pytest.raises(
        bodegas_secundarias.BodegasSecundariasInvalidasError
    ) as exc:
        await bodegas_secundarias.guardar_de_sucursal(
            sesion, tienda, [f"MC{s}", f"BP{s}"], USER_ID
        )

    assert f"'{otra.nombre}'" in str(exc.value)
    assert await _estado(sesion, f"MC{s}") == (otra.id, f"BP{s}")
