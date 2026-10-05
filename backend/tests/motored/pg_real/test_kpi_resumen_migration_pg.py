"""
KPI summary tables (R1) against a real Postgres (opt-in, database migrated to
head): the tables, the indexes and the constraints that doubles cannot show.
Every test rolls back.
"""
import datetime
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.sucursal import Sucursal

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

ENERO = datetime.date(2097, 1, 1)
TABLAS = (
    "kpi_venta_mes", "kpi_factura_firma", "kpi_cliente_mes", "kpi_costo_referencia", "kpi_inventario_corte",
    "kpi_resumen_estado",
)
INSERT_VENTA = text(
    "INSERT INTO kpi_venta_mes (anio_mes, sucursal_id, vendedor_norm, linea_norm, nit_especial, es_mostrador, "
    "con_costo, venta, bruto, descuentos, cantidad, lineas, costo, costo_estimado) "
    "VALUES (:mes, :s, 'ANA', :linea, NULL, true, false, 1, 1, 0, 1, 1, 0, 0)")


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _sucursal(db):
    sfx = uuid.uuid4().hex[:8].upper()
    sucursal = Sucursal(id=uuid.uuid4(), nombre=f"Kpi {sfx}", sic=f"K-{sfx}")
    db.add(sucursal)
    await db.flush()
    return sucursal.id


async def test_all_tables_exist_with_their_indexes(sesion):
    tablas = (await sesion.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_name = ANY(:t)"), {"t": list(TABLAS)}))
    indices = (await sesion.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'kpi\\_%'")))

    assert {t for (t,) in tablas.all()} == set(TABLAS)
    nombres = {i for (i,) in indices.all()}
    assert {"uq_kpi_venta_mes_llave", "uq_kpi_factura_firma_llave", "uq_kpi_cliente_mes_llave"} <= nombres


async def test_the_month_must_be_the_first_day(sesion):
    s = await _sucursal(sesion)

    with pytest.raises(IntegrityError, match="ck_kpi_venta_mes_dia_1"):
        await sesion.execute(INSERT_VENTA, {"mes": datetime.date(2097, 1, 2), "s": s, "linea": "GPS"})


async def test_the_key_is_unique_even_when_nullable_parts_are_null(sesion):
    s = await _sucursal(sesion)
    await sesion.execute(INSERT_VENTA, {"mes": ENERO, "s": s, "linea": None})

    with pytest.raises(IntegrityError, match="uq_kpi_venta_mes_llave"):
        await sesion.execute(INSERT_VENTA, {"mes": ENERO, "s": s, "linea": None})


async def test_the_same_key_with_a_line_is_a_different_row(sesion):
    s = await _sucursal(sesion)

    await sesion.execute(INSERT_VENTA, {"mes": ENERO, "s": s, "linea": None})
    await sesion.execute(INSERT_VENTA, {"mes": ENERO, "s": s, "linea": "GPS"})


async def test_the_estado_table_holds_only_row_one(sesion):
    await sesion.execute(text("INSERT INTO kpi_resumen_estado (id) VALUES (1) ON CONFLICT DO NOTHING"))

    with pytest.raises(IntegrityError, match="ck_kpi_resumen_estado_fila_unica"):
        await sesion.execute(text("INSERT INTO kpi_resumen_estado (id) VALUES (2)"))
