"""
Report Service — Informe Gerencial PDF

Generates a consolidated management PDF report covering 8 data sections (F2–F8).
Uses WeasyPrint rendered in a thread pool (same pattern as pdf_service.py).
All queries are raw SQL via text() for heavy aggregations.
"""
import asyncio
import logging
import os
from datetime import date, datetime, timezone, timedelta
from functools import partial
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'html_templates')
_jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

_MONTH_NAMES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre',
}

COL_5 = timezone(timedelta(hours=-5))

# ---------------------------------------------------------------------------
# Helper: normalize float
# ---------------------------------------------------------------------------

def _f(val) -> float:
    """Convert DB numeric/None to float, never crash."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _i(val) -> int:
    if val is None:
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# F2 — Pedidos de Importación
# ---------------------------------------------------------------------------

async def _query_f2(desde: date, hasta: date, db: AsyncSession) -> dict:
    sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE computed_status NOT IN ('completado','cancelado'))
                AS activos_total,
            COUNT(*) FILTER (
                WHERE computed_status NOT IN ('completado','cancelado')
                  AND is_spare_part = false
            ) AS motos_activos,
            COUNT(*) FILTER (
                WHERE computed_status NOT IN ('completado','cancelado')
                  AND is_spare_part = true
            ) AS repuestos_activos,
            -- status buckets motos (all active)
            COUNT(*) FILTER (
                WHERE computed_status NOT IN ('completado','cancelado')
                  AND is_spare_part = false
                  AND computed_status IN ('en_destino','completado_parcial','nacionalizado')
            ) AS motos_nacionalizado,
            COUNT(*) FILTER (
                WHERE computed_status NOT IN ('completado','cancelado')
                  AND is_spare_part = false
                  AND computed_status IN ('en_transito','en_transito_parcial')
            ) AS motos_en_transito,
            COUNT(*) FILTER (
                WHERE computed_status NOT IN ('completado','cancelado')
                  AND is_spare_part = false
                  AND computed_status IN ('en_preparacion','listo_fabrica','en_origen')
            ) AS motos_en_origen,
            -- motos en pedido: sum total_units for active moto orders
            COALESCE(SUM(total_units) FILTER (
                WHERE computed_status NOT IN ('completado','cancelado')
                  AND is_spare_part = false
            ), 0) AS motos_unidades,
            -- repuestos FOB: sum fob_pi from spare_part_items linked to active SP orders
            COALESCE((
                SELECT SUM(spi.fob_pi)
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so2 ON so2.id = spl.shipment_order_id
                WHERE so2.computed_status NOT IN ('completado','cancelado')
                  AND so2.is_spare_part = true
            ), 0) AS repuestos_fob
        FROM shipment_orders
    """)

    row = (await db.execute(sql)).fetchone()
    if row is None or (_i(row.activos_total) == 0):
        return {
            'sin_datos': True,
            'activos_total': 0, 'motos_activos': 0, 'repuestos_activos': 0,
            'motos_nacionalizado': 0, 'motos_en_transito': 0, 'motos_en_origen': 0,
            'motos_unidades': 0, 'repuestos_fob': 0.0,
        }
    return {
        'sin_datos': False,
        'activos_total': _i(row.activos_total),
        'motos_activos': _i(row.motos_activos),
        'repuestos_activos': _i(row.repuestos_activos),
        'motos_nacionalizado': _i(row.motos_nacionalizado),
        'motos_en_transito': _i(row.motos_en_transito),
        'motos_en_origen': _i(row.motos_en_origen),
        'motos_unidades': _i(row.motos_unidades),
        'repuestos_fob': _f(row.repuestos_fob),
    }


# ---------------------------------------------------------------------------
# F3 — Motocicletas (snapshot — no date filter)
# ---------------------------------------------------------------------------

