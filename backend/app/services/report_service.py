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
# Palette
# ---------------------------------------------------------------------------

_MODEL_COLORS = [
    '#F4925C', '#7A88C0', '#66BA88', '#A888D0',
    '#D9B05A', '#6EAAD8', '#E07878', '#8EA0B0',
    '#5AAAB8', '#92C458', '#BC88CC', '#E09090',
]

# ---------------------------------------------------------------------------
# Helper: normalize float / int
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
# Presentation helpers (pure functions — tested in test_report_helpers.py)
# ---------------------------------------------------------------------------

def _pct(num, den, decimals: int = 0):
    """Safe percentage. Returns 0 when den == 0."""
    if not den:
        return 0
    v = num / den * 100
    return round(v, decimals) if decimals else round(v)


def _bar(value, max_val) -> int:
    """Bar width 0-100. Returns 0 when max_val == 0."""
    if not max_val:
        return 0
    return int(min(100, max(0, round(value / max_val * 100))))


def _heat_style(value, max_val) -> str:
    """Orange heatmap CSS style for matrix cells."""
    if not value or not max_val:
        return 'background:#F5F6F9;color:#AEB6BF;'
    i = value / max_val
    if i >= 0.7:
        return 'background:#F9CCAF;color:#B05030;'
    if i >= 0.4:
        return 'background:#FBDECB;color:#C06040;'
    if i >= 0.2:
        return 'background:#FDEEE4;color:#C87050;'
    return 'background:#FEF5F0;color:#D08060;'


def _make_conic(slices: list) -> str:
    """Build a CSS conic-gradient string from [(color, pct_float), ...]."""
    if not slices:
        return 'conic-gradient(#AEB6BF 0% 100%)'
    parts = []
    pos = 0.0
    for color, pct in slices:
        end = pos + pct
        parts.append(f"{color} {pos:.1f}% {end:.1f}%")
        pos = end
    return f"conic-gradient({', '.join(parts)})"


def _make_svg_donut(slices: list, size: int = 120, hole: float = 0.63,
                    center_val: str = '', center_sub: str = '') -> str:
    """
    Generate an inline SVG donut chart — 100% WeasyPrint safe.
    slices = [(color, pct_float), ...] where pct_float values sum to ~100.
    """
    import math
    cx = cy = size / 2.0
    r_out = size / 2.0
    r_in  = size / 2.0 * hole

    if not slices or sum(p for _, p in slices) <= 0:
        gray = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_out:.1f}" fill="#E5E8EC"/>'
        gray_in = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_in:.1f}" fill="#fff"/>'
        return f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">{gray}{gray_in}</svg>'

    paths = []
    angle = -90.0
    for color, pct in slices:
        if pct <= 0:
            continue
        sweep = min(pct / 100.0 * 360.0, 359.9999)
        end = angle + sweep
        def pt(a, r):
            return cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
        ox1, oy1 = pt(angle, r_out)
        ox2, oy2 = pt(end,   r_out)
        ix1, iy1 = pt(end,   r_in)
        ix2, iy2 = pt(angle, r_in)
        lg = 1 if sweep > 180 else 0
        d = (f"M {ox1:.3f},{oy1:.3f} "
             f"A {r_out:.3f},{r_out:.3f} 0 {lg} 1 {ox2:.3f},{oy2:.3f} "
             f"L {ix1:.3f},{iy1:.3f} "
             f"A {r_in:.3f},{r_in:.3f} 0 {lg} 0 {ix2:.3f},{iy2:.3f} Z")
        paths.append(f'<path d="{d}" fill="{color}"/>')
        angle = end

    txt = ''
    if center_val:
        txt += (f'<text x="{cx:.0f}" y="{cy-2:.0f}" '
                f'text-anchor="middle" font-family="Arial,Helvetica,sans-serif" '
                f'font-size="22" font-weight="800" fill="#15181C">{center_val}</text>')
    if center_sub:
        txt += (f'<text x="{cx:.0f}" y="{cy+14:.0f}" '
                f'text-anchor="middle" font-family="Arial,Helvetica,sans-serif" '
                f'font-size="9" fill="#828B95" letter-spacing="1">{center_sub}</text>')

    body = ''.join(paths) + txt
    return f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'


# ---------------------------------------------------------------------------
# F2 — Pedidos de Importación
# ---------------------------------------------------------------------------

