"""
Inventory counts -- per-referencia differences (odd/motored-conteos-
inventario, WU9; design §5.1, §5.2, §7).

ONE aggregate query builds the whole picture of a conteo, per code:

- system = the frozen snapshot `existencia` (the store's own bodegas,
  already summed at Iniciar); a code with no snapshot line is 0;
- round 1 = the sum of the non-voided round-1 readings across ALL
  locations; a snapshot referencia nobody read is 0. Unknown codes
  (readings with no referencia) are grouped by the code read;
- the conteo's live (non-cancelled) reconteo of that code, with the sum
  of the round-2 readings taken by its CURRENT assignee only (readings a
  disconnected pair left behind never count).

The rules on top are pure functions:

- final quantity (`cantidad_final`): a TERMINADO reconteo replaces round
  1 with its round-2 sum (no readings = found 0); otherwise round 1;
- value = difference x the frozen `costo_unitario`, to the cent. A code
  with no cost (no snapshot line, or `SIN_COSTO`) has no value;
- reconteo (design §7.7): a difference whose |value| reaches the frozen
  `umbral_reconteo_pesos`, or any difference with no cost;
- critical (§7.8): |value| reaches the frozen `umbral_critico_pesos`;
  an unvalued difference is never critical.

These are leader-only numbers: nothing here is ever sent to a pair.
"""
import uuid
from decimal import Decimal
from typing import List, NamedTuple, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import Conteo

CENTAVO = Decimal("0.01")
CERO = Decimal("0")
SIN_COSTO = "SIN_COSTO"
TERMINADO = "TERMINADO"
FILTROS = ("todas", "criticas", "reconteo")

_SQL_DIFERENCIAS = """
WITH sis AS (
    SELECT s.referencia_id, r.codigo, r.nombre, s.existencia,
           s.costo_unitario, s.costo_fuente
    FROM conteo_snapshot_linea s
    JOIN referencia r ON r.id = s.referencia_id
    WHERE s.conteo_id = :conteo_id
),
lec AS (
    SELECT lec1.referencia_id,
           COALESCE(r.codigo, lec1.codigo_leido) AS codigo,
           r.nombre, SUM(lec1.cantidad) AS ronda1,
           array_agg(DISTINCT u.nombre ORDER BY u.nombre) AS ubicaciones
    FROM conteo_lectura lec1
    JOIN ubicacion_inventario u ON u.id = lec1.ubicacion_id
    LEFT JOIN referencia r ON r.id = lec1.referencia_id
    WHERE lec1.conteo_id = :conteo_id AND lec1.ronda = 1
      AND lec1.anulada_en IS NULL
    GROUP BY lec1.referencia_id, COALESCE(r.codigo, lec1.codigo_leido),
             r.nombre
),
base AS (
    SELECT COALESCE(sis.referencia_id, lec.referencia_id) AS referencia_id,
           COALESCE(sis.codigo, lec.codigo) AS codigo,
           COALESCE(sis.nombre, lec.nombre) AS nombre,
           sis.existencia AS sistema, lec.ronda1,
           sis.costo_unitario, sis.costo_fuente, lec.ubicaciones
    FROM sis FULL JOIN lec ON lec.referencia_id = sis.referencia_id
),
rec AS (
    SELECT rc.id, rc.referencia_id, rc.codigo, rc.estado, rc.origen,
           rc.sesion_id, rc.misma_pareja_autorizada,
           SUM(lec2.cantidad) AS ronda2
    FROM conteo_reconteo rc
    LEFT JOIN conteo_lectura lec2
      ON lec2.reconteo_id = rc.id AND lec2.sesion_id = rc.sesion_id
     AND lec2.ronda = 2 AND lec2.anulada_en IS NULL
    WHERE rc.conteo_id = :conteo_id AND rc.estado <> 'CANCELADO'
    GROUP BY rc.id
)
SELECT COALESCE(base.referencia_id, rec.referencia_id) AS referencia_id,
       COALESCE(base.codigo, rec.codigo) AS codigo,
       COALESCE(base.nombre, rr.nombre) AS nombre,
       base.sistema, base.ronda1, base.costo_unitario, base.costo_fuente,
       base.ubicaciones, rec.id AS reconteo_id,
       rec.estado AS reconteo_estado, rec.origen AS reconteo_origen,
       rec.sesion_id AS reconteo_sesion_id, rec.misma_pareja_autorizada,
       rec.ronda2
FROM base
FULL JOIN rec ON rec.codigo = base.codigo
LEFT JOIN referencia rr ON rr.id = rec.referencia_id
"""

_SOLO_DIFERENCIAS = """
WHERE rec.id IS NOT NULL
   OR COALESCE(base.ronda1, 0) <> COALESCE(base.sistema, 0)
"""


class FilaCruda(NamedTuple):
    """One row of the aggregate, as the database returns it (NULL where
    a side is missing)."""

    referencia_id: Optional[uuid.UUID]
    codigo: str
    nombre: Optional[str]
    sistema: Optional[Decimal]
    ronda1: Optional[Decimal]
    costo_unitario: Optional[Decimal]
    costo_fuente: Optional[str]
    ubicaciones: Optional[List[str]]
    reconteo_id: Optional[uuid.UUID]
    reconteo_estado: Optional[str]
    reconteo_origen: Optional[str]
    reconteo_sesion_id: Optional[uuid.UUID]
    misma_pareja_autorizada: Optional[bool]
    ronda2: Optional[Decimal]


