"""
`reemplaza_mes_completo` at the row level against a real Postgres (opt-in):
the apply empties `venta_detalle` + `venta_mensual` of EVERY store for the
months of the file and refreshes the KPI summaries of every purged
(store, month); the acceptance criterion is the one of the carga refresh
tests: the refreshed summaries equal a full rebuild. Every test rolls back.
"""
import datetime

import pytest
from sqlalchemy import select

from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services import kpi_resumen as k
from app.motored.services.ingesta import ventas
from tests.motored.pg_real.test_kpi_resumen_cargas_pg import (
    _construido, _igual_a_una_reconstruccion,
)
from tests.motored.pg_real.test_venta_detalle_pg import (  # noqa: F401
    SEP, AGO_SEP, _detalle, _staging, pytestmark, sesion,
)


async def _reemplazar(db, carga, filas, desde, hasta):
    veredicto = await ventas.aplicar_reemplazando_meses(
        db, filas, desde, hasta, carga.id)
    await db.flush()
    return veredicto


async def _meses_de(db, tienda):
    detalle = {(d.anio, d.mes, d.nro_documento) for d in await _detalle(db, tienda)}
    mensual = {
        (m.anio, m.mes) for m in (await db.execute(
            select(VentaMensual).where(
                VentaMensual.sucursal_id == tienda.id))).scalars()}
    return detalle, mensual


async def test_the_apply_empties_every_store_for_the_months_of_the_file(sesion):
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await ventas.aplicar_con_periodo(sesion, [
        _staging(c1, a, ref, 8, 5, "AGO-A"), _staging(c1, a, ref, 9, 1, "SEP-A"),
        _staging(c1, b, ref, 8, 6, "AGO-B"), _staging(c1, b, ref, 9, 2, "SEP-B"),
    ], *AGO_SEP, c1.id)
    await sesion.flush()

    # The new file only brings store A, September.
    await _reemplazar(sesion, c2, [_staging(c2, a, ref, 9, 3, "SEP-A-NUEVA")], *SEP)

    detalle_a, mensual_a = await _meses_de(sesion, a)
    detalle_b, mensual_b = await _meses_de(sesion, b)
    assert detalle_a == {(2026, 8, "AGO-A"), (2026, 9, "SEP-A-NUEVA")}
    assert mensual_a == {(2026, 8), (2026, 9)}
    # Store B loses September (the month of the file) and keeps August.
    assert detalle_b == {(2026, 8, "AGO-B")}
    assert mensual_b == {(2026, 8)}


async def test_the_kpi_summaries_of_the_purged_stores_are_refreshed(sesion):
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await ventas.aplicar_con_periodo(sesion, [
        _staging(c1, a, ref, 9, 1, "SEP-A"), _staging(c1, b, ref, 9, 2, "SEP-B"),
    ], *SEP, c1.id)
    await sesion.flush()
    await k.refrescar_si_construido(sesion, await k.claves_de_carga(sesion, c1.id))

    await _reemplazar(sesion, c2, [_staging(c2, a, ref, 9, 3, "SEP-A2")], *SEP)

    resumenes = await _igual_a_una_reconstruccion(sesion)
    assert resumenes["kpi_venta_mes"]
    assert not [fila for fila in resumenes["kpi_venta_mes"] if str(b.id) in fila]


async def test_refreshes_cover_the_purged_keys_the_file_did_not_bring(
        sesion, monkeypatch):
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await ventas.aplicar_con_periodo(sesion, [
        _staging(c1, a, ref, 9, 1, "SEP-A"), _staging(c1, b, ref, 9, 2, "SEP-B"),
    ], *SEP, c1.id)
    await sesion.flush()
    llamadas = []
    original = ventas.kpi_resumen.refrescar_si_construido

    async def espia(db, claves):
        llamadas.append(set(claves))
        return await original(db, claves)

    monkeypatch.setattr(ventas.kpi_resumen, "refrescar_si_construido", espia)

    await _reemplazar(sesion, c2, [_staging(c2, a, ref, 9, 3, "SEP-A2")], *SEP)

    assert {(a.id, 2026, 9)} in llamadas       # the file's own key (aplicar_detalle)
    assert {(b.id, 2026, 9)} in llamadas       # the store the file did not bring


async def test_a_rejected_period_purges_nothing(sesion):
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await ventas.aplicar_con_periodo(
        sesion, [_staging(c1, b, ref, 9, 2, "SEP-B")], *SEP, c1.id)
    await sesion.flush()

    # Declared September, but every row is from August: whole file rejected.
    veredicto = await _reemplazar(
        sesion, c2, [_staging(c2, a, ref, 8, 3, "AGO-A")], *SEP)

    assert veredicto.tipo.value == "RECHAZO"
    assert (await _meses_de(sesion, b))[0] == {(2026, 9, "SEP-B")}


async def test_an_empty_file_purges_nothing(sesion):
    (a, b), ref, (c1, c2, _) = await _construido(sesion)
    await ventas.aplicar_con_periodo(
        sesion, [_staging(c1, b, ref, 9, 2, "SEP-B")], *SEP, c1.id)
    await sesion.flush()

    await _reemplazar(sesion, c2, [], *SEP)

    assert (await _meses_de(sesion, b))[0] == {(2026, 9, "SEP-B")}
