"""
A store's PRINCIPAL bodega must not belong to another store, against a
real Postgres (opt-in, database migrated to head; each test rolls back).

Before, the upload and the form accepted a principal another store owned
(as its principal or as a secondary record), and the principal sync then
moved that record silently, so the other store lost the bodega and its
inventory. Now both reject it naming the store, unless the same file or
save releases it, validated on the final state so swaps still work. A raw
`principal_id` in a JSON upload row never associates stores.
"""
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import SucursalUpdate
from app.motored.services import bodegas_secundarias, maestros
from tests.motored.pg_real.codigos_co import codigo_co_unico

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


def _motivo(codigo, nombre):
    return (
        f"La bodega {codigo} ya es de la sucursal {nombre}. Quítela de "
        "esa sucursal primero o muévala con la carga masiva."
    )


async def _tienda(sesion, principal, secundarias=()):
    """A saved store with its principal and secondary records."""
    s = uuid.uuid4().hex[:6].upper()
    tienda = Sucursal(
        id=uuid.uuid4(), nombre=f"TIENDA {s}", codigo_co=codigo_co_unico(),
        bodega_principal=principal,
    )
    sesion.add(tienda)
    await sesion.flush()
    await bodegas_secundarias.guardar_de_sucursal(
        sesion, tienda, list(secundarias), USER_ID
    )
    await sesion.flush()
    return tienda


def _fila(tienda, principal, **extra):
    return {
        "nombre": tienda.nombre, "codigo_co": tienda.codigo_co,
        "bodega_principal": principal, **extra,
    }


def _nueva(principal, **extra):
    s = uuid.uuid4().hex[:6].upper()
    return {
        "nombre": f"NUEVA {s}", "codigo_co": codigo_co_unico(),
        "bodega_principal": principal, **extra,
    }


async def _subir(sesion, *filas):
    return await _resolver_y_procesar_carga(
        sesion, "sucursal", list(filas), USER_ID
    )


async def _duena(sesion, codigo):
    return (await sesion.execute(
        select(Bodega.sucursal_id).where(Bodega.codigo == codigo)
    )).scalar_one()


def _codigo(prefijo):
    return f"{prefijo}{uuid.uuid4().hex[:6].upper()}"


class TestUpload:
    async def test_another_stores_principal_is_rejected(self, sesion):
        p = _codigo("P")
        duena = await _tienda(sesion, p)

        resultado = await _subir(sesion, _nueva(p))

        assert resultado.ok is False
        assert [e.motivo for e in resultado.errores] == [
            _motivo(p, duena.nombre)
        ]
        assert await _duena(sesion, p) == duena.id

    async def test_another_stores_secondary_is_rejected(self, sesion):
        p, sec = _codigo("P"), _codigo("S")
        duena = await _tienda(sesion, p, [sec])

        resultado = await _subir(sesion, _nueva(sec))

        assert [e.motivo for e in resultado.errores] == [
            _motivo(sec, duena.nombre)
        ]

    async def test_two_rows_with_one_principal_are_rejected(self, sesion):
        p = _codigo("P")
        a, b = _nueva(p), _nueva(p)

        resultado = await _subir(sesion, a, b)

        assert [(e.fila, e.motivo) for e in resultado.errores] == [
            (1, _motivo(p, b["nombre"])), (2, _motivo(p, a["nombre"])),
        ]

    async def test_the_file_may_release_a_principal(self, sesion):
        p, q = _codigo("P"), _codigo("Q")
        vieja = await _tienda(sesion, p)
        nueva = _nueva(p)

        resultado = await _subir(sesion, _fila(vieja, q), nueva)

        assert resultado.ok is True, resultado.errores
        nueva_id = (await sesion.execute(select(Sucursal.id).where(
            Sucursal.nombre == nueva["nombre"]
        ))).scalar_one()
        assert await _duena(sesion, p) == nueva_id

    async def test_the_file_may_release_a_secondary(self, sesion):
        p, sec = _codigo("P"), _codigo("S")
        vieja = await _tienda(sesion, p, [sec])

        resultado = await _subir(
            sesion, _fila(vieja, p, bodegas_secundarias=""), _nueva(sec)
        )

        assert resultado.ok is True, resultado.errores

    async def test_two_stores_may_swap_principals(self, sesion):
        p, q = _codigo("P"), _codigo("Q")
        a = await _tienda(sesion, p)
        b = await _tienda(sesion, q)

        resultado = await _subir(sesion, _fila(a, q), _fila(b, p))

        assert resultado.ok is True, resultado.errores
        assert (await _duena(sesion, q), await _duena(sesion, p)) == (
            a.id, b.id,
        )

    async def test_a_raw_principal_id_never_associates(self, sesion):
        principal = await _tienda(sesion, _codigo("P"))
        nueva = _nueva(_codigo("N"), principal_id=str(principal.id))

        resultado = await _subir(sesion, nueva)

        assert resultado.ok is True, resultado.errores
        guardada = (await sesion.execute(select(Sucursal.principal_id).where(
            Sucursal.nombre == nueva["nombre"]
        ))).scalar_one()
        assert guardada is None


class TestForm:
    async def test_another_stores_principal_is_rejected(self, sesion):
        p = _codigo("P")
        duena = await _tienda(sesion, p)
        tienda = await _tienda(sesion, _codigo("Q"))
        await maestros.update_sucursal(
            sesion, tienda, SucursalUpdate(bodega_principal=p), USER_ID
        )

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError
        ) as error:
            await bodegas_secundarias.guardar_de_sucursal(
                sesion, tienda, None, USER_ID
            )

        assert str(error.value) == _motivo(p, duena.nombre)

    async def test_another_stores_secondary_is_rejected(self, sesion):
        p, sec = _codigo("P"), _codigo("S")
        duena = await _tienda(sesion, p, [sec])
        tienda = await _tienda(sesion, _codigo("Q"))
        await maestros.update_sucursal(
            sesion, tienda, SucursalUpdate(bodega_principal=sec), USER_ID
        )

        with pytest.raises(
            bodegas_secundarias.BodegasSecundariasInvalidasError
        ) as error:
            await bodegas_secundarias.guardar_de_sucursal(
                sesion, tienda, [], USER_ID
            )

        assert str(error.value) == _motivo(sec, duena.nombre)

    async def test_its_own_secondary_may_become_the_principal(self, sesion):
        p, sec = _codigo("P"), _codigo("S")
        tienda = await _tienda(sesion, p, [sec])
        await maestros.update_sucursal(
            sesion, tienda, SucursalUpdate(bodega_principal=sec), USER_ID
        )

        await bodegas_secundarias.guardar_de_sucursal(
            sesion, tienda, [p], USER_ID
        )
        await sesion.flush()

        assert (await _duena(sesion, sec), await _duena(sesion, p)) == (
            tienda.id, tienda.id,
        )
