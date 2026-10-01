"""
CLIENTES TECNIRED contra un Postgres real (opt-in).

Corre solo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transaccion que se revierte al final (los
`commit()` del codigo bajo prueba se degradan a `flush()`).

Cubre lo que los dobles no pueden: que la carga REEMPLAZA la lista completa,
que un archivo invalido deja la lista anterior intacta, y que un fallo de la
base a mitad del reemplazo (despues del DELETE) revierte el DELETE tambien.
"""
import os

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.services import carga, maestros

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


async def _lista(db):
    filas = (await db.execute(select(ClienteTecnired))).scalars().all()
    return {f.nit: f.razon_social for f in filas}


async def _sembrar(db, **nits):
    # Parte de una lista vacia: el reemplazo borra todo lo que hubiera.
    await carga.procesar_carga(
        db, "cliente_tecnired", [{"nit": n, "razon_social": r} for n, r in nits.items()])


async def test_la_carga_reemplaza_la_lista_completa(sesion):
    await _sembrar(sesion, **{"900111": "VIEJA A", "900222": "VIEJA B"})

    resultado = await carga.procesar_carga(
        sesion, "cliente_tecnired",
        [{"nit": "900222.", "razon_social": "NUEVA B"}, {"nit": "900333"}])

    assert resultado.ok and resultado.insertados == 2 and resultado.eliminados == 2
    assert await _lista(sesion) == {"900222": "NUEVA B", "900333": None}


async def test_un_archivo_invalido_deja_la_lista_anterior_intacta(sesion):
    await _sembrar(sesion, **{"900111": "A", "900222": "B"})

    resultado = await carga.procesar_carga(
        sesion, "cliente_tecnired", [{"nit": "900999"}, {"nit": "  "}])

    assert resultado.ok is False
    assert await _lista(sesion) == {"900111": "A", "900222": "B"}


async def test_un_archivo_sin_filas_no_borra_la_lista(sesion):
    await _sembrar(sesion, **{"900111": "A"})

    resultado = await carga.procesar_carga(sesion, "cliente_tecnired", [])

    assert resultado.ok is False
    assert await _lista(sesion) == {"900111": "A"}


async def test_un_fallo_de_la_base_despues_del_delete_revierte_el_delete(sesion):
    await _sembrar(sesion, **{"900111": "A", "900222": "B"})

    # Salta la validacion a proposito: un NIT mas largo que la columna rompe
    # el INSERT DESPUES de que el DELETE ya se ejecuto en la transaccion.
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await maestros.reemplazar_clientes_tecnired(
                sesion, [{"nit": "X" * 60}], None)
            await sesion.flush()

    assert await _lista(sesion) == {"900111": "A", "900222": "B"}
