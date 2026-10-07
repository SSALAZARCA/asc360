"""
`ultima_fecha_venta` against a real Postgres (odd/motored-kpis-velocidad, S3): the date of the latest loaded
sale of a month, with the same answer as the plain `max(fecha)` it replaced, and the index it relies on.
"""
import datetime

import pytest
from sqlalchemy import func, select, text

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores_consultas as q
from tests.motored.pg_real.test_kpi_resumen_pg import URL, Mundo, pytestmark, sesion  # noqa: F401

D = datetime.date


async def _mundo(db):
    """Mundo's sales are in 2097-01..03; add days to the stores, an ANULADO carga with the newest day."""
    mundo = await Mundo().crear(db)
    for suc, ref, vend, mes, dia, nro, carga in [
        (mundo.s2, "R1", "ANA", 2, 27, "Z1", mundo.c_venta),
        (mundo.s1, "R1", "ANA", 2, 28, "Z2", mundo.c_anulada),  # the newest of February, but ANULADO
        (mundo.s1, "R1", "ANA", 3, 31, "Z3", mundo.c_mar),
    ]:
        await mundo.linea(db, suc, ref, vend, "Taller X", mes, dia, nro, 1, 10, 0, "VENTA", carga)
    await db.flush()
    return mundo


async def _referencia(db, mes, sucursales=None, hasta=None):
    """The plain `max(fecha)` of the not ANULADO sales of the month, the way the function used to ask."""
    inicio = D(int(mes[:4]), int(mes[5:]), 1)
    fin = (inicio + datetime.timedelta(days=32)).replace(day=1)
    consulta = (
        select(func.max(VentaDetalle.fecha)).select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .where(CargaArchivo.estado != "ANULADO", VentaDetalle.fecha >= inicio, VentaDetalle.fecha < fin))
    if sucursales:
        consulta = consulta.where(VentaDetalle.sucursal_id.in_(sucursales))
    if hasta is not None:
        consulta = consulta.where(VentaDetalle.fecha <= hasta)
    return (await db.execute(consulta)).scalar()


async def test_the_latest_sale_of_a_month_is_the_plain_maximum(sesion):
    mundo = await _mundo(sesion)
    s1, s2 = mundo.s1.id, mundo.s2.id
    casos = [
        ("2097-01", None, None), ("2097-01", [s1], None), ("2097-01", [s2], None), ("2097-01", [s1, s2], None),
        ("2097-02", None, None), ("2097-02", [s1], None), ("2097-02", [s2], None),  # ANULADO day does not count
        ("2097-03", None, None), ("2097-03", [s1], None), ("2097-03", [s2], D(2097, 3, 13)),
        ("2097-03", None, D(2097, 3, 13)), ("2097-03", None, D(2097, 3, 2)), ("2097-03", [s1], D(2097, 3, 1)),
        ("2097-04", None, None), ("2097-12", [s1], None), ("2096-12", None, D(2097, 1, 1)),
    ]
    for mes, tiendas, hasta in casos:
        esperado = await _referencia(sesion, mes, tiendas, hasta)
        assert await q.ultima_fecha_venta(sesion, mes, tiendas, hasta) == esperado, (mes, tiendas, hasta)

    assert await q.ultima_fecha_venta(sesion, "2097-02") == D(2097, 2, 27)  # not the ANULADO 28th
    assert await q.ultima_fecha_venta(sesion, "2097-03") == D(2097, 3, 31)
    assert await q.ultima_fecha_venta(sesion, "2097-04") is None


async def test_the_database_has_the_date_index(sesion):
    nombres = (await sesion.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'venta_detalle'"))).scalars().all()
    assert "ix_venta_detalle_fecha" in nombres
