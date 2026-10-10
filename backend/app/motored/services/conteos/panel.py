"""
Inventory counts -- the leader's live panel (odd/motored-conteos-
inventario, WU12b; design ADR-8, §6.1, §9.3).

The panel polls every 15 s, so the common answer must be cheap:

- `huella` is ONE query on the conteo row that also returns the panel
  version: the max reading `seq` (a new reading), the count of live
  readings (a void), a digest of the live reconteos' state and assignee
  (an assignment, a release; a cancel drops the row from it; the filter
  matches the partial index `uq_conteo_reconteo_codigo_activo`), a
  digest of the sessions' state, location and last-activity MINUTE (a
  join, a disconnect, a move, a device that went silent) and the
  conteo's own state and `updated_at`. Every part is an index scan, so
  no new index is needed.
  The minute bucket keeps heartbeats from refreshing every poll while
  the panel still sees a pair go quiet well inside the 2-minute rule;
- `armar` builds the full payload only when the version moved: the
  progress of every open conteo in one grouped query (shared with the
  list), the readings and units per pair in one grouped query, the
  session list, and the differences aggregate run ONCE for the summary,
  the partial accuracy and the units card.

Progress (owner rule): the universe is the snapshot referencias whose
existencia is not 0, the same rule as the close KPI; a referencia is
counted once it has a live round-1 reading. Round 2, voided readings and
codes outside the snapshot never move it.

The partial accuracy is the close KPI's formula (`cierre.calcular_kpi`)
over the codes counted so far: round-1 reads (surplus and unknown codes
included, valued with the close's cost fallback) and finished reconteos.
"""
import hashlib
import uuid
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import Conteo
from app.motored.services.conteos import cierre, diferencias, sesiones

BITS_VERSION = 53

_SQL_HUELLA = text("""
SELECT c.lider_id, c.es_prueba, c.estado, c.updated_at,
  (SELECT max(l.seq) FROM conteo_lectura l
    WHERE l.conteo_id = c.id) AS max_seq,
  (SELECT count(*) FROM conteo_lectura l
    WHERE l.conteo_id = c.id AND l.anulada_en IS NULL) AS vigentes,
  (SELECT md5(string_agg(
      r.id::text || r.estado || coalesce(r.sesion_id::text, ''),
      ',' ORDER BY r.id))
    FROM conteo_reconteo r
    WHERE r.conteo_id = c.id AND r.estado <> 'CANCELADO') AS reconteos,
  (SELECT md5(string_agg(
      s.id::text || s.estado
        || coalesce(s.ubicacion_actual_id::text, '')
        || floor(extract(epoch FROM s.ultima_actividad_en) / 60)::text,
      ',' ORDER BY s.id))
    FROM conteo_sesion s WHERE s.conteo_id = c.id) AS sesiones
FROM conteo c
WHERE c.id = :conteo_id
""")

_SQL_PROGRESO = text("""
SELECT s.conteo_id, count(*) AS universo,
       sum(CASE WHEN EXISTS (
           SELECT 1 FROM conteo_lectura l
           WHERE l.conteo_id = s.conteo_id AND l.ronda = 1
             AND l.referencia_id = s.referencia_id
             AND l.anulada_en IS NULL) THEN 1 ELSE 0 END) AS contadas
FROM conteo_snapshot_linea s
WHERE s.conteo_id IN :ids AND s.existencia <> 0
GROUP BY s.conteo_id
""").bindparams(bindparam("ids", expanding=True))

_SQL_POR_SESION = text("""
SELECT l.sesion_id, count(*) AS lecturas, max(l.recibida_en) AS ultima,
       coalesce(sum(l.cantidad), 0) AS unidades
FROM conteo_lectura l
WHERE l.conteo_id = :conteo_id AND l.anulada_en IS NULL
GROUP BY l.sesion_id
""")


# (lecturas, ultima_lectura_en, unidades) of a pair with no live reading.
_SIN_LECTURAS = (0, None, Decimal("0"))


class Huella(NamedTuple):
    """Who owns the conteo (scoping) and its current panel version."""

    lider_id: Optional[uuid.UUID]
    version: int
    es_prueba: bool = False


class Progreso(NamedTuple):
    refs_universo: int
    refs_contadas: int


# --- pure rules -------------------------------------------------------------


