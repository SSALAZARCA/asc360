"""
KPI summaries are marked dirty when their inputs change (odd/motored-kpis-resumenes, R7a)
against a real Postgres (opt-in, database migrated to head).

Every input a full rebuild depends on and that has no incremental refresh flags the state row
in the writer's own transaction, only once the summaries were built at least once: a
referencia's `linea_comercial` or `precio_normal` (single edit and Excel replace), the retention purge of inventory, the cliente_tecnired list, the
`hmcl_nits` / `lineas_comerciales` parameters and the INVENTARIO carga apply / annul. A write
that does not change the input flags nothing. Every test rolls back.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.motored.api import cargas as cargas_api
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.kpi_resumen import KpiResumenEstado
from app.motored.schemas.referencia import ReferenciaUpdate
from app.motored.services import kpi_resumen as k
from app.motored.services import maestros, parametros, reemplazo_referencias, retencion
from app.motored.services.ingesta import inventario as inventario_mod
from tests.motored.pg_real.test_inventario_detalle_pg import (  # noqa: F401
    CORTE, CORTE_VIEJO, URL, _aplicar, _carga, _mundo, _staging, pytestmark, sesion,
)


async def _sucio(db):
    """The `sucio` flag of the state row (None when there is no row)."""
    return (await db.execute(select(KpiResumenEstado.sucio))).scalar_one_or_none()


async def _construido(db):
    mundo = await _mundo(db)
    await k.reconstruir_todo(db)
    assert await _sucio(db) is False
    return mundo


async def _con_linea(db, referencia, linea):
    referencia.linea_comercial = linea
    await db.flush()


# --- referencia.linea_comercial --------------------------------------------------------------


async def test_editing_the_linea_comercial_of_a_referencia_marks_dirty(sesion):
    _, (ref, _) = await _construido(sesion)

    await maestros.update_referencia(sesion, ref, ReferenciaUpdate(linea_comercial="MOTOS"))

    assert await _sucio(sesion) is True


async def test_editing_other_fields_or_keeping_the_linea_leaves_the_summaries_clean(sesion):
    _, (ref, _) = await _construido(sesion)
    await _con_linea(sesion, ref, "MOTOS")
    await k.reconstruir_todo(sesion)

    await maestros.update_referencia(sesion, ref, ReferenciaUpdate(nombre="Other", linea_comercial="MOTOS"))

    assert await _sucio(sesion) is False


async def test_the_excel_replace_marks_dirty_only_when_a_linea_changes(sesion):
    (_, _), (ref, _) = await _construido(sesion)
    await _con_linea(sesion, ref, "MOTOS")
    await k.reconstruir_todo(sesion)

    def fila(linea):
        return [{"codigo": ref.codigo, "proveedor_id": ref.proveedor_id, "nombre": ref.nombre or "N",
                 "linea_comercial": linea, "unidad_empaque": 1, "precio_normal": ref.precio_normal}]

    plan = await reemplazo_referencias.planificar(sesion, fila("MOTOS"))
    await reemplazo_referencias._escribir_fila(sesion, plan, plan.objetivos[0], None)
    assert await _sucio(sesion) is False

    plan = await reemplazo_referencias.planificar(sesion, fila("REPUESTOS"))
    await reemplazo_referencias._escribir_fila(sesion, plan, plan.objetivos[0], None)
    assert await _sucio(sesion) is True


# --- referencia.precio_normal (the fallback cost and valuation) -------------------------------


async def _con_precio(db, referencia, precio):
    referencia.precio_normal = precio
    await db.flush()


async def test_editing_the_precio_normal_of_a_referencia_marks_dirty(sesion):
    _, (ref, _) = await _construido(sesion)
    await _con_precio(sesion, ref, Decimal("20.00"))
    await k.reconstruir_todo(sesion)

    await maestros.update_referencia(sesion, ref, ReferenciaUpdate(precio_normal=Decimal("20")))
    assert await _sucio(sesion) is False

    await maestros.update_referencia(sesion, ref, ReferenciaUpdate(precio_normal=Decimal("25.50")))
    assert await _sucio(sesion) is True


async def test_giving_a_price_to_a_referencia_without_one_marks_dirty(sesion):
    _, (ref, _) = await _construido(sesion)
    await _con_precio(sesion, ref, None)
    await k.reconstruir_todo(sesion)

    await maestros.update_referencia(sesion, ref, ReferenciaUpdate(precio_normal=Decimal("10")))

    assert await _sucio(sesion) is True


async def test_the_excel_replace_marks_dirty_when_only_the_precio_normal_changes(sesion):
    (_, _), (ref, _) = await _construido(sesion)
    await _con_precio(sesion, ref, Decimal("20.00"))
    await k.reconstruir_todo(sesion)

    def fila(precio):
        return [{"codigo": ref.codigo, "proveedor_id": ref.proveedor_id, "nombre": ref.nombre or "N",
                 "linea_comercial": ref.linea_comercial, "unidad_empaque": 1, "precio_normal": precio}]

    plan = await reemplazo_referencias.planificar(sesion, fila(Decimal("20.00")))
    await reemplazo_referencias._escribir_fila(sesion, plan, plan.objetivos[0], None)
    assert await _sucio(sesion) is False

    plan = await reemplazo_referencias.planificar(sesion, fila(Decimal("33.00")))
    await reemplazo_referencias._escribir_fila(sesion, plan, plan.objetivos[0], None)
    assert await _sucio(sesion) is True


# --- cliente_tecnired -------------------------------------------------------------------------


async def test_replacing_the_tecnired_list_marks_dirty(sesion):
    await _construido(sesion)
    sesion.add(ClienteTecnired(id=uuid.uuid4(), nit="900111", razon_social="A"))
    await sesion.flush()
    await k.reconstruir_todo(sesion)
    assert await _sucio(sesion) is False

    await maestros.reemplazar_clientes_tecnired(sesion, [{"nit": "900111"}, {"nit": "900222"}])

    assert await _sucio(sesion) is True


async def test_replacing_an_empty_list_with_an_empty_one_marks_nothing(sesion):
    await _construido(sesion)

    await maestros.reemplazar_clientes_tecnired(sesion, [])

    assert await _sucio(sesion) is False


# --- parametro_metodologia --------------------------------------------------------------------


@pytest.mark.parametrize("clave,sucio", [("hmcl_nits", True), ("lineas_comerciales", True),
                                         ("dias_ventana_ingresos", False)])
async def test_only_the_configuration_keys_the_summaries_depend_on_mark_dirty(sesion, clave, sucio):
    await _construido(sesion)

    await parametros.registrar_cambio(sesion, clave, ["X"], datetime.date(2099, 1, 1))

    assert await _sucio(sesion) is sucio


# --- INVENTARIO carga -------------------------------------------------------------------------


async def test_applying_an_inventario_carga_marks_dirty(sesion):
    (a, _), (ref, _) = await _construido(sesion)
    carga = _carga()
    sesion.add(carga)
    await sesion.flush()

    await inventario_mod.aplicar_detalle(sesion, [_staging(carga, a, ref, "B1", "5", "10")], CORTE, carga.id)

    assert await _sucio(sesion) is True


async def test_annulling_an_inventario_carga_marks_dirty(sesion):
    await _construido(sesion)
    carga = _carga(estado="APLICADO")
    sesion.add(carga)
    await sesion.flush()

    await cargas_api.anular_carga(carga.id, db=sesion, user=None)

    assert carga.estado == "ANULADO" and await _sucio(sesion) is True


# --- retention purge ---------------------------------------------------------------------------


async def test_the_retention_purge_of_old_cortes_marks_dirty(sesion):
    (a, _), (ref, _) = await _mundo(sesion)
    for corte in (CORTE_VIEJO, CORTE):
        carga = _carga(corte)
        await _aplicar(sesion, carga, [_staging(carga, a, ref, "B1", "5", "10")])
    await k.reconstruir_todo(sesion)
    assert await _sucio(sesion) is False

    await retencion.ejecutar_purga_inventario(sesion, chunk_size=1)

    assert await _sucio(sesion) is True


async def test_a_purge_with_nothing_to_delete_leaves_the_summaries_clean(sesion):
    (a, _), (ref, _) = await _mundo(sesion)
    carga = _carga(CORTE)
    await _aplicar(sesion, carga, [_staging(carga, a, ref, "B1", "5", "10")])
    await k.reconstruir_todo(sesion)

    await retencion.ejecutar_purga_inventario(sesion, chunk_size=1)

    assert await _sucio(sesion) is False


# --- never built ------------------------------------------------------------------------------


async def test_nothing_is_flagged_until_the_summaries_were_built_once(sesion):
    (a, _), (ref, _) = await _mundo(sesion)
    carga = _carga()
    sesion.add(carga)
    await sesion.flush()

    await maestros.update_referencia(sesion, ref, ReferenciaUpdate(linea_comercial="MOTOS"))
    await maestros.reemplazar_clientes_tecnired(sesion, [{"nit": "900111"}])
    await parametros.registrar_cambio(sesion, "hmcl_nits", ["1"], datetime.date(2099, 1, 1))
    await inventario_mod.aplicar_detalle(sesion, [_staging(carga, a, ref, "B1", "5", "10")], CORTE, carga.id)

    assert await _sucio(sesion) is None  # no state row: the first build reads every input


# --- the rebuild lock -------------------------------------------------------------------------


async def test_a_trigger_that_waits_too_long_for_a_running_rebuild_fails_with_a_clear_message(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS", 1)
    motor = create_async_engine(URL)
    try:
        async with AsyncSession(motor) as reconstruyendo, AsyncSession(motor) as espera:
            await k._bloquear(reconstruyendo)  # a rebuild in flight holds the lock until it commits

            with pytest.raises(k.ResumenOcupadoError, match="reconstruyendo"):
                await k.marcar_sucio_si_construido(espera)
            await reconstruyendo.rollback()
            await espera.rollback()
    finally:
        await motor.dispose()
