"""The world of the Inventario tab tests with the summaries built (shared by the summary tests)."""
import uuid
from decimal import Decimal as D

from sqlalchemy import select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.services import kpi_resumen as k
from tests.motored.pg_real.test_tablero_kpis_inventario_pg import C_OCT_EXTRA, _mundo


async def _carga_de_inventario(db):
    filas = await db.execute(select(CargaArchivo).where(
        CargaArchivo.tipo == "INVENTARIO", CargaArchivo.estado == "APLICADO"))
    return filas.scalars().first()


async def mundo_con_resumen(db, **opciones):
    """`_mundo` + an earlier corte in the month of the latest one (not a closing cut) + a full rebuild."""
    w = await _mundo(db, **opciones)
    carga = await _carga_de_inventario(db)
    db.add(InventarioDetalle(
        id=uuid.uuid4(), carga_id=carga.id, fecha_corte=C_OCT_EXTRA, sucursal_id=w.s["S1"].id,
        referencia_id=w.refs["R1"].id, bodega="B1", existencia=D(77), costo_unitario=D(10)))
    await db.flush()
    await k.reconstruir_todo(db)
    return w
