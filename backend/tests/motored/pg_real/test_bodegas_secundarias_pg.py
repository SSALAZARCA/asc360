"""
Sucursales upload "Bodegas secundarias" contra un Postgres real (opt-in).

Corre solo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transaccion que se revierte al final (los
`commit()` del codigo bajo prueba se degradan a `flush()`).

Cubre lo que los dobles no pueden: que despues de subir la sucursal con sus
secundarias, una fila de VENTAS/INVENTARIO con el codigo de la secundaria
resuelve a la tienda (`construir_cache` + `resolver_sucursal_por_codigo_o_nombre`),
que el inventario de la principal y de la secundaria se consolida en una sola
clave, y que desvincular deja la bodega sin tienda sin borrarla.
"""
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.bodega import Bodega
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.sucursal import Sucursal
from app.motored.services.ingesta import inventario, resolucion

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

USER_ID = None  # `auditoria_maestro.usuario_id` is a real FK to `usuario`


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


def _fila(nombre, principal, secundarias=None):
    fila = {"nombre": nombre, "bodega_principal": principal}
    if secundarias is not None:
        fila["bodegas_secundarias"] = secundarias
    return fila


async def _subir(db, *filas):
    return await _resolver_y_procesar_carga(db, "sucursal", list(filas), USER_ID)


async def _bodega(db, codigo):
    return (await db.execute(select(Bodega).where(Bodega.codigo == codigo))).scalars().first()


async def _sucursal(db, nombre):
    return (await db.execute(select(Sucursal).where(Sucursal.nombre == nombre))).scalars().first()


def _staging(sucursal_id, referencia_id, existencia):
    return CargaFilaStaging(
        carga_id=uuid.uuid4(), fila=1, lote=1, sucursal_id=sucursal_id,
        referencia_id=referencia_id, payload={"existencia": existencia},
    )


async def test_la_secundaria_resuelve_a_la_tienda_y_el_inventario_se_consolida(sesion):
    s = _sufijo()
    nombre, principal, sec1, sec2 = f"TIENDA {s}", f"P{s}", f"A{s}", f"B{s}"

    resultado = await _subir(sesion, _fila(nombre, principal, f"{sec1}, {sec2}"))
    await sesion.flush()

    assert resultado.ok is True
    tienda = await _sucursal(sesion, nombre)
    for codigo in (sec1, sec2):
        bodega = await _bodega(sesion, codigo)
        assert bodega.sucursal_id == tienda.id
        assert bodega.bodega_principal == principal

    cache = await resolucion.construir_cache(sesion)
    assert resolucion.resolver_sucursal_por_codigo_o_nombre(cache, sec1, None) == tienda.id
    assert resolucion.resolver_sucursal_por_codigo_o_nombre(cache, sec2, "OTRO") == tienda.id

    referencia = uuid.uuid4()
    filas = [
        _staging(resolucion.resolver_sucursal_por_codigo_o_nombre(cache, sec1, None), referencia, "10"),
        _staging(resolucion.resolver_sucursal_por_codigo_o_nombre(cache, sec2, None), referencia, "5"),
    ]
    assert inventario.consolidar_existencias(filas) == {(tienda.id, referencia): Decimal("15")}


async def test_desvincular_deja_la_bodega_sin_tienda_y_no_la_borra(sesion):
    s = _sufijo()
    nombre, principal, sec1, sec2 = f"TIENDA {s}", f"P{s}", f"A{s}", f"B{s}"
    await _subir(sesion, _fila(nombre, principal, f"{sec1}, {sec2}"))
    await sesion.flush()

    resultado = await _subir(sesion, _fila(nombre, principal, sec2))
    await sesion.flush()

    quitada = await _bodega(sesion, sec1)
    assert quitada is not None
    assert quitada.sucursal_id is None and quitada.bodega_principal is None
    assert [v["bodega"] for v in resultado.bodegas_secundarias.desvinculadas] == [sec1]
    cache = await resolucion.construir_cache(sesion)
    assert resolucion.resolver_sucursal_por_codigo_o_nombre(cache, sec1, None) is None

    await _subir(sesion, _fila(nombre, principal, ""))
    await sesion.flush()
    assert (await _bodega(sesion, sec2)).sucursal_id is None


async def test_sin_la_columna_no_se_toca_nada(sesion):
    s = _sufijo()
    nombre, principal, sec = f"TIENDA {s}", f"P{s}", f"A{s}"
    await _subir(sesion, _fila(nombre, principal, sec))
    await sesion.flush()

    await _subir(sesion, _fila(nombre, principal))
    await sesion.flush()

    assert (await _bodega(sesion, sec)).sucursal_id == (await _sucursal(sesion, nombre)).id


async def test_una_bodega_de_otra_tienda_se_rechaza_sin_escribir(sesion):
    s = _sufijo()
    sec = f"A{s}"
    await _subir(sesion, _fila(f"UNO {s}", f"P1{s}", sec))
    await sesion.flush()

    resultado = await _subir(sesion, _fila(f"DOS {s}", f"P2{s}", sec))

    assert resultado.ok is False
    assert "Quítela primero" in resultado.errores[0].motivo
    assert await _sucursal(sesion, f"DOS {s}") is None


@pytest.mark.parametrize("destino_primero", [True, False])
async def test_mover_una_secundaria_de_tienda_en_una_sola_carga(
    sesion, destino_primero
):
    s = _sufijo()
    origen, destino, sec = f"ORIGEN {s}", f"DESTINO {s}", f"A{s}"
    await _subir(
        sesion, _fila(origen, f"P1{s}", sec), _fila(destino, f"P2{s}", "")
    )
    await sesion.flush()

    filas = [_fila(destino, f"P2{s}", sec), _fila(origen, f"P1{s}", "")]
    if not destino_primero:
        filas.reverse()
    resultado = await _subir(sesion, *filas)
    await sesion.flush()

    assert resultado.ok is True
    movida = await _bodega(sesion, sec)
    assert movida.sucursal_id == (await _sucursal(sesion, destino)).id
    assert movida.bodega_principal == f"P2{s}"
    assert resultado.bodegas_secundarias.desvinculadas == []
    cache = await resolucion.construir_cache(sesion)
    assert resolucion.resolver_sucursal_por_codigo_o_nombre(
        cache, sec, None
    ) == (await _sucursal(sesion, destino)).id
