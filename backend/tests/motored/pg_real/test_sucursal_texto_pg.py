"""Store-text resolver against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`)."""
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal
from app.motored.services.sucursal_texto import sucursal_id_por_texto

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


def _co():
    return "Y" + str(int(uuid.uuid4().hex[:6], 16) % 100).zfill(2)


async def test_codigo_co_resolves_first_then_name_then_alias(sesion):
    sfx = uuid.uuid4().hex[:8].upper()
    co = _co()
    cali = Sucursal(id=uuid.uuid4(), nombre=f"Cali {sfx}", sic=f"C-{sfx}", codigo_co=co)
    # A store whose NAME is another store's C.O. must not steal it.
    impostora = Sucursal(id=uuid.uuid4(), nombre=co, sic=f"I-{sfx}")
    sesion.add_all([cali, impostora])
    await sesion.flush()
    sesion.add(SucursalAlias(id=uuid.uuid4(), texto_normalizado=f"SEDE VIEJA {sfx}", sucursal_id=cali.id))
    await sesion.flush()

    mapa = await sucursal_id_por_texto(sesion)

    assert mapa[normalizar_texto_sucursal(co)] == cali.id
    assert mapa[normalizar_texto_sucursal(co.lower())] == cali.id
    assert mapa[normalizar_texto_sucursal(f"cali {sfx}")] == cali.id
    assert mapa[f"SEDE VIEJA {sfx}"] == cali.id
    assert "Z00NOEXISTE" not in mapa
