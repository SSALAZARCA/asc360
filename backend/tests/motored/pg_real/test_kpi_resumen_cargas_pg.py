"""
KPI summaries and the VENTAS cargas (odd/motored-kpis-resumenes, R6) against a real Postgres
(opt-in, database migrated to head).

Applying a VENTAS carga refreshes the summaries of the (sucursal, anio, mes) keys it touches
and annulling one refreshes the months it had; both inside the carga's own transaction and only
once the summaries were fully built at least once. The acceptance criterion: after every
operation the incrementally refreshed summaries equal a full rebuild from `venta_detalle`.
Every test rolls back.
"""
import pytest
from sqlalchemy import select

from app.motored.api import cargas as cargas_api
from app.motored.models.kpi_resumen import (
    KpiClienteMes, KpiFacturaFirma, KpiResumenEstado, KpiVentaMes,
)
from app.motored.services import kpi_resumen as k
from tests.motored.pg_real.test_venta_detalle_pg import (
    SEP, AGO_SEP, _aplicar, _mundo, _staging, pytestmark, sesion,  # noqa: F401
)

TABLAS = (KpiVentaMes, KpiFacturaFirma, KpiClienteMes)


async def _resumenes(db):
    """Every summary row without its surrogate key, as comparable sorted tuples."""
    instantanea = {}
    for modelo in TABLAS:
        columnas = [c for c in modelo.__table__.columns if c.name != "id"]
        filas = (await db.execute(select(*columnas))).all()
        instantanea[modelo.__tablename__] = sorted(tuple(map(str, fila)) for fila in filas)
    return instantanea


async def _igual_a_una_reconstruccion(db):
    refrescado = await _resumenes(db)
    await k.reconstruir_todo(db)
    assert refrescado == await _resumenes(db)
    return refrescado


async def _construido(db):
    sucursales, referencia, cargas = await _mundo(db)
    await k.reconstruir_todo(db)
    return sucursales, referencia, cargas


async def test_applying_a_carga_refreshes_the_summaries_of_its_keys(sesion):
    (a, b), ref, (c1, *_) = await _construido(sesion)

    await _aplicar(sesion, c1, [
        _staging(c1, a, ref, 8, 5, "AGO-A"), _staging(c1, a, ref, 9, 1, "SEP-A1"),
        _staging(c1, a, ref, 9, 2, "SEP-A2", vendedor="José Núñez", bruto="-500"),
        _staging(c1, b, ref, 9, 3, "SEP-B"),
    ], *AGO_SEP)

    resumenes = await _igual_a_una_reconstruccion(sesion)
    assert len(resumenes["kpi_venta_mes"]) >= 3 and resumenes["kpi_factura_firma"]


async def test_reuploading_replaces_the_summary_rows_of_the_replaced_months(sesion):
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await _aplicar(sesion, c1, [
        _staging(c1, a, ref, 8, 5, "AGO-A"), _staging(c1, a, ref, 9, 1, "SEP-A1"),
        _staging(c1, b, ref, 9, 3, "SEP-B"),
    ], *AGO_SEP)
    antes = await _resumenes(sesion)

    await _aplicar(sesion, c2, [_staging(c2, a, ref, 9, 4, "SEP-A3", bruto="250")], *SEP)

    despues = await _igual_a_una_reconstruccion(sesion)
    assert despues != antes
    # The other month of the same store and the other store keep their rows.
    assert sum("2026-08-01" in fila[0] for fila in despues["kpi_venta_mes"]) == 1


async def test_annulling_a_carga_removes_its_rows_from_the_summaries(sesion, monkeypatch):
    monkeypatch.setattr(sesion, "commit", sesion.flush)  # `anular_carga` commits; the fixture rolls back
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await _aplicar(sesion, c1, [_staging(c1, a, ref, 8, 5, "AGO-A")], *AGO_SEP)
    await _aplicar(sesion, c2, [_staging(c2, a, ref, 9, 1, "SEP-A1"), _staging(c2, b, ref, 9, 3, "SEP-B")], *SEP)
    c1.estado = c2.estado = "APLICADO"
    await sesion.flush()
    assert len((await _resumenes(sesion))["kpi_venta_mes"]) == 3

    await cargas_api.anular_carga(c2.id, db=sesion, user=None)

    resumenes = await _igual_a_una_reconstruccion(sesion)
    assert [fila[0] for fila in resumenes["kpi_venta_mes"]] == ["2026-08-01"]  # only the August of c1 is left
    assert all("2026-09" not in fila[0] for fila in resumenes["kpi_factura_firma"])


async def test_annulling_a_carga_without_lines_changes_nothing(sesion, monkeypatch):
    monkeypatch.setattr(sesion, "commit", sesion.flush)
    (a, _), ref, (c1, c2, _) = await _construido(sesion)
    await _aplicar(sesion, c1, [_staging(c1, a, ref, 9, 1, "SEP-A1")], *SEP)
    antes = await _resumenes(sesion)

    await cargas_api.anular_carga(c2.id, db=sesion, user=None)  # a carga that never applied a line

    assert c2.estado == "ANULADO" and await _resumenes(sesion) == antes


async def test_nothing_is_refreshed_until_the_summaries_were_built_once(sesion):
    (a, _), ref, (c1, *_) = await _mundo(sesion)

    await _aplicar(sesion, c1, [_staging(c1, a, ref, 9, 1, "SEP-A1")], *SEP)

    assert all(not filas for filas in (await _resumenes(sesion)).values())
    assert (await sesion.execute(select(KpiResumenEstado))).first() is None
    await k.reconstruir_todo(sesion)  # the first full build includes the carga
    assert (await _resumenes(sesion))["kpi_venta_mes"]


async def test_a_failed_refresh_fails_the_apply(sesion, monkeypatch):
    (a, _), ref, (c1, *_) = await _construido(sesion)

    async def falla(db, claves):
        raise RuntimeError("summary refresh failed")

    monkeypatch.setattr(k, "refrescar_periodos", falla)

    with pytest.raises(RuntimeError, match="summary refresh failed"):
        await _aplicar(sesion, c1, [_staging(c1, a, ref, 9, 1, "SEP-A1")], *SEP)