class ReconteoVista(NamedTuple):
    id: uuid.UUID
    estado: str
    origen: str
    sesion_id: Optional[uuid.UUID]
    misma_pareja_autorizada: bool


class Diferencia(NamedTuple):
    """One code's leader-only picture; `contado` is the final quantity."""

    referencia_id: Optional[uuid.UUID]
    codigo: str
    descripcion: Optional[str]
    ubicaciones: List[str]
    sistema: Decimal
    contado_ronda1: Decimal
    contado: Decimal
    diferencia: Decimal
    costo_unitario: Optional[Decimal]
    sin_costo: bool
    valor: Optional[Decimal]
    critico: bool
    reconteo: Optional[ReconteoVista]


# --- pure rules -------------------------------------------------------------


def cantidad_final(
        ronda1: Decimal, estado_reconteo: Optional[str],
        ronda2: Optional[Decimal]) -> Decimal:
    """The count that stands for a code: a TERMINADO reconteo's round-2
    sum (no readings = found 0) replaces round 1; anything else keeps
    round 1. WU10 writes `conteo_resultado` with it."""
    if estado_reconteo == TERMINADO:
        return CERO if ronda2 is None else ronda2
    return ronda1


def valorar(
        diferencia: Decimal, costo: Optional[Decimal]) -> Optional[Decimal]:
    """difference x unit cost, to the cent; None without a cost."""
    if costo is None:
        return None
    return (diferencia * costo).quantize(CENTAVO)


def requiere_reconteo(
        diferencia: Decimal, valor: Optional[Decimal],
        umbral: Decimal) -> bool:
    """A difference worth at least the frozen amount, or any difference
    that cannot be valued."""
    if diferencia == 0:
        return False
    return valor is None or abs(valor) >= umbral


def es_critica(valor: Optional[Decimal], umbral_critico: Decimal) -> bool:
    return valor is not None and abs(valor) >= umbral_critico


def _vista(fila: FilaCruda) -> Optional[ReconteoVista]:
    if fila.reconteo_id is None:
        return None
    return ReconteoVista(
        fila.reconteo_id, fila.reconteo_estado, fila.reconteo_origen,
        fila.reconteo_sesion_id, bool(fila.misma_pareja_autorizada))


def calcular(fila: FilaCruda, umbral_critico: Decimal) -> Diferencia:
    """A raw row turned into quantities, value and flags."""
    sistema = CERO if fila.sistema is None else fila.sistema
    ronda1 = CERO if fila.ronda1 is None else fila.ronda1
    contado = cantidad_final(ronda1, fila.reconteo_estado, fila.ronda2)
    diferencia = contado - sistema
    sin_costo = fila.costo_unitario is None or fila.costo_fuente in (
        None, SIN_COSTO)
    valor = None if sin_costo else valorar(diferencia, fila.costo_unitario)
    return Diferencia(
        referencia_id=fila.referencia_id, codigo=fila.codigo,
        descripcion=fila.nombre, ubicaciones=list(fila.ubicaciones or []),
        sistema=sistema, contado_ronda1=ronda1, contado=contado,
        diferencia=diferencia, costo_unitario=fila.costo_unitario,
        sin_costo=sin_costo, valor=valor,
        critico=es_critica(valor, umbral_critico), reconteo=_vista(fila))


def _orden(fila: Diferencia):
    valor = CERO if fila.valor is None else abs(fila.valor)
    return (fila.valor is None, -valor, -abs(fila.diferencia), fila.codigo)


def ordenar(filas: Sequence[Diferencia]) -> List[Diferencia]:
    """Largest |value| first; differences with no value go last, largest
    |quantity| first."""
    return sorted(filas, key=_orden)


def filtrar(filas: Sequence[Diferencia], filtro: str) -> List[Diferencia]:
    """'todas', 'criticas' (red ones) or 'reconteo' (with a live one)."""
    if filtro == "criticas":
        return [f for f in filas if f.critico]
    if filtro == "reconteo":
        return [f for f in filas if f.reconteo is not None]
    return list(filas)


# --- the aggregate ----------------------------------------------------------


async def filas(
        db: AsyncSession, conteo_id: uuid.UUID,
        solo_diferencias: bool = True) -> List[FilaCruda]:
    """The one aggregate query. With `solo_diferencias`, only codes whose
    round 1 differs from the system or that have a live reconteo."""
    sql = _SQL_DIFERENCIAS
    if solo_diferencias:
        sql += _SOLO_DIFERENCIAS
    resultado = await db.execute(text(sql), {"conteo_id": conteo_id})
    return [FilaCruda(*fila) for fila in resultado.all()]


async def listar(db: AsyncSession, conteo: Conteo) -> List[Diferencia]:
    """Every difference of a conteo, sorted (see `ordenar`)."""
    critico = conteo.umbral_critico_pesos
    if critico is None:
        return []
    crudas = await filas(db, conteo.id)
    return ordenar([calcular(f, critico) for f in crudas])