async def _query_f3(db: AsyncSession) -> dict:
    snap_sql = text("""
        SELECT
            COUNT(*)                                                           AS total,
            COUNT(*) FILTER (WHERE facturado = false
                             AND separada_nacionalizacion = false)             AS disponibles,
            COUNT(*) FILTER (WHERE separada_nacionalizacion = true)           AS separadas,
            COUNT(*) FILTER (WHERE empadronamiento_fisico_enviado = false)    AS pend_empadronamiento,
            COUNT(*) FILTER (WHERE observation_id IS NOT NULL)                AS con_obs,
            COUNT(*) FILTER (WHERE cargado_runt = true)                       AS con_runt,
            COUNT(*) FILTER (WHERE facturado = true)                          AS facturadas_historico
        FROM shipment_moto_units
    """)

    modelo_sql = text("""
        SELECT
            model,
            COUNT(*) FILTER (WHERE facturado = false
                             AND separada_nacionalizacion = false) AS disponibles,
            COUNT(*) AS total
        FROM shipment_moto_units
        GROUP BY model
        ORDER BY model
    """)

    snap_row = (await db.execute(snap_sql)).fetchone()
    modelo_rows = (await db.execute(modelo_sql)).all()

    total = _i(snap_row.total) if snap_row else 0
    if total == 0:
        return {
            'sin_datos': True,
            'total': 0, 'disponibles': 0, 'separadas': 0,
            'pend_empadronamiento': 0, 'con_obs': 0, 'con_runt': 0,
            'facturadas_historico': 0,
            'por_modelo': [],
        }

    por_modelo = [
        {'model': r.model or 'Sin modelo', 'disponibles': _i(r.disponibles), 'total': _i(r.total)}
        for r in modelo_rows
    ]

    return {
        'sin_datos': False,
        'total': total,
        'disponibles': _i(snap_row.disponibles),
        'separadas': _i(snap_row.separadas),
        'pend_empadronamiento': _i(snap_row.pend_empadronamiento),
        'con_obs': _i(snap_row.con_obs),
        'con_runt': _i(snap_row.con_runt),
        'facturadas_historico': _i(snap_row.facturadas_historico),
        'por_modelo': por_modelo,
    }


# ---------------------------------------------------------------------------
# F4 — Cobertura de Repuestos
# ---------------------------------------------------------------------------

async def _query_f4(db: AsyncSession) -> dict:
    coverage_sql = text("""
        WITH
        aqui AS (
            SELECT UPPER(TRIM(REPLACE(part_number, ' ', ''))) AS pn
            FROM spare_part_availability
            WHERE qty_available > 0
            GROUP BY 1
        ),
        en_camino AS (
            SELECT UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) AS pn
            FROM spare_part_items spi
            JOIN spare_part_lots spl ON spl.id = spi.lot_id
            JOIN shipment_orders so  ON so.id  = spl.shipment_order_id
            WHERE spi.qty_received > 0
              AND spi.qty_physical IS NULL
              AND (so.bl_container IS NOT NULL OR spl.packing_list_received = true)
              AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) NOT IN (SELECT pn FROM aqui)
            UNION
            SELECT UPPER(TRIM(part_code)) AS pn
            FROM part_catalog
            WHERE public_price IS NOT NULL
              AND UPPER(TRIM(part_code)) NOT IN (SELECT pn FROM aqui)
        ),
        pedido AS (
            SELECT UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) AS pn
            FROM spare_part_items spi
            JOIN spare_part_lots spl ON spl.id = spi.lot_id
            WHERE (spl.packing_list_received = false OR spi.status IN ('BACKORDER', 'BACKORDER_PARCIAL'))
              AND spi.status != 'CANCELLED'
              AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) NOT IN (SELECT pn FROM aqui)
              AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) NOT IN (SELECT pn FROM en_camino)
            GROUP BY 1
        )
        SELECT
            COUNT(*)                                                        AS total,
            COUNT(CASE WHEN a.pn IS NOT NULL THEN 1 END)                   AS aqui,
            COUNT(CASE WHEN c.pn IS NOT NULL AND a.pn IS NULL THEN 1 END)  AS en_camino,
            COUNT(CASE WHEN p.pn IS NOT NULL AND a.pn IS NULL AND c.pn IS NULL THEN 1 END) AS pedido,
            COUNT(CASE WHEN a.pn IS NULL AND c.pn IS NULL AND p.pn IS NULL THEN 1 END)     AS sin_cobertura
        FROM parts_references r
        LEFT JOIN aqui      a ON a.pn = UPPER(TRIM(REPLACE(r.factory_part_number, ' ', '')))
        LEFT JOIN en_camino c ON c.pn = UPPER(TRIM(REPLACE(r.factory_part_number, ' ', '')))
        LEFT JOIN pedido    p ON p.pn = UPPER(TRIM(REPLACE(r.factory_part_number, ' ', '')))
        WHERE EXISTS (
            SELECT 1 FROM parts_manual_items pmi
            WHERE pmi.factory_part_number = r.factory_part_number
        )
    """)

    fob_sql = text("""
        SELECT COALESCE(SUM(spa.qty_available * COALESCE(pr.avg_fob_cost, pr.preliminary_fob, 0)), 0) AS fob_stock
        FROM spare_part_availability spa
        LEFT JOIN parts_references pr
            ON UPPER(TRIM(REPLACE(spa.part_number, ' ', ''))) = UPPER(TRIM(pr.factory_part_number))
        WHERE spa.qty_available > 0
    """)

    cov_row = (await db.execute(coverage_sql)).fetchone()
    fob_row = (await db.execute(fob_sql)).fetchone()

    total = _i(cov_row.total) if cov_row else 0
    if total == 0:
        return {
            'sin_datos': True,
            'total': 0, 'aqui': 0, 'en_camino': 0, 'pedido': 0, 'sin_cobertura': 0,
            'fob_stock': 0.0,
        }

    return {
        'sin_datos': False,
        'total': total,
        'aqui': _i(cov_row.aqui),
        'en_camino': _i(cov_row.en_camino),
        'pedido': _i(cov_row.pedido),
        'sin_cobertura': _i(cov_row.sin_cobertura),
        'fob_stock': _f(fob_row.fob_stock) if fob_row else 0.0,
    }