async def _query_f2(desde: date, hasta: date, db: AsyncSession) -> dict:
    sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE computed_status != 'completado')
                AS activos_total,
            -- pedidos únicos de motos por pi_number
            COUNT(DISTINCT pi_number) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
            ) AS motos_activos,
            COUNT(*) FILTER (
                WHERE computed_status != 'completado'
                  AND computed_status != 'cancelado'
                  AND is_spare_part = true
            ) AS repuestos_activos,
            -- status buckets motos (all active)
            COUNT(*) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status IN ('en_destino','completado_parcial','nacionalizado')
            ) AS motos_nacionalizado,
            COUNT(*) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status IN ('en_transito','en_transito_parcial')
            ) AS motos_en_transito,
            COUNT(*) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status IN ('en_preparacion','listo_fabrica','en_origen')
            ) AS motos_en_origen,
            -- motos en pedido: sum total_units for active moto orders
            COALESCE(SUM(total_units) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
            ), 0) AS motos_unidades,
            -- repuestos FOB
            COALESCE((
                SELECT SUM(spi.qty_ordered * COALESCE(spi.unit_price, spi.fob_pi, 0))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so2 ON so2.id = spl.shipment_order_id
                WHERE so2.computed_status != 'completado'
                  AND so2.is_spare_part = true
                  AND spi.status != 'CANCELLED'
            ), 0) AS repuestos_fob,
            -- pipeline motos: unidades de moto por etapa (SUM total_units)
            COALESCE(SUM(total_units) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status = 'en_preparacion'
            ), 0) AS m_prep,
            COALESCE(SUM(total_units) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status = 'listo_fabrica'
            ), 0) AS m_listo,
            COALESCE(SUM(total_units) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status = 'en_origen'
            ), 0) AS m_origen,
            COALESCE(SUM(total_units) FILTER (
                WHERE computed_status != 'completado'
                  AND is_spare_part = false
                  AND computed_status IN ('en_transito','en_transito_parcial')
            ), 0) AS m_transito,
            -- m_destino: unidades en destino aún no facturadas
            COALESCE((
                SELECT COUNT(*)
                FROM shipment_moto_units mu_d
                JOIN shipment_orders so_d ON so_d.id = mu_d.shipment_order_id
                WHERE so_d.computed_status != 'completado'
                  AND so_d.is_spare_part = false
                  AND so_d.computed_status = 'en_destino'
                  AND mu_d.facturado = false
            ), 0) AS m_destino,
            -- m_nac: unidades facturadas (facturado = nacionalizado)
            COALESCE((
                SELECT COUNT(*)
                FROM shipment_moto_units mu_n
                JOIN shipment_orders so_n ON so_n.id = mu_n.shipment_order_id
                WHERE so_n.computed_status != 'completado'
                  AND so_n.is_spare_part = false
                  AND mu_n.facturado = true
            ), 0) AS m_nac,
            -- pipeline repuestos: referencias únicas por etapa (subquery)
            COALESCE((
                SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number,' ',''))))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so_s ON so_s.id = spl.shipment_order_id
                WHERE so_s.computed_status != 'completado'
                  AND so_s.is_spare_part = true
                  AND so_s.computed_status = 'en_preparacion'
                  AND spi.status != 'CANCELLED'
            ), 0) AS r_prep,
            COALESCE((
                SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number,' ',''))))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so_s ON so_s.id = spl.shipment_order_id
                WHERE so_s.computed_status != 'completado'
                  AND so_s.is_spare_part = true
                  AND so_s.computed_status = 'listo_fabrica'
                  AND spi.status != 'CANCELLED'
            ), 0) AS r_listo,
            COALESCE((
                SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number,' ',''))))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so_s ON so_s.id = spl.shipment_order_id
                WHERE so_s.computed_status != 'completado'
                  AND so_s.is_spare_part = true
                  AND so_s.computed_status = 'en_origen'
                  AND spi.status != 'CANCELLED'
            ), 0) AS r_origen,
            COALESCE((
                SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number,' ',''))))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so_s ON so_s.id = spl.shipment_order_id
                WHERE so_s.computed_status != 'completado'
                  AND so_s.is_spare_part = true
                  AND so_s.computed_status IN ('en_transito','en_transito_parcial')
                  AND spi.status != 'CANCELLED'
            ), 0) AS r_transito,
            COALESCE((
                SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number,' ',''))))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so_s ON so_s.id = spl.shipment_order_id
                WHERE so_s.computed_status != 'completado'
                  AND so_s.is_spare_part = true
                  AND so_s.computed_status = 'en_destino'
                  AND spi.status != 'CANCELLED'
            ), 0) AS r_destino,
            COALESCE((
                SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number,' ',''))))
                FROM spare_part_items spi
                JOIN spare_part_lots spl ON spl.id = spi.lot_id
                JOIN shipment_orders so_s ON so_s.id = spl.shipment_order_id
                WHERE so_s.computed_status != 'completado'
                  AND so_s.is_spare_part = true
                  AND (so_s.computed_status IN ('nacionalizado','completado_parcial')
                       OR so_s.nacionalizacion_status IS NOT NULL)
                  AND spi.status != 'CANCELLED'
                  AND spi.qty_received > 0
            ), 0) AS r_nac
        FROM shipment_orders
    """)

    # COUNT DISTINCT normalized part_number on active SP orders
    refs_sql = text("""
        SELECT COUNT(DISTINCT UPPER(TRIM(REPLACE(spi.part_number, ' ', '')))) AS refs_unicas
        FROM spare_part_items spi
        JOIN spare_part_lots spl ON spl.id = spi.lot_id
        JOIN shipment_orders so ON so.id = spl.shipment_order_id
        WHERE so.computed_status NOT IN ('completado', 'cancelado')
          AND so.is_spare_part = true
          AND spi.status != 'CANCELLED'
    """)

    row = (await db.execute(sql)).fetchone()
    refs_row = (await db.execute(refs_sql)).fetchone()

    refs_unicas_sp = _i(refs_row.refs_unicas) if refs_row else 0

    if row is None or (_i(row.activos_total) == 0):
        empty = {
            'sin_datos': True,
            'activos_total': 0, 'motos_activos': 0, 'repuestos_activos': 0,
            'motos_nacionalizado': 0, 'motos_en_transito': 0, 'motos_en_origen': 0,
            'motos_unidades': 0, 'repuestos_fob': 0.0,
            'refs_unicas_sp': refs_unicas_sp,
        }
        # Build zero pipelines
        empty['pipeline_motos'] = _build_pipeline([0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], 0, 'Motos', 0)
        empty['pipeline_repuestos'] = _build_pipeline([0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], 0, 'Repuestos', 0)
        return empty

    m_vals = [
        _i(row.m_prep), _i(row.m_listo), _i(row.m_origen),
        _i(row.m_transito), _i(row.m_destino), _i(row.m_nac),
    ]
    r_vals = [
        _i(row.r_prep), _i(row.r_listo), _i(row.r_origen),
        _i(row.r_transito), _i(row.r_destino), _i(row.r_nac),
    ]
    all_vals = m_vals + r_vals
    global_max = max(all_vals) if any(all_vals) else 1

    def build_stages(vals):
        return [{'n': v, 'pct': _bar(v, global_max), 'min_pct': max(_bar(v, global_max), 10) if v > 0 else 0} for v in vals]

    pipeline_motos = {
        'total': _i(row.motos_activos),
        'stages': build_stages(m_vals),
    }
    pipeline_repuestos = {
        'total': _i(row.repuestos_activos),
        'stages': build_stages(r_vals),
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
        'refs_unicas_sp': refs_unicas_sp,
        'pipeline_motos': pipeline_motos,
        'pipeline_repuestos': pipeline_repuestos,
    }


def _build_pipeline(m_vals, r_vals, global_max, label, total):
    """Helper to build a zero pipeline dict."""
    return {
        'total': total,
        'stages': [{'n': 0, 'pct': 0} for _ in range(6)],
    }


# ---------------------------------------------------------------------------
# F3 — Motocicletas (snapshot — no date filter)
# ---------------------------------------------------------------------------

async def _query_f3(db: AsyncSession) -> dict:
    snap_sql = text("""
        SELECT
            COUNT(*)                                                           AS total,
            COUNT(*) FILTER (WHERE facturado = false
                             AND separada_nacionalizacion = false
                             AND observation_id IS NULL
                             AND dim_pdf_object_name IS NULL)                 AS disponibles,
            COUNT(*) FILTER (WHERE separada_nacionalizacion = true)           AS separadas,
            COUNT(*) FILTER (WHERE empadronamiento_fisico_enviado = false)    AS pend_empadronamiento,
            COUNT(*) FILTER (WHERE observation_id IS NOT NULL)                AS con_obs,
            COUNT(*) FILTER (WHERE cargado_runt = true)                       AS con_runt,
            COUNT(*) FILTER (WHERE facturado = true)                          AS facturadas_historico
        FROM shipment_moto_units
    """)

    snap_row = (await db.execute(snap_sql)).fetchone()

    total = _i(snap_row.total) if snap_row else 0
    if total == 0:
        return {
            'sin_datos': True,
            'total': 0, 'disponibles': 0, 'separadas': 0,
            'pend_empadronamiento': 0, 'con_obs': 0, 'con_runt': 0,
            'facturadas_historico': 0,
            'matriz': None,
            'por_distribuidor': [],
            'por_observacion': [],
            'por_anio': [],
        }

    # --- B1: Matrix (disponibles para nacionalizar) ---
    # REGEXP_REPLACE colapsa whitespace interno y caracteres invisibles además de UPPER+TRIM
    matriz_sql = text("""
        SELECT
            REGEXP_REPLACE(UPPER(TRIM(COALESCE(mu.model, so.model, 'SIN MODELO'))), '\\s+', ' ', 'g') AS model,
            COALESCE(ml.name, 'Sin ubicación') AS ubicacion,
            COUNT(*) AS cnt
        FROM shipment_moto_units mu
        JOIN shipment_orders so ON so.id = mu.shipment_order_id
        LEFT JOIN moto_locations ml ON ml.id = mu.location_id
        WHERE mu.facturado = false
          AND mu.separada_nacionalizacion = false
          AND mu.observation_id IS NULL
          AND mu.dim_pdf_object_name IS NULL
        GROUP BY 1, 2
        ORDER BY 1, 2

    """)

    # --- B2: Facturadas por distribuidor ---
    dist_sql = text("""
        SELECT
            COALESCE(empadronamiento_fisico_distribuidor_nombre, 'Sin asignar') AS dist,
            COUNT(*) AS cnt
        FROM shipment_moto_units
        WHERE facturado = true
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 8
    """)

    # --- B3: Por observación ---
    obs_sql = text("""
        SELECT mo.name AS obs_name, COUNT(*) AS cnt
        FROM shipment_moto_units mu
        JOIN moto_observations mo ON mo.id = mu.observation_id
        GROUP BY mo.name
        ORDER BY cnt DESC
    """)

    # --- B4: Por año modelo ---
    # Fallback a modelo/año del pedido padre cuando la unidad no tiene el suyo propio
    anio_sql = text("""
        SELECT
            COALESCE(mu.model_year, so.model_year, 0)::text AS anio,
            REGEXP_REPLACE(UPPER(TRIM(COALESCE(mu.model, so.model, 'SIN MODELO'))), '\\s+', ' ', 'g') AS model,
            COUNT(*) AS cnt
        FROM shipment_moto_units mu
        JOIN shipment_orders so ON so.id = mu.shipment_order_id
        WHERE mu.facturado = false
          AND mu.separada_nacionalizacion = false
          AND mu.observation_id IS NULL
          AND mu.dim_pdf_object_name IS NULL
        GROUP BY 1, 2
        ORDER BY 1 ASC, 3 DESC
    """)

    matriz_rows = (await db.execute(matriz_sql)).all()
    dist_rows = (await db.execute(dist_sql)).all()
    obs_rows = (await db.execute(obs_sql)).all()
    anio_rows = (await db.execute(anio_sql)).all()

    # Build matriz
    matriz = None
    if matriz_rows:
        modelos_set = []
        ubicaciones_set = []
        for r in matriz_rows:
            if r.model not in modelos_set:
                modelos_set.append(r.model)
            if r.ubicacion not in ubicaciones_set:
                ubicaciones_set.append(r.ubicacion)

        # Fill grid
        cell_data = {}  # (model, ubicacion) -> count
        for r in matriz_rows:
            cell_data[(r.model, r.ubicacion)] = _i(r.cnt)

        rows = []
        for model in modelos_set:
            row_max = max(
                (cell_data.get((model, ub), 0) for ub in ubicaciones_set),
                default=0,
            )
            celdas = {}
            row_total = 0
            for ub in ubicaciones_set:
                n = cell_data.get((model, ub), 0)
                celdas[ub] = {'n': n, 'style': _heat_style(n, row_max)}
                row_total += n
            rows.append({'model': model, 'celdas': celdas, 'total': row_total})

        totales_ubicacion = {ub: sum(cell_data.get((m, ub), 0) for m in modelos_set) for ub in ubicaciones_set}
        total_general = sum(totales_ubicacion.values())

        matriz = {
            'modelos': modelos_set,
            'ubicaciones': ubicaciones_set,
            'rows': rows,
            'totales_ubicacion': totales_ubicacion,
            'total_general': total_general,
            'sin_datos': False,
        }

    # Build por_distribuidor
    por_distribuidor = []
    if dist_rows:
        max_dist = max((_i(r.cnt) for r in dist_rows), default=1)
        total_facturadas = sum(_i(r.cnt) for r in dist_rows)
        for r in dist_rows:
            cnt = _i(r.cnt)
            por_distribuidor.append({
                'nombre': r.dist,
                'cnt': cnt,
                'pct': _bar(cnt, max_dist),
                'total_pct': _pct(cnt, total_facturadas),
            })

    # Build por_observacion
    por_observacion = []
    if obs_rows:
        max_obs = max((_i(r.cnt) for r in obs_rows), default=1)
        total_obs = sum(_i(r.cnt) for r in obs_rows)
        for idx, r in enumerate(obs_rows):
            cnt = _i(r.cnt)
            por_observacion.append({
                'nombre': r.obs_name,
                'cnt': cnt,
                'pct': _bar(cnt, max_obs),
                'total_pct': _pct(cnt, total_obs),
                'color': _MODEL_COLORS[idx % len(_MODEL_COLORS)],
            })

    # Build por_anio
    por_anio = []
    if anio_rows:
        # Group by year
        anio_totals = {}  # anio -> total
        anio_modelos = {}  # anio -> [(model, cnt)]
        for r in anio_rows:
            anio = r.anio
            if anio not in anio_totals:
                anio_totals[anio] = 0
                anio_modelos[anio] = []
            cnt = _i(r.cnt)
            anio_totals[anio] += cnt
            anio_modelos[anio].append((r.model, cnt))

        # Sort: non-null years ascending, then 'Sin año'
        real_years = sorted(k for k in anio_totals if k != 'Sin año')
        if 'Sin año' in anio_totals:
            real_years.append('Sin año')
        # Keep only top 2 by total (non-null first)
        sorted_by_total = sorted(real_years, key=lambda y: anio_totals.get(y, 0), reverse=True)
        top2 = sorted_by_total[:2]
        # Re-sort top2 ascending
        top2_non_null = sorted(y for y in top2 if y != 'Sin año')
        if 'Sin año' in top2:
            top2_non_null.append('Sin año')
        top2 = top2_non_null

        for anio in top2:
            modelos_list = anio_modelos[anio]
            total_anio = anio_totals[anio]
            # Build conic slices
            slices = []
            por_modelo = []
            for idx, (model, cnt) in enumerate(modelos_list):
                color = _MODEL_COLORS[idx % len(_MODEL_COLORS)]
                pct_val = _pct(cnt, total_anio, decimals=2) if total_anio else 0
                slices.append((color, pct_val))
                por_modelo.append({'model': model, 'cnt': cnt, 'color': color, 'pct': round(pct_val)})
            svg = _make_svg_donut(slices, center_val=str(total_anio), center_sub=anio)
            por_anio.append({
                'anio': anio,
                'total': total_anio,
                'svg': svg,
                'por_modelo': por_modelo,
            })

    return {
        'sin_datos': False,
        'total': _i(snap_row.total),
        'disponibles': _i(snap_row.disponibles),
        'separadas': _i(snap_row.separadas),
        'pend_empadronamiento': _i(snap_row.pend_empadronamiento),
        'con_obs': _i(snap_row.con_obs),
        'con_runt': _i(snap_row.con_runt),
        'facturadas_historico': _i(snap_row.facturadas_historico),
        'matriz': matriz,
        'por_distribuidor': por_distribuidor,
        'por_observacion': por_observacion,
        'por_anio': por_anio,
    }


# ---------------------------------------------------------------------------
# F4 — Cobertura de Repuestos
# ---------------------------------------------------------------------------

async def _query_f4(db: AsyncSession) -> dict:
    coverage_sql = text("""
        WITH
        part_all_codes AS (
            SELECT factory_part_number,
                   UPPER(TRIM(REPLACE(factory_part_number, ' ', ''))) AS norm_code
            FROM parts_references
            UNION ALL
            SELECT pr.factory_part_number,
                   UPPER(TRIM(REPLACE(
                       CASE WHEN jsonb_typeof(elem) = 'string' THEN elem #>> '{}'
                            ELSE elem->>'code'
                       END, ' ', ''))) AS norm_code
            FROM parts_references pr,
                 jsonb_array_elements(pr.prev_codes) AS elem
            WHERE jsonb_array_length(pr.prev_codes) > 0
              AND (
                  (jsonb_typeof(elem) = 'string'  AND (elem #>> '{}') != '')
                  OR (jsonb_typeof(elem) = 'object' AND elem->>'code' IS NOT NULL AND elem->>'code' != '')
              )
        ),
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
        ),
        ref_coverage AS (
            SELECT r.factory_part_number,
                MAX(CASE
                    WHEN a.pn IS NOT NULL THEN 3
                    WHEN c.pn IS NOT NULL THEN 2
                    WHEN p.pn IS NOT NULL THEN 1
                    ELSE 0
                END) AS score
            FROM parts_references r
            JOIN part_all_codes pac ON pac.factory_part_number = r.factory_part_number
            LEFT JOIN aqui      a ON a.pn = pac.norm_code
            LEFT JOIN en_camino c ON c.pn = pac.norm_code
            LEFT JOIN pedido    p ON p.pn = pac.norm_code
            WHERE EXISTS (
                SELECT 1 FROM parts_manual_items pmi
                WHERE pmi.factory_part_number = r.factory_part_number
            )
            GROUP BY r.factory_part_number
        )
        SELECT
            COUNT(*)                               AS total,
            COUNT(CASE WHEN score = 3 THEN 1 END) AS aqui,
            COUNT(CASE WHEN score = 2 THEN 1 END) AS en_camino,
            COUNT(CASE WHEN score = 1 THEN 1 END) AS pedido,
            COUNT(CASE WHEN score = 0 THEN 1 END) AS sin_cobertura
        FROM ref_coverage
    """)

    # Valor materializado = SUM(total_declared_value) de lotes en órdenes activas de repuestos
    # Mismo universo que fob_pedido_sql para que el ratio sea coherente
    fob_materializado_sql = text("""
        SELECT COALESCE(SUM(spl.total_declared_value), 0) AS fob_materializado
        FROM spare_part_lots spl
        JOIN shipment_orders so ON so.id = spl.shipment_order_id
        WHERE so.computed_status != 'completado'
          AND so.is_spare_part = true
    """)

    # Valor pedido = FOB comprometido en órdenes activas de repuestos
    fob_pedido_sql = text("""
        SELECT COALESCE(SUM(spi.qty_ordered * COALESCE(spi.unit_price, spi.fob_pi, 0)), 0) AS fob_pedido
        FROM spare_part_items spi
        JOIN spare_part_lots spl ON spl.id = spi.lot_id
        JOIN shipment_orders so ON so.id = spl.shipment_order_id
        WHERE so.computed_status != 'completado'
          AND so.is_spare_part = true
          AND spi.status != 'CANCELLED'
    """)

    cov_row = (await db.execute(coverage_sql)).fetchone()
    fob_mat_row = (await db.execute(fob_materializado_sql)).fetchone()
    fob_pedido_row = (await db.execute(fob_pedido_sql)).fetchone()

    total = _i(cov_row.total) if cov_row else 0
    fob_materializado = _f(fob_mat_row.fob_materializado) if fob_mat_row else 0.0
    fob_pedido = _f(fob_pedido_row.fob_pedido) if fob_pedido_row else 0.0

    pct_materializado = _pct(fob_materializado, fob_pedido)
    pct_mat_pbar = min(100, pct_materializado)
    mat_status = 'ok' if pct_materializado >= 80 else ('warn' if pct_materializado >= 50 else 'crit')
    fob_pendiente = max(0.0, fob_pedido - fob_materializado)

    if total == 0 and fob_pedido == 0:
        return {
            'sin_datos': True,
            'total': 0, 'aqui': 0, 'en_camino': 0, 'pedido': 0, 'sin_cobertura': 0,
            'fob_pedido': 0.0, 'fob_materializado': 0.0, 'fob_pendiente': 0.0,
            'pct_materializado': 0, 'pct_mat_pbar': 0,
            'mat_status': 'crit',
        }

    return {
        'sin_datos': False,
        'total': total,
        'aqui': _i(cov_row.aqui) if cov_row else 0,
        'en_camino': _i(cov_row.en_camino) if cov_row else 0,
        'pedido': _i(cov_row.pedido) if cov_row else 0,
        'sin_cobertura': _i(cov_row.sin_cobertura) if cov_row else 0,
        'fob_pedido': fob_pedido,
        'fob_materializado': fob_materializado,
        'fob_pendiente': fob_pendiente,
        'pct_materializado': pct_materializado,
        'pct_mat_pbar': pct_mat_pbar,
        'mat_status': mat_status,
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
            COALESCE(SUM(spi.qty_ordered * COALESCE(spi.unit_price, spi.fob_pi, pr.preliminary_fob, 0)), 0) AS fob_riesgo
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
            'total_refs': 0,
            'conic': _make_conic([]),
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

    # Compute pct for each class + build conic
    total_rot_refs = sum(c['refs'] for c in clases) + sin_clasificar_refs
    rot_colors = {'alta': '#66BA88', 'media': '#D9B05A', 'baja': '#E07878'}

    for c in clases:
        c['pct'] = _pct(c['refs'], total_rot_refs, 1)

    slices = [(rot_colors.get(c['clase'], '#AEB6BF'), _pct(c['refs'], total_rot_refs, 2)) for c in clases]
    if sin_clasificar_refs > 0:
        slices.append(('#AEB6BF', _pct(sin_clasificar_refs, total_rot_refs, 2)))

    svg_rot = _make_svg_donut(slices, size=110,
                              center_val=str(total_rot_refs), center_sub='refs')

    return {
        'sin_datos': not has_data,
        'clases': clases,
        'sin_clasificar_refs': sin_clasificar_refs,
        'sin_clasificar_fob': sin_clasificar_fob,
        'total_riesgo': total_riesgo,
        'total_refs': total_rot_refs,
        'svg': svg_rot,
    }


# ---------------------------------------------------------------------------
# F6 — Backorders
# ---------------------------------------------------------------------------

async def _query_f6(desde: date, hasta: date, db: AsyncSession) -> dict:
    sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE bo.resolved = false)                           AS activos,
            COUNT(*) FILTER (WHERE bo.resolved = true
                             AND bo.resolved_at::date BETWEEN :desde AND :hasta)  AS resueltos_periodo,
            COUNT(DISTINCT bo.part_number) FILTER (WHERE bo.resolved = false)     AS refs_afectadas,
            COALESCE(SUM(
                CASE WHEN bo.resolved = false
                THEN bo.qty_pending * COALESCE(spi.unit_price, spi.fob_pi, 0)
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
    # Counts usan los mismos filtros que el FOB: solo lotes sin PL recibido.
    # cambiar_pendiente solo cuenta reducciones (new_quantity < original) para
    # alinear con markedCambiarConReduccion del frontend.
    counts_sql = text("""
        SELECT
            COUNT(*) FILTER (
                WHERE pod.decision = 'cancelar' AND pod.executed_at IS NULL
            ) AS cancelar_pendiente,
            COUNT(*) FILTER (
                WHERE pod.decision = 'cambiar'
                  AND pod.executed_at IS NULL
                  AND pod.new_quantity IS NOT NULL
                  AND pod.new_quantity < COALESCE(
                      pod.original_quantity,
                      (SELECT SUM(spi2.qty_ordered)
                       FROM spare_part_items spi2
                       JOIN spare_part_lots spl2 ON spl2.id = spi2.lot_id
                       WHERE spl2.lot_identifier = pod.lot_identifier
                         AND UPPER(TRIM(REPLACE(spi2.part_number, ' ', ''))) =
                             UPPER(TRIM(REPLACE(pod.factory_part_number, ' ', ''))))
                  )
            ) AS cambiar_pendiente,
            COUNT(*) FILTER (
                WHERE pod.decision = 'cancelar'
                  AND pod.executed_at IS NOT NULL
                  AND pod.executed_at::date BETWEEN :desde AND :hasta
            ) AS cancelar_ejecutado
        FROM part_order_decisions pod
        JOIN spare_part_lots spl ON spl.lot_identifier = pod.lot_identifier
        WHERE spl.packing_list_received = FALSE
    """)

    # FOB total ajuste = cancelar (qty total × precio) + cambiar (delta reducción × precio)
    # Usa MAX(unit_price, fob_pi) × SUM(qty) por lote — idéntico a low-rotation-ordered en la app
    fob_pendiente_sql = text("""
        SELECT COALESCE(SUM(adj_fob), 0) AS fob
        FROM (
            SELECT MAX(COALESCE(spi.unit_price, spi.fob_pi, 0)) * SUM(spi.qty_ordered)::numeric AS adj_fob
            FROM part_order_decisions pod
            JOIN spare_part_lots spl ON spl.lot_identifier = pod.lot_identifier
            JOIN spare_part_items spi
                ON spi.lot_id = spl.id
               AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) =
                   UPPER(TRIM(REPLACE(pod.factory_part_number, ' ', '')))
            WHERE pod.decision = 'cancelar'
              AND pod.executed_at IS NULL
              AND spi.status != 'CANCELLED'
              AND spl.packing_list_received = FALSE
            GROUP BY pod.factory_part_number, pod.lot_identifier

            UNION ALL

            SELECT MAX(COALESCE(spi.unit_price, spi.fob_pi, 0)) *
                   GREATEST(0, (COALESCE(pod.original_quantity, SUM(spi.qty_ordered)) - pod.new_quantity))::numeric AS adj_fob
            FROM part_order_decisions pod
            JOIN spare_part_lots spl ON spl.lot_identifier = pod.lot_identifier
            JOIN spare_part_items spi
                ON spi.lot_id = spl.id
               AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) =
                   UPPER(TRIM(REPLACE(pod.factory_part_number, ' ', '')))
            WHERE pod.decision = 'cambiar'
              AND pod.executed_at IS NULL
              AND pod.new_quantity IS NOT NULL
              AND spi.status != 'CANCELLED'
              AND spl.packing_list_received = FALSE
            GROUP BY pod.factory_part_number, pod.lot_identifier, pod.original_quantity, pod.new_quantity
        ) adj
    """)

    fob_ejecutado_sql = text("""
        SELECT COALESCE(SUM(adj_fob), 0) AS fob
        FROM (
            SELECT MAX(COALESCE(spi.unit_price, spi.fob_pi, 0)) * SUM(spi.qty_ordered)::numeric AS adj_fob
            FROM part_order_decisions pod
            JOIN spare_part_lots spl ON spl.lot_identifier = pod.lot_identifier
            JOIN spare_part_items spi
                ON spi.lot_id = spl.id
               AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) =
                   UPPER(TRIM(REPLACE(pod.factory_part_number, ' ', '')))
            WHERE pod.decision = 'cancelar'
              AND pod.executed_at IS NOT NULL
              AND pod.executed_at::date BETWEEN :desde AND :hasta
              AND spi.status != 'CANCELLED'
              AND spl.packing_list_received = FALSE
            GROUP BY pod.factory_part_number, pod.lot_identifier

            UNION ALL

            SELECT MAX(COALESCE(spi.unit_price, spi.fob_pi, 0)) *
                   GREATEST(0, (COALESCE(pod.original_quantity, SUM(spi.qty_ordered)) - pod.new_quantity))::numeric AS adj_fob
            FROM part_order_decisions pod
            JOIN spare_part_lots spl ON spl.lot_identifier = pod.lot_identifier
            JOIN spare_part_items spi
                ON spi.lot_id = spl.id
               AND UPPER(TRIM(REPLACE(spi.part_number, ' ', ''))) =
                   UPPER(TRIM(REPLACE(pod.factory_part_number, ' ', '')))
            WHERE pod.decision = 'cambiar'
              AND pod.executed_at IS NOT NULL
              AND pod.executed_at::date BETWEEN :desde AND :hasta
              AND pod.new_quantity IS NOT NULL
              AND spi.status != 'CANCELLED'
              AND spl.packing_list_received = FALSE
            GROUP BY pod.factory_part_number, pod.lot_identifier, pod.original_quantity, pod.new_quantity
        ) adj
    """)

    cnt_row = (await db.execute(counts_sql, {'desde': desde, 'hasta': hasta})).fetchone()
    fob_p_row = (await db.execute(fob_pendiente_sql)).fetchone()
    fob_e_row = (await db.execute(fob_ejecutado_sql, {'desde': desde, 'hasta': hasta})).fetchone()

    cancelar_pendiente = _i(cnt_row.cancelar_pendiente) if cnt_row else 0
    cambiar_pendiente  = _i(cnt_row.cambiar_pendiente)  if cnt_row else 0
    cancelar_ejecutado = _i(cnt_row.cancelar_ejecutado) if cnt_row else 0

    if cancelar_pendiente == 0 and cambiar_pendiente == 0 and cancelar_ejecutado == 0:
        return {
            'sin_datos': True,
            'cancelar_pendiente': 0, 'cambiar_pendiente': 0,
            'cancelar_ejecutado': 0,
            'fob_cancelar_pendiente': 0.0, 'fob_cancelar_ejecutado': 0.0,
        }

    return {
        'sin_datos': False,
        'cancelar_pendiente': cancelar_pendiente,
        'cambiar_pendiente': cambiar_pendiente,
        'cancelar_ejecutado': cancelar_ejecutado,
        'fob_cancelar_pendiente': _f(fob_p_row.fob) if fob_p_row else 0.0,
        'fob_cancelar_ejecutado': _f(fob_e_row.fob) if fob_e_row else 0.0,
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
    por_concepto_map = {c: {'count': 0, 'fob': 0.0} for c in _CONCEPTS}
    for r in desp_rows:
        tipo = (r.type or '').upper()
        if tipo in por_concepto_map:
            por_concepto_map[tipo] = {'count': _i(r.total), 'fob': _f(r.fob)}

    total_despachos = sum(v['count'] for v in por_concepto_map.values())
    total_fob = sum(v['fob'] for v in por_concepto_map.values())
    anuladas = _i(anu_row.anuladas) if anu_row else 0

    # Add pct per concepto
    _CONCEPT_COLORS = {
        'PEDIDO': 'var(--info)',
        'GARANTIA': 'var(--violet)',
        'CORTESIA': 'var(--ok)',
        'VEHICULO_PROPIO': 'var(--warn)',
    }

    por_concepto = [
        {
            'tipo': c,
            'count': por_concepto_map[c]['count'],
            'fob': por_concepto_map[c]['fob'],
            'pct': _pct(por_concepto_map[c]['count'], total_despachos) if total_despachos else 0,
            'color': _CONCEPT_COLORS.get(c, 'var(--muted)'),
        }
        for c in _CONCEPTS
    ]

    sin_datos = total_despachos == 0 and anuladas == 0
    return {
        'sin_datos': sin_datos,
        'total': total_despachos,
        'fob': total_fob,
        'por_concepto': por_concepto,
        'anuladas': anuladas,
    }


# ---------------------------------------------------------------------------
# Maestro de Partes
# ---------------------------------------------------------------------------

async def _query_maestro(db: AsyncSession) -> dict:
    # con_precio = partes con cualquier "Valor Final" disponible en el Maestro:
    # precio manual (part_catalog) O precio calculado desde FOB (avg_fob_cost / preliminary_fob)
    sql = text("""
        SELECT
            (SELECT COUNT(*) FROM parts_references) AS total_refs,
            (SELECT COUNT(*)
             FROM parts_references pr
             WHERE pr.avg_fob_cost IS NOT NULL
                OR pr.preliminary_fob IS NOT NULL
                OR EXISTS (
                    SELECT 1 FROM part_catalog pc
                    WHERE pc.part_code = pr.factory_part_number
                )
            ) AS con_precio
    """)
    row = (await db.execute(sql)).fetchone()
    total = _i(row.total_refs) if row else 0
    con = _i(row.con_precio) if row else 0
    sin = max(0, total - con)
    pct = _pct(con, total)
    status = 'ok' if pct >= 90 else ('warn' if pct >= 70 else 'crit')
    return {
        'sin_datos': total == 0,
        'total_refs': total,
        'con_precio': con,
        'sin_precio': sin,
        'pct_con_precio': pct,
        'precio_status': status,
    }


# ---------------------------------------------------------------------------
# TRM
# ---------------------------------------------------------------------------

async def _query_logo(db: AsyncSession) -> str | None:
    row = (await db.execute(text("SELECT value FROM system_config WHERE key = 'logo_base64'"))).fetchone()
    if row and row.value:
        val = row.value
        if "," in val:
            val = val.split(",", 1)[1]
        return val
    return None


async def _query_trm(db: AsyncSession):
    row = (await db.execute(text("SELECT value FROM system_config WHERE key = 'pricing.trm'"))).fetchone()
    if row and row.value:
        try:
            return float(row.value)
        except (TypeError, ValueError):
            pass
    return 3800.0  # default from pricing service


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
    Runs all section queries sequentially (AsyncSession not safe for concurrent
    execution on one connection), builds Jinja2 context, renders the HTML template,
    and converts to PDF bytes via WeasyPrint in a thread pool executor (non-blocking).
    """
    f2 = await _query_f2(desde, hasta, db)
    f3 = await _query_f3(db)
    f4 = await _query_f4(db)
    f5 = await _query_f5(db)
    f6 = await _query_f6(desde, hasta, db)
    f7 = await _query_f7(desde, hasta, db)
    f8 = await _query_f8(desde, hasta, db)
    trm = await _query_trm(db)
    maestro = await _query_maestro(db)
    logo_base64 = await _query_logo(db)

    now_col5 = datetime.now(tz=COL_5)
    generado_at = now_col5.strftime('%d/%m/%Y %H:%M') + ' (UTC-5)'

    bo_status = 'ok' if f6['refs_afectadas'] == 0 else ('warn' if f6['refs_afectadas'] < 50 else 'crit')

    context = {
        'meta': {
            'periodo_label': _periodo_label(desde, hasta),
            'generado_at': generado_at,
            'desde': desde.isoformat(),
            'hasta': hasta.isoformat(),
            'trm': trm,
        },
        'f2': f2,
        'f3': f3,
        'f4': f4,
        'f5': f5,
        'f6': f6,
        'f7': f7,
        'f8': f8,
        'trm': trm,
        'maestro': maestro,
        'logo_base64': logo_base64,
        'bo_status': bo_status,
    }

    template = _jinja_env.get_template('informe_gerencial.html')
    html_out = template.render(context)

    loop = asyncio.get_running_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        partial(HTML(string=html_out).write_pdf)
    )
    return pdf_bytes
