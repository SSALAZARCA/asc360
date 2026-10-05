"""
The store code C.O. as the sucursal's business key, against a real
Postgres.

Runs only with `MOTORED_TEST_PG_URL` pointing at a database migrated with
`alembic -c alembic_motored.ini upgrade head`. Each test works inside a
transaction rolled back at the end (`commit()` is degraded to `flush()`).

Covers what the doubles cannot: `sucursal.nombre` is UNIQUE and NOT
deferrable, so a rename, two stores swapping names, and a new store taking
a name another store leaves must reach the database in an order Postgres
accepts. Also the first upload of codes (by name) and a rename together
with a bodega move and an association in one file.
"""
import os
import random
import string
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal

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


async def _crear(sesion, nombre, codigo_co=None, bodega_principal=None):
    sucursal = Sucursal(
        id=uuid.uuid4(), nombre=nombre, codigo_co=codigo_co,
        bodega_principal=bodega_principal,
    )
    sesion.add(sucursal)
    await sesion.flush()
    return sucursal


async def _leer(sesion, sucursal_id):
    """(nombre, codigo_co, principal_id) as stored."""
    return tuple((await sesion.execute(
        select(Sucursal.nombre, Sucursal.codigo_co, Sucursal.principal_id)
        .where(Sucursal.id == sucursal_id)
    )).one())


async def _cuantas(sesion):
    return (await sesion.execute(
        select(func.count()).select_from(Sucursal)
    )).scalar_one()


async def _subir(sesion, *filas):
    resultado = await _resolver_y_procesar_carga(
        sesion, "sucursal", list(filas), USER_ID
    )
    await sesion.flush()
    return resultado


async def test_a_rename_updates_the_coded_store(sesion):
    (codigo,) = await _codigos_libres(sesion, 1)
    tienda = await _crear(sesion, f"VIEJA {_sufijo()}", codigo)
    antes = await _cuantas(sesion)
    nuevo = f"NUEVA {_sufijo()}"

    resultado = await _subir(sesion, {"nombre": nuevo, "codigo_co": codigo})

    assert resultado.ok is True, resultado.errores
    assert (resultado.insertados, resultado.actualizados) == (0, 1)
    assert await _leer(sesion, tienda.id) == (nuevo, codigo, None)
    assert await _cuantas(sesion) == antes


async def test_two_stores_swap_names_and_a_new_store_takes_a_left_name(
    sesion,
):
    primero, segundo, tercero = await _codigos_libres(sesion, 3)
    s = _sufijo()
    a = await _crear(sesion, f"A {s}", primero)
    b = await _crear(sesion, f"B {s}", segundo)
    c = await _crear(sesion, f"C {s}", tercero)
    (nuevo,) = await _codigos_libres(sesion, 1)  # a, b, c are saved

    resultado = await _subir(
        sesion,
        {"nombre": f"B {s}", "codigo_co": primero},
        {"nombre": f"A {s}", "codigo_co": segundo},
        {"nombre": f"C2 {s}", "codigo_co": tercero},
        {"nombre": f"C {s}", "codigo_co": nuevo},
    )

    assert resultado.ok is True, resultado.errores
    await sesion.execute(_INMEDIATA)
    assert (await _leer(sesion, a.id))[:2] == (f"B {s}", primero)
    assert (await _leer(sesion, b.id))[:2] == (f"A {s}", segundo)
    assert (await _leer(sesion, c.id))[:2] == (f"C2 {s}", tercero)
    creada = (await sesion.execute(
        select(Sucursal.codigo_co).where(Sucursal.nombre == f"C {s}")
    )).scalar_one()
    assert creada == nuevo


async def test_first_upload_fills_in_the_code_by_name(sesion):
    (codigo,) = await _codigos_libres(sesion, 1)
    tienda = await _crear(sesion, f"SIN CO {_sufijo()}")

    resultado = await _subir(
        sesion, {"nombre": tienda.nombre, "codigo_co": codigo.lower()}
    )

    assert resultado.ok is True, resultado.errores
    await sesion.execute(_INMEDIATA)
    assert await _leer(sesion, tienda.id) == (tienda.nombre, codigo, None)


async def test_rename_bodega_move_and_association_in_one_file(sesion):
    co_a, co_b = await _codigos_libres(sesion, 2)
    s = _sufijo()
    a = await _crear(sesion, f"A {s}", co_a, f"PA{s}")
    b = await _crear(sesion, f"B {s}", co_b, f"PB{s}")
    movida = Bodega(
        id=uuid.uuid4(), codigo=f"SA{s}", sucursal_id=a.id,
        bodega_principal=f"PA{s}",
    )
    sesion.add(movida)
    await sesion.flush()

    resultado = await _subir(
        sesion,
        {"nombre": f"A NUEVA {s}", "codigo_co": co_a,
         "bodega_principal": f"PA{s}", "bodegas_secundarias": ""},
        {"nombre": f"B {s}", "codigo_co": co_b,
         "bodega_principal": f"PB{s}", "bodegas_secundarias": f"SA{s}",
         "sucursal_principal": co_a},
    )

    assert resultado.ok is True, resultado.errores
    assert (await _leer(sesion, a.id))[0] == f"A NUEVA {s}"
    assert (await _leer(sesion, b.id))[2] == a.id
    fila = (await sesion.execute(
        select(Bodega.sucursal_id, Bodega.bodega_principal)
        .where(Bodega.codigo == f"SA{s}")
    )).one()
    assert tuple(fila) == (b.id, f"PB{s}")