# ---------------------------------------------------------------------------
# F5 — Rotación de Repuestos
# ---------------------------------------------------------------------------

async def _query_f5(db: AsyncSession) -> dict:
    rot_sql = text("""
        SELECT
            COALESCE(r.rotation_class, '__sin_clasificar__') AS cls,
            COUNT(*) AS refs,
            COALESCE(SUM(spa.qty_available * COALESCE(r.avg_fob_cost, r.preliminary_fob, 0)), 0) AS fob_disponible
        FROM parts_references r
        LEFT JOIN spare_part_availability spa
            ON UPPER(TRIM(REPLACE(spa.part_number, ' ', ''))) = UPPER(TRIM(r.factory_part_number))
        WHERE EXISTS (
            SELECT 1 FROM parts_manual_items pmi
            WHERE pmi.factory_part_number = r.factory_part_number
        )
        GROUP BY COALESCE(r.rotation_class, '__sin_clasificar__')
    """)

    # Risk: items in media/baja rotation that are ordered but not yet received
    risk_sql = text("""
        SELECT
            pr.rotation_class,
            COALESCE(SUM(spi.qty_ordered * COALESCE(spi.fob_pi, pr.preliminary_fob, 0)), 0) AS fob_riesgo
        FROM parts_references pr
        JOIN spare_part_items spi
            ON UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) = UPPER(TRIM(pr.factory_part_number))
        JOIN spare_part_lots spl ON spl.id = spi.lot_id
        WHERE pr.rotation_class IN ('media', 'baja')
          AND spl.packing_list_received = false
          AND spi.status NOT IN ('CANCELLED', 'RECEIVED')
        GROUP BY pr.rotation_class
    """)

    rot_rows = (await db.execute(rot_sql)).all()
    risk_rows = (await db.execute(risk_sql)).all()

    if not rot_rows:
        return {
            'sin_datos': True,
            'clases': [],
            'sin_clasificar_refs': 0,
            'sin_clasificar_fob': 0.0,
            'total_riesgo': 0.0,
        }

    risk_by_class = {r.rotation_class: _f(r.fob_riesgo) for r in risk_rows}

    clases = []
    sin_clasificar_refs = 0
    sin_clasificar_fob = 0.0

    for r in rot_rows:
        if r.cls == '__sin_clasificar__':
            sin_clasificar_refs = _i(r.refs)
            sin_clasificar_fob = _f(r.fob_disponible)
            continue
        clases.append({
            'clase': r.cls,
            'refs': _i(r.refs),
            'fob_disponible': _f(r.fob_disponible),
            'fob_riesgo': risk_by_class.get(r.cls, 0.0),
        })

    # Ensure orden: alta, media, baja
    orden = {'alta': 0, 'media': 1, 'baja': 2}
    clases.sort(key=lambda x: orden.get(x['clase'], 99))

    total_riesgo = sum(c['fob_riesgo'] for c in clases if c['clase'] in ('media', 'baja'))

    has_data = any(c['refs'] > 0 for c in clases) or sin_clasificar_refs > 0
    return {
        'sin_datos': not has_data,
        'clases': clases,
        'sin_clasificar_refs': sin_clasificar_refs,
        'sin_clasificar_fob': sin_clasificar_fob,
        'total_riesgo': total_riesgo,
    }


