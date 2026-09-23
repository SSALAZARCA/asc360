"""
Motored Pedidos — Fase 3 "Cargas: Tipo Declarado", Phase 1 "Pre-Deploy Data
Check" (sdd/motored-cargas-tipo-declarado; design D2, tasks 1.1/1.2).

Antes de este cambio, `carga_archivo` podía quedar huérfana en `PENDIENTE`
de DOS formas distintas, ambas cerradas por el mismo `PATCH /cargas/{id}`
que este cambio le saca esa capacidad (design D1: `PATCH` ya no acepta
`tipo`, y el frontend nuevo nunca deja pasar un `POST` sin período cuando
el tipo lo exige):

  A. **Sin tipo** (`tipo IS NULL`): el viejo flujo detectaba el tipo por
     firma de encabezado y, si no lo lograba, dejaba la fila pendiente de
     que un humano completara `tipo` a mano. Estructuralmente imposible de
     completar después de este cutover.
  B. **Con tipo, sin período** (`tipo IS NOT NULL AND periodo_desde IS
     NULL`, para un tipo que declara período): el tipo SÍ se detectó, pero
     el usuario cerró el modal viejo antes de completar el Paso 2 (período).
     El nuevo flujo nunca permite este estado a futuro (el período se pide
     ANTES de subir, cuando hace falta), pero una fila así, creada antes
     del cutover, queda igual de huérfana que el caso A -- el `PATCH` que
     la hubiera completado perdió esa capacidad.

Ninguno de los dos casos puede quedar en silencio (spec "PENDIENTE rows
have a stated outcome, never silence").

Qué hace este script (design D2, mecanismo de dos pasos, NO una migración
de Alembic -- deliberado, preserva "rollback nunca revierte un cambio de
esquema/datos"):

  1. Cuenta y lista, de forma READ-ONLY, las filas de cada uno de los dos
     casos.
  2. Si hay alguna, imprime cada fila (id, created_at, nombre_archivo) y el
     texto EXACTO del `UPDATE` de una sola vez que las cierra como
     `ANULADO` con un marcador de log distinto por caso -- pero NUNCA lo
     ejecuta. Un humano revisa la lista impresa y, si está de acuerdo,
     corre esos `UPDATE` a mano.

Uso: correr esto contra la base de datos de PRODUCCIÓN de Motored (p.ej.
desde la consola de Coolify: `python backend/scripts/verificar_cargas_
pendientes_sin_tipo.py`) ANTES del push combinado de la Fase 4 (Phase 2's
backend commit narrows `tipo` a no-inferible; corriendo esto antes evita
sorprender al deploy operator con filas que ya no van a poder completarse).

Es seguro correrlo las veces que haga falta: la ÚNICA acción que ejecuta es
un `SELECT`, nunca escribe nada -- correrlo dos veces antes de aplicar el
`UPDATE` a mano da exactamente el mismo resultado.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import List

# Añadir el raíz del proyecto al PYTHONPATH (mismo patrón que
# `create_motored_admin.py`/`create_superadmin.py`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import settings  # noqa: E402
from app.motored.database import motored_session_maker  # noqa: E402
from app.motored.models.carga_archivo import CargaArchivo  # noqa: E402
from app.motored.services.ingesta import periodo as periodo_mod  # noqa: E402

MOTIVO_CUTOVER_SIN_TIPO = "cutover_tipo_declarado_sin_tipo"
MOTIVO_CUTOVER_SIN_PERIODO = "cutover_tipo_declarado_sin_periodo"

# `coalesce(log, '{}'::jsonb)` en vez del `log || '...'` literal de la tabla
# de tasks: en Postgres, `NULL || jsonb` es `NULL` -- sin el coalesce, una
# fila cuyo `log` nunca se pobló perdería el marcador en vez de ganarlo.
# Mismo resultado final que el diseño pide (visible, no-silencioso), sin
# ese gap.
UPDATE_SQL = (
    "UPDATE carga_archivo "
    "SET estado = 'ANULADO', "
    f"log = coalesce(log, '{{}}'::jsonb) || '{{\"motivo\": \"{MOTIVO_CUTOVER_SIN_TIPO}\"}}'::jsonb "
    "WHERE estado = 'PENDIENTE' AND tipo IS NULL;"
)

_TIPOS_CON_PERIODO_SQL = ", ".join(f"'{t}'" for t in sorted(periodo_mod.TIPOS_QUE_DECLARAN_PERIODO))
UPDATE_SQL_SIN_PERIODO = (
    "UPDATE carga_archivo "
    "SET estado = 'ANULADO', "
    f"log = coalesce(log, '{{}}'::jsonb) || '{{\"motivo\": \"{MOTIVO_CUTOVER_SIN_PERIODO}\"}}'::jsonb "
    "WHERE estado = 'PENDIENTE' AND tipo IS NOT NULL AND periodo_desde IS NULL "
    f"AND tipo IN ({_TIPOS_CON_PERIODO_SQL});"
)


async def buscar_cargas_pendientes_sin_tipo(session: AsyncSession) -> List[CargaArchivo]:
    """Lectura pura y read-only: `estado='PENDIENTE' AND tipo IS NULL`
    (caso A -- nunca se detectó el tipo). Separada de `main()` a propósito
    -- es la única parte de este script que se puede probar sin una base
    de datos real (`FakeAsyncSession`, ver `tests/motored/test_verificar_
    cargas_pendientes_sin_tipo.py`)."""
    stmt = select(CargaArchivo).where(
        CargaArchivo.estado == "PENDIENTE", CargaArchivo.tipo.is_(None)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def buscar_cargas_pendientes_sin_periodo(session: AsyncSession) -> List[CargaArchivo]:
    """Lectura pura y read-only: caso B -- el tipo SÍ se detectó y declara
    período, pero el viejo Paso 2 nunca se completó (`periodo_desde IS
    NULL`). Distinto del caso A: acá `tipo` no es `None`, así que el
    `WHERE` de `buscar_cargas_pendientes_sin_tipo` nunca las alcanza -- sin
    esta segunda query quedarían huérfanas en silencio, exactamente lo que
    la spec prohíbe."""
    stmt = select(CargaArchivo).where(
        CargaArchivo.estado == "PENDIENTE",
        CargaArchivo.tipo.is_not(None),
        CargaArchivo.periodo_desde.is_(None),
        CargaArchivo.tipo.in_(periodo_mod.TIPOS_QUE_DECLARAN_PERIODO),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _formatear_grupo(huerfanas: List[CargaArchivo], titulo: str, update_sql: str) -> List[str]:
    lineas = [f"{titulo} ({len(huerfanas)}):"]
    for carga in huerfanas:
        lineas.append(
            f"  id={carga.id}  created_at={carga.created_at}  "
            f"nombre_archivo={carga.nombre_archivo!r}"
        )
    lineas.extend(["", "  UPDATE sugerido (revisar y correr a mano, nunca automático):", f"  {update_sql}"])
    return lineas


def formatear_reporte(sin_tipo: List[CargaArchivo], sin_periodo: List[CargaArchivo] = ()) -> str:
    """Arma el texto completo del reporte (lista de filas de cada caso + el
    `UPDATE` sugerido para cada uno) -- separado de `print()` para poder
    afirmar su contenido en un test sin capturar stdout. `sin_periodo` es
    opcional con default `()` para no romper callers/tests que todavía solo
    conocen el caso A."""
    sin_periodo = list(sin_periodo)
    if not sin_tipo and not sin_periodo:
        return "OK -- no hay filas PENDIENTE huérfanas (ni sin tipo, ni sin período). Nada que reconciliar."

    lineas: List[str] = []
    if sin_tipo:
        lineas.extend(_formatear_grupo(sin_tipo, "Sin tipo (tipo IS NULL)", UPDATE_SQL))
    if sin_periodo:
        if lineas:
            lineas.append("")
        lineas.extend(_formatear_grupo(sin_periodo, "Con tipo, sin período", UPDATE_SQL_SIN_PERIODO))

    lineas.extend([
        "",
        "Estas filas quedaron huérfanas de los flujos viejos de tipo/período:",
        "PATCH /cargas/{id} ya no acepta tipo, y el frontend nuevo ya nunca deja",
        "un período sin declarar cuando el tipo lo exige -- así que ninguna de",
        "estas filas va a poder completarse nunca más por la UI. Revisá las",
        "listas de arriba y, si estás de acuerdo, corré A MANO -- una sola vez",
        "cada uno -- los UPDATE de arriba contra la base de PRODUCCIÓN (este",
        "script NUNCA los ejecuta por sí mismo).",
    ])
    return "\n".join(lineas)


async def main() -> None:
    if not settings.MOTORED_DATABASE_URL:
        print(
            "ERROR: MOTORED_DATABASE_URL no está configurada. Corré este script "
            "contra la base de datos de PRODUCCIÓN de Motored (p.ej. desde la "
            "consola de Coolify), antes del push combinado de la Fase 4."
        )
        raise SystemExit(1)

    session_maker = motored_session_maker()
    async with session_maker() as session:
        sin_tipo = await buscar_cargas_pendientes_sin_tipo(session)
        sin_periodo = await buscar_cargas_pendientes_sin_periodo(session)
        print(formatear_reporte(sin_tipo, sin_periodo))


if __name__ == "__main__":
    asyncio.run(main())
