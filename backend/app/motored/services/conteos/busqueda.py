"""
Inventory counts -- the leader panel's "Contadas" chip, the reference
search and the per-reference detail
(odd/tasks/motored-conteo-panel-busqueda.md).

The differences table polls `todas` with the differences-only
aggregate. These reads run on demand only (a chip click, a debounced
search, a row opened), so the 15 s poll stays as cheap as before:

- "Contadas": every code of the conteo with `contado` > 0 (the table's
  own `diferencias.contado_de`), the latest live reading first;
- the search runs over EVERY code of the conteo, not only the
  differences: by code key (`lecturas.clave_codigo`, so hyphens,
  spaces and dots are ignored, partial keys match) or by part of the
  name, case-insensitive; it combines with the active chip;
- the detail of one code: its live readings per location and pair,
  with the time of the last one. Round 2 shows only the current
  assignee's readings of a live reconteo, the same rule as `Contado`.

Leader-only, like the differences: nothing here is sent to a pair.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import Conteo
from app.motored.services.conteos import diferencias
from app.motored.services.conteos.lecturas import clave_codigo

Diferencia = diferencias.Diferencia
# (ubicacion, ronda, sesion_id, cantidad, ultima_lectura_en)
LineaCruda = Tuple[str, int, uuid.UUID, Decimal, datetime]

_SQL_DETALLE = text("""
SELECT u.nombre AS ubicacion, l.ronda, l.sesion_id,
       SUM(l.cantidad) AS cantidad, max(l.recibida_en) AS ultima
FROM conteo_lectura l
JOIN ubicacion_inventario u ON u.id = l.ubicacion_id
LEFT JOIN referencia r ON r.id = l.referencia_id
LEFT JOIN conteo_reconteo rc ON rc.id = l.reconteo_id
WHERE l.conteo_id = :conteo_id AND l.anulada_en IS NULL
  AND COALESCE(r.codigo, l.codigo_leido) = :codigo
  AND (l.ronda = 1 OR (rc.estado <> 'CANCELADO'
                       AND l.sesion_id = rc.sesion_id))
GROUP BY u.nombre, l.ronda, l.sesion_id
ORDER BY ultima DESC, u.nombre
""")


# --- pure rules -------------------------------------------------------------


def coincide(fila: Diferencia, q: Optional[str]) -> bool:
    """The code's key contains the search's key, or the name contains
    the search text (case-insensitive). An empty search matches
    nothing."""
    texto = (q or "").strip().casefold()
    if not texto:
        return False
    clave = clave_codigo(texto)
    if clave and clave in clave_codigo(fila.codigo):
        return True
    return texto in (fila.descripcion or "").casefold()


def es_diferencia(fila: Diferencia) -> bool:
    """The `/diferencias` rule: a live reconteo, or round 1 differs
    from the system."""
    return (fila.reconteo is not None
            or fila.contado_ronda1 != fila.sistema)


def _mas_reciente(fila: Diferencia):
    marca = fila.ultima_lectura_en
    return (marca is None, -(marca.timestamp() if marca else 0),
            fila.codigo)


def contadas(filas: Sequence[Diferencia]) -> List[Diferencia]:
    """Codes with something counted, the latest live reading first."""
    return sorted((f for f in filas if f.contado > 0), key=_mas_reciente)


def cuenta_contadas(filas: Sequence[Diferencia]) -> int:
    return sum(1 for f in filas if f.contado > 0)


def cuentas(filas: Sequence[Diferencia]) -> Dict[str, int]:
    """The chips' numbers over the whole conteo (never the search)."""
    difs = [f for f in filas if es_diferencia(f)]
    return {
        "total": len(difs),
        "criticas": sum(1 for f in difs if f.critico),
        "en_reconteo": sum(1 for f in difs if f.reconteo is not None),
        "contadas": cuenta_contadas(filas)}


def elegir(
        filas: Sequence[Diferencia], filtro: str,
        q: Optional[str]) -> List[Diferencia]:
    """Search first (over every code), then the chip. Without a search
    'todas' is the differences only, as the polled table."""
    if q and q.strip():
        filas = [f for f in filas if coincide(f, q)]
    else:
        filas = [f for f in filas
                 if filtro == "contadas" or es_diferencia(f)]
    if filtro == "contadas":
        return contadas(filas)
    return diferencias.filtrar(diferencias.ordenar(filas), filtro)


def armar_detalle(
        crudas: Sequence[LineaCruda],
        etiquetas: Dict[uuid.UUID, str]) -> dict:
    """The detail payload: one line per location, round and pair."""
    lineas = [{
        "ubicacion": c[0], "ronda": int(c[1]),
        "sesion": {"id": c[2], "etiqueta": etiquetas.get(c[2], "")},
        "cantidad": c[3], "ultima_lectura_en": c[4]} for c in crudas]
    marcas = [c[4] for c in crudas if c[4] is not None]
    return {"lineas": lineas,
            "ultima_lectura_en": max(marcas) if marcas else None}


# --- queries ----------------------------------------------------------------


async def todas(db: AsyncSession, conteo: Conteo) -> List[Diferencia]:
    """Every code of the conteo, valued (empty with no thresholds)."""
    critico = conteo.umbral_critico_pesos
    if critico is None:
        return []
    crudas = await diferencias.filas(
        db, conteo.id, solo_diferencias=False)
    return [diferencias.calcular(c, critico) for c in crudas]


async def lineas_de(
        db: AsyncSession, conteo_id: uuid.UUID,
        codigo: str) -> List[LineaCruda]:
    """The live readings of one code, per location, round and pair."""
    resultado = await db.execute(
        _SQL_DETALLE, {"conteo_id": conteo_id, "codigo": codigo})
    return [tuple(f) for f in resultado.all()]