# ---------------------------------------------------------------------------
# F6 — Backorders
# ---------------------------------------------------------------------------

async def _query_f6(desde: date, hasta: date, db: AsyncSession) -> dict:
    sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE resolved = false)                          AS activos,
            COUNT(*) FILTER (WHERE resolved = true
                             AND resolved_at::date BETWEEN :desde AND :hasta) AS resueltos_periodo,
            COUNT(DISTINCT part_number) FILTER (WHERE resolved = false)       AS refs_afectadas,
            COALESCE(SUM(
                CASE WHEN resolved = false
                THEN qty_pending * COALESCE(unit_price, fob_pi, 0)
                ELSE 0 END
            ), 0) AS fob_pendiente
        FROM backorders bo
        LEFT JOIN spare_part_items spi ON spi.id = bo.spare_part_item_id
    """)

    row = (await db.execute(sql, {'desde': desde, 'hasta': hasta})).fetchone()
    if row is None or _i(row.activos) == 0 and _i(row.resueltos_periodo) == 0:
        return {
            'sin_datos': True,
            'activos': 0, 'resueltos_periodo': 0,
            'refs_afectadas': 0, 'fob_pendiente': 0.0,
        }

    return {
        'sin_datos': False,
        'activos': _i(row.activos),
        'resueltos_periodo': _i(row.resueltos_periodo),
        'refs_afectadas': _i(row.refs_afectadas),
        'fob_pendiente': _f(row.fob_pendiente),
    }


# ---------------------------------------------------------------------------
# F7 — Ajuste de Pedidos
# ---------------------------------------------------------------------------

async def _query_f7(desde: date, hasta: date, db: AsyncSession) -> dict:
    sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE decision = 'cancelar' AND executed_at IS NULL) AS cancelar_pendiente,
            COUNT(*) FILTER (WHERE decision = 'cambiar'  AND executed_at IS NULL) AS cambiar_pendiente,
            COUNT(*) FILTER (
                WHERE decision = 'cancelar'
                  AND executed_at IS NOT NULL
                  AND executed_at::date BETWEEN :desde AND :hasta
            ) AS cancelar_ejecutado,
            COALESCE(SUM(
                CASE WHEN decision = 'cancelar' AND executed_at IS NULL
                THEN COALESCE(pr.avg_fob_cost, pr.preliminary_fob, 0)
                ELSE 0 END
            ), 0) AS fob_cancelar_pendiente,
            COALESCE(SUM(
                CASE WHEN decision = 'cancelar'
                      AND executed_at IS NOT NULL
                      AND executed_at::date BETWEEN :desde AND :hasta
                THEN COALESCE(pr.avg_fob_cost, pr.preliminary_fob, 0)
                ELSE 0 END
            ), 0) AS fob_cancelar_ejecutado
        FROM part_order_decisions pod
        LEFT JOIN parts_references pr
            ON UPPER(TRIM(REPLACE(pod.factory_part_number, ' ', ''))) = UPPER(TRIM(pr.factory_part_number))
    """)

    row = (await db.execute(sql, {'desde': desde, 'hasta': hasta})).fetchone()
    if row is None or (
        _i(row.cancelar_pendiente) == 0 and _i(row.cambiar_pendiente) == 0
        and _i(row.cancelar_ejecutado) == 0
    ):
        return {
            'sin_datos': True,
            'cancelar_pendiente': 0, 'cambiar_pendiente': 0,
            'cancelar_ejecutado': 0,
            'fob_cancelar_pendiente': 0.0, 'fob_cancelar_ejecutado': 0.0,
        }

    return {
        'sin_datos': False,
        'cancelar_pendiente': _i(row.cancelar_pendiente),
        'cambiar_pendiente': _i(row.cambiar_pendiente),
        'cancelar_ejecutado': _i(row.cancelar_ejecutado),
        'fob_cancelar_pendiente': _f(row.fob_cancelar_pendiente),
        'fob_cancelar_ejecutado': _f(row.fob_cancelar_ejecutado),
    }


# ---------------------------------------------------------------------------
# F8 — Remisiones de Inventario
# ---------------------------------------------------------------------------