def version_de(partes: Sequence) -> int:
    """A stable, JavaScript-safe integer digest of the change markers
    (blake2b, so it is the same in every process)."""
    digest = hashlib.blake2b(
        repr(tuple(partes)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> (64 - BITS_VERSION)


def _es_diferencia(cruda: diferencias.FilaCruda) -> bool:
    """The `/diferencias` filter: a live reconteo, or round 1 differs
    from the system."""
    sistema = cruda.sistema or diferencias.CERO
    ronda1 = cruda.ronda1 or diferencias.CERO
    return cruda.reconteo_id is not None or ronda1 != sistema


def resumen_diferencias(
        crudas: Sequence[diferencias.FilaCruda],
        umbral_critico: Optional[Decimal]) -> Dict[str, int]:
    """The same three counts as `GET /diferencias`, plus `contadas`:
    the codes whose `Contado` is above 0 (the "Contadas (N)" chip)."""
    if umbral_critico is None:
        return {"criticas": 0, "en_reconteo": 0, "total": 0,
                "contadas": 0}
    filas = [diferencias.calcular(c, umbral_critico)
             for c in crudas if _es_diferencia(c)]
    return {
        "criticas": sum(1 for f in filas if f.critico),
        "en_reconteo": sum(1 for f in filas if f.reconteo is not None),
        "total": len(filas),
        "contadas": sum(
            1 for c in crudas if diferencias.contado_de(c) > 0)}


def contadas(
        crudas: Sequence[diferencias.FilaCruda],
) -> List[diferencias.FilaCruda]:
    """Codes counted so far: a live round-1 reading or a finished
    reconteo."""
    return [c for c in crudas if c.ronda1 is not None
            or c.reconteo_estado == diferencias.TERMINADO]


def unidades(crudas: Sequence[diferencias.FilaCruda]) -> Dict[str, Decimal]:
    """The "Unidades contadas" card over the differences aggregate.

    `contado` is `diferencias.contado_de`, the table's own column. Per
    code, the expected units are the system's (a negative system counts
    as 0): `dentro` is the part of the count within them, `sobrantes`
    the rest (codes the system lacks and unknown codes are all surplus).
    Total = dentro + sobrantes; `sistema_total` is the expected units of
    the whole snapshot."""
    dentro = sobrantes = sistema_total = diferencias.CERO
    for cruda in crudas:
        esperado = max(cruda.sistema or diferencias.CERO, diferencias.CERO)
        contado = diferencias.contado_de(cruda)
        dentro += min(contado, esperado)
        sobrantes += max(diferencias.CERO, contado - esperado)
        sistema_total += esperado
    return {
        "total_contado": dentro + sobrantes, "dentro_esperado": dentro,
        "sobrantes": sobrantes, "sistema_total": sistema_total}


# --- queries ----------------------------------------------------------------


async def huella(
        db: AsyncSession, conteo_id: uuid.UUID) -> Optional[Huella]:
    """The one cheap query of every poll; None when the conteo does not
    exist."""
    fila = (await db.execute(
        _SQL_HUELLA, {"conteo_id": conteo_id})).first()
    if fila is None:
        return None
    return Huella(fila[0], version_de(fila[2:]), bool(fila[1]))


async def progreso(
        db: AsyncSession,
        ids: Sequence[uuid.UUID]) -> Dict[uuid.UUID, Progreso]:
    """Counted / universe referencias of several conteos at once (one
    grouped query; a conteo with no snapshot has no entry)."""
    if not ids:
        return {}
    filas = (await db.execute(_SQL_PROGRESO, {"ids": list(ids)})).all()
    return {f[0]: Progreso(int(f[1]), int(f[2] or 0)) for f in filas}


async def _por_sesion(
        db: AsyncSession, conteo_id: uuid.UUID) -> Dict[uuid.UUID, tuple]:
    filas = (await db.execute(
        _SQL_POR_SESION, {"conteo_id": conteo_id})).all()
    return {f[0]: (int(f[1]), f[2], Decimal(f[3])) for f in filas}


async def _exactitud(
        db: AsyncSession, conteo: Conteo,
        crudas: Sequence[diferencias.FilaCruda]) -> Optional[dict]:
    leidas = contadas(crudas)
    if not leidas or conteo.umbral_critico_pesos is None:
        return None
    kpi = cierre.calcular_kpi(
        await cierre.lineas_de(db, conteo, leidas))
    return {
        "refs_evaluadas": kpi.refs_universo,
        "refs_exactas": kpi.refs_exactas,
        "exactitud_pct": kpi.exactitud_pct,
        "valor_diferencia_neta": kpi.valor_diferencia_neta,
        "valor_diferencia_abs": kpi.valor_diferencia_abs}


def _pareja(fila: sesiones.FilaSesion, lecturas: Tuple) -> dict:
    sesion, ubicacion = fila.sesion, fila.ubicacion
    return {
        "sesion_id": sesion.id, "numero": fila.numero,
        "etiqueta": sesiones.etiqueta(
            fila.numero, [p.nombre for p in fila.integrantes]),
        "ubicacion_actual": (None if ubicacion is None else {
            "id": ubicacion.id, "nombre": ubicacion.nombre}),
        "lecturas": lecturas[0], "ultima_lectura_en": lecturas[1],
        "unidades": lecturas[2],
        "ultima_actividad_en": sesion.ultima_actividad_en,
        "estado": sesion.estado}


def _progreso_total(
        avance: Progreso, por_sesion: Dict[uuid.UUID, tuple]) -> dict:
    ultimas = [v[1] for v in por_sesion.values() if v[1] is not None]
    return {
        "refs_universo": avance.refs_universo,
        "refs_contadas": avance.refs_contadas,
        "lecturas_total": sum(v[0] for v in por_sesion.values()),
        "ultima_lectura_en": max(ultimas) if ultimas else None}


async def armar(db: AsyncSession, conteo: Conteo, version: int) -> dict:
    """The full panel payload (the version moved)."""
    avance = (await progreso(db, [conteo.id])).get(
        conteo.id, Progreso(0, 0))
    por_sesion = await _por_sesion(db, conteo.id)
    filas = await sesiones.listar(db, conteo.id)
    crudas = await diferencias.filas(
        db, conteo.id, solo_diferencias=False)
    return {
        "version": version, "sin_cambios": False,
        "estado": conteo.estado,
        "progreso": _progreso_total(avance, por_sesion),
        "exactitud_parcial": await _exactitud(db, conteo, crudas),
        "parejas": [_pareja(f, por_sesion.get(f.sesion.id, _SIN_LECTURAS))
                    for f in filas],
        "unidades": unidades(crudas),
        "diferencias_resumen": resumen_diferencias(
            crudas, conteo.umbral_critico_pesos)}
