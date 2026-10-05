"""
Associated stores (`sucursal.principal_id`) against a real Postgres.

Runs only with `MOTORED_TEST_PG_URL` pointing at a database migrated with
`alembic -c alembic_motored.ini upgrade head`. Each test works inside a
transaction rolled back at the end (`commit()` is degraded to `flush()`).

Covers what the doubles cannot: the CHECK against a self-reference, the FK
against a missing store and its ON DELETE RESTRICT, the insert order when a
file links a store to a principal created further down the same file, and
the group helpers on real rows.
"""
import os
import uuid

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.sucursal import Sucursal
from app.motored.services import sucursal_grupo

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


async def _crear(sesion, nombre, principal_id=None):
    sucursal = Sucursal(
        id=uuid.uuid4(), nombre=nombre, principal_id=principal_id,
    )
    sesion.add(sucursal)
    await sesion.flush()
    return sucursal


async def _por_nombre(sesion, nombre):
    return (await sesion.execute(
        select(Sucursal).where(Sucursal.nombre == nombre)
    )).scalars().first()


async def test_check_rejects_a_self_reference(sesion):
    sucursal = await _crear(sesion, f"PROPIA {_sufijo()}")

    with pytest.raises(IntegrityError, match="ck_sucursal_principal"):
        await sesion.execute(
            update(Sucursal).where(Sucursal.id == sucursal.id)
            .values(principal_id=sucursal.id)
        )


async def test_fk_rejects_a_missing_principal(sesion):
    with pytest.raises(IntegrityError, match="fk_sucursal_principal_id"):
        await _crear(sesion, f"HUERFANA {_sufijo()}", uuid.uuid4())


async def test_fk_restricts_deleting_a_principal_with_associates(sesion):
    s = _sufijo()
    principal = await _crear(sesion, f"LA 33 {s}")
    await _crear(sesion, f"EXPO {s}", principal.id)

    with pytest.raises(IntegrityError, match="fk_sucursal_principal_id"):
        await sesion.execute(
            delete(Sucursal).where(Sucursal.id == principal.id)
        )


async def test_upload_links_to_a_principal_created_later_in_the_file(
    sesion,
):
    s = _sufijo()
    filas = [
        {"nombre": f"EXPO {s}", "sucursal_principal": f"nueva {s}"},
        {"nombre": f"NUEVA {s}", "sucursal_principal": ""},
    ]

    resultado = await _resolver_y_procesar_carga(
        sesion, "sucursal", filas, USER_ID
    )
    await sesion.flush()

    assert resultado.ok is True
    nueva = await _por_nombre(sesion, f"NUEVA {s}")
    assert (await _por_nombre(sesion, f"EXPO {s}")).principal_id == nueva.id
    assert nueva.principal_id is None


async def test_upload_rejects_a_chain_against_the_database(sesion):
    s = _sufijo()
    principal = await _crear(sesion, f"LA 33 {s}")
    await _crear(sesion, f"EXPO 1 {s}", principal.id)

    resultado = await _resolver_y_procesar_carga(
        sesion, "sucursal",
        [{"nombre": f"EXPO 2 {s}", "sucursal_principal": f"EXPO 1 {s}"}],
        USER_ID,
    )

    assert resultado.ok is False
    assert await _por_nombre(sesion, f"EXPO 2 {s}") is None


async def test_group_helpers_on_real_rows(sesion):
    s = _sufijo()
    principal = await _crear(sesion, f"LA 33 {s}")
    asociada = await _crear(sesion, f"EXPO {s}", principal.id)

    mapa = await sucursal_grupo.principal_de(sesion)
    efectivo = (await sesion.execute(
        select(sucursal_grupo.principal_efectivo_expr())
        .where(Sucursal.id == asociada.id)
    )).scalar_one()

    assert mapa[asociada.id] == principal.id
    assert mapa[principal.id] == principal.id
    assert sucursal_grupo.grupo_de(mapa, principal.id) == [
        principal.id, asociada.id,
    ]
    assert efectivo == principal.id