async def _query_f8(desde: date, hasta: date, db: AsyncSession) -> dict:
    _CONCEPTS = ('PEDIDO', 'GARANTIA', 'CORTESIA', 'VEHICULO_PROPIO')

    despacho_sql = text("""
        SELECT
            ir.type,
            COUNT(DISTINCT ir.id)                                           AS total,
            COALESCE(SUM(ABS(irm.delta) * COALESCE(spi.unit_price, spi.fob_pi, 0)), 0) AS fob
        FROM inventory_remisions ir
        LEFT JOIN inventory_remision_movements irm ON irm.remision_id = ir.id AND irm.delta < 0
        LEFT JOIN spare_part_items spi ON spi.id = irm.spare_part_item_id
        WHERE ir.status = 'DESPACHADO'
          AND ir.dispatched_at::date BETWEEN :desde AND :hasta
        GROUP BY ir.type
    """)

    anuladas_sql = text("""
        SELECT COUNT(*) AS anuladas
        FROM inventory_remisions
        WHERE status = 'ANULADO'
          AND cancelled_at::date BETWEEN :desde AND :hasta
    """)

    params = {'desde': desde, 'hasta': hasta}
    desp_rows = (await db.execute(despacho_sql, params)).all()
    anu_row = (await db.execute(anuladas_sql, params)).fetchone()

    # Build concept map — ensure all 4 appear even with 0
    por_concepto = {c: {'count': 0, 'fob': 0.0} for c in _CONCEPTS}
    for r in desp_rows:
        tipo = (r.type or '').upper()
        if tipo in por_concepto:
            por_concepto[tipo] = {'count': _i(r.total), 'fob': _f(r.fob)}

    total_despachos = sum(v['count'] for v in por_concepto.values())
    total_fob = sum(v['fob'] for v in por_concepto.values())
    anuladas = _i(anu_row.anuladas) if anu_row else 0

    sin_datos = total_despachos == 0 and anuladas == 0
    return {
        'sin_datos': sin_datos,
        'total': total_despachos,
        'fob': total_fob,
        'por_concepto': [
            {'tipo': c, 'count': por_concepto[c]['count'], 'fob': por_concepto[c]['fob']}
            for c in _CONCEPTS
        ],
        'anuladas': anuladas,
    }


# ---------------------------------------------------------------------------
# Period label helper
# ---------------------------------------------------------------------------

def _periodo_label(desde: date, hasta: date) -> str:
    d_day = desde.day
    d_month = _MONTH_NAMES[desde.month]
    d_year = desde.year
    h_day = hasta.day
    h_month = _MONTH_NAMES[hasta.month]
    h_year = hasta.year

    if d_year == h_year:
        if d_month == h_month:
            return f"{d_day} – {h_day} de {d_month} de {d_year}"
        return f"{d_day} de {d_month} – {h_day} de {h_month} de {h_year}"
    return f"{d_day} de {d_month} de {d_year} – {h_day} de {h_month} de {h_year}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_gerencial_report(desde: date, hasta: date, db: AsyncSession) -> bytes:
    """
    Runs all section queries (mostly in parallel), builds Jinja2 context,
    renders the HTML template, and converts to PDF bytes via WeasyPrint
    in a thread pool executor (non-blocking).
    """
    # Run independent queries concurrently
    f2_task = _query_f2(desde, hasta, db)
    f3_task = _query_f3(db)
    f4_task = _query_f4(db)
    f5_task = _query_f5(db)
    f6_task = _query_f6(desde, hasta, db)
    f7_task = _query_f7(desde, hasta, db)
    f8_task = _query_f8(desde, hasta, db)

    # SQLAlchemy AsyncSession is NOT safe for true concurrent tasks on the same
    # connection, so we gather sequentially-safe by awaiting them in order.
    # For true parallelism you'd need separate sessions; for simplicity here
    # we run sequentially which is still fast enough for a management report.
    f2 = await f2_task
    f3 = await f3_task
    f4 = await f4_task
    f5 = await f5_task
    f6 = await f6_task
    f7 = await f7_task
    f8 = await f8_task

    now_col5 = datetime.now(tz=COL_5)
    generado_at = now_col5.strftime('%d/%m/%Y %H:%M') + ' (UTC-5)'

    context = {
        'meta': {
            'periodo_label': _periodo_label(desde, hasta),
            'generado_at': generado_at,
            'desde': desde.isoformat(),
            'hasta': hasta.isoformat(),
        },
        'f2': f2,
        'f3': f3,
        'f4': f4,
        'f5': f5,
        'f6': f6,
        'f7': f7,
        'f8': f8,
    }

    template = _jinja_env.get_template('informe_gerencial.html')
    html_out = template.render(context)

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        partial(HTML(string=html_out).write_pdf)
    )
    return pdf_bytes
