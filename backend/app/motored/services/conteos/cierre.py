"""
Inventory counts -- close a TOTAL count (odd/motored-conteos-inventario,
WU10; design §4.8, §5.1, §6.1, §7).

`cerrar` runs under the conteo row lock (`FOR UPDATE`): a readings batch
takes the same row `FOR SHARE`, so the close waits for batches in flight
and every later batch sees CERRADO; a second close waits, then finds
CERRADO and is refused. Guards: only from EN_RECONTEO (after
`terminar-ronda`); a PENDIENTE or ASIGNADO reconteo refuses the close
with the counts, unless it is forced with a reason, which cancels them
(those codes keep their round-1 quantity).

The result (`conteo_resultado`) has ONE line per code: every snapshot
referencia plus every code counted or sent to reconteo, unknown codes
(`referencia_id` NULL) included. The numbers come from the same aggregate
and the same rules as the live differences (`diferencias`):

- counted = `cantidad_final` (a TERMINADO reconteo's round 2, else round
  1); system = the snapshot store total, 0 outside the snapshot;
- cost = the snapshot's frozen cost. A code outside the snapshot takes
  the snapshot's fallback chain over the same carga (REFERENCIA: other
  stores weighted by quantity; MEDIANA; PRECIO), else SIN_COSTO, which
  has no value (NULL) and stays out of the money totals;
- owner override: the whole difference goes to the store's PRINCIPAL
  bodega (`sucursal.bodega_principal`, the `bodega` record of that code
  owned by the store); with none, the close is refused;
- `confirmada`: with a finished reconteo, whether round 2 kept the sign
  of the round-1 difference; NULL without one.

Accuracy KPI (§7.9): the universe is the codes with system != 0 or
counted > 0; exact = difference 0; stock value = Σ system x cost over
lines with system > 0; net and absolute differences over valued lines.

Nothing here commits: the API owns the transaction.
"""
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import (
    Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence,
)

from sqlalchemy import and_, bindparam, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.bodega import Bodega
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.conteo_resultado import ConteoResultado
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.services.conteos import acceso, diferencias, errores

EN_RECONTEO = "EN_RECONTEO"
CERRADO = "CERRADO"
ABIERTOS = ("PENDIENTE", "ASIGNADO")
CERO = diferencias.CERO
CENTAVO = diferencias.CENTAVO
CIEN = Decimal("100")

_SQL_COSTO_FUERA = text("""
WITH filas AS (
    SELECT d.referencia_id, d.existencia, d.costo_unitario
    FROM inventario_detalle d
    WHERE d.carga_id = :carga_id AND d.fecha_corte = :fecha_corte
      AND d.referencia_id IN :ids
), ajenas AS (
    SELECT referencia_id,
           sum(existencia * costo_unitario) / sum(existencia) AS costo
    FROM filas
    WHERE costo_unitario > 0 AND existencia > 0
    GROUP BY referencia_id
), mediana AS (
    SELECT referencia_id,
           CAST(percentile_cont(0.5) WITHIN GROUP (
               ORDER BY costo_unitario) AS numeric) AS costo
    FROM filas
    WHERE costo_unitario > 0
    GROUP BY referencia_id
)
SELECT r.id,
       round(coalesce(
           a.costo, m.costo,
           CASE WHEN r.precio_normal > 0 THEN r.precio_normal END), 2),
       CASE WHEN a.costo IS NOT NULL THEN 'REFERENCIA'
            WHEN m.costo IS NOT NULL THEN 'MEDIANA'
            WHEN r.precio_normal > 0 THEN 'PRECIO'
            ELSE 'SIN_COSTO' END
FROM referencia r
LEFT JOIN ajenas a ON a.referencia_id = r.id
LEFT JOIN mediana m ON m.referencia_id = r.id
WHERE r.id IN :ids
""").bindparams(bindparam("ids", expanding=True))


class Linea(NamedTuple):
    """One code of the result (the Excel and `GET /resultado` too)."""

    referencia_id: Optional[uuid.UUID]
    codigo: str
    descripcion: Optional[str]
    sistema: Decimal
    contado: Decimal
    diferencia: Decimal
    costo_unitario: Optional[Decimal]
    costo_fuente: str
    valor: Optional[Decimal]
    ubicaciones: List[str]
    con_reconteo: bool
    critico: bool
    confirmada: Optional[bool]
    bodega: Optional[str] = None


class Kpi(NamedTuple):
    refs_universo: int
    refs_exactas: int
    exactitud_pct: Optional[Decimal]
    valor_sistema: Decimal
    valor_diferencia_neta: Decimal
    valor_diferencia_abs: Decimal


class Cierre(NamedTuple):
    conteo: Conteo
    kpi: Kpi
    reconteos_cancelados: int


class Encabezado(NamedTuple):
    """The facts of the Excel's summary sheet."""

    tienda: str
    codigo_co: str
    lider: Optional[str]
    estado: str
    fecha_programada: date
    iniciado_en: Optional[datetime]
    ronda_terminada_en: Optional[datetime]
    cerrado_en: Optional[datetime]
    fecha_corte: Optional[date]
    bodega: Optional[str]
    kpi: Kpi
    motivo_cierre_forzado: Optional[str]


# --- pure rules -------------------------------------------------------------


def exigir_fase(conteo: Conteo) -> None:
    """Only the reconteo phase (after `terminar-ronda`) can close."""
    if conteo.estado != EN_RECONTEO:
        raise errores.EstadoInvalido(
            "Solo se cierra un conteo en reconteo: termine primero la "
            "ronda de conteo.", estado=conteo.estado)


def decidir_cierre(
        abiertos: Mapping[str, int], *, forzar: bool,
        motivo: Optional[str]) -> Optional[str]:
    """The trimmed reason of a forced close (None for a normal one).
    ReconteosAbiertos with the counts when a reconteo is still open and
    the close is not forced; MotivoRequerido for a forced one with no
    reason."""
    if forzar:
        limpio = (motivo or "").strip()
        if not limpio:
            raise errores.MotivoRequerido(
                "Escriba por qué cierra el conteo de forma forzada.")
        return limpio
    pendientes = int(abiertos.get("PENDIENTE", 0))
    asignados = int(abiertos.get("ASIGNADO", 0))
    if pendientes or asignados:
        raise errores.ReconteosAbiertos(
            pendientes=pendientes, asignados=asignados)
    return None


def con_costo(
        cruda: diferencias.FilaCruda, costo: Optional[Decimal],
        fuente: str) -> diferencias.FilaCruda:
    """A code outside the snapshot with its fallback cost."""
    return cruda._replace(costo_unitario=costo, costo_fuente=fuente)


def _signo(valor: Decimal) -> int:
    return (valor > 0) - (valor < 0)


def linea_de(
        cruda: diferencias.FilaCruda, umbral_critico: Decimal) -> Linea:
    """A raw aggregate row turned into its result line."""
    fila = diferencias.calcular(cruda, umbral_critico)
    terminado = cruda.reconteo_estado == diferencias.TERMINADO
    confirmada = None
    if terminado:
        ronda1 = fila.contado_ronda1 - fila.sistema
        confirmada = _signo(fila.diferencia) == _signo(ronda1)
    return Linea(
        referencia_id=fila.referencia_id, codigo=fila.codigo,
        descripcion=fila.descripcion, sistema=fila.sistema,
        contado=fila.contado, diferencia=fila.diferencia,
        costo_unitario=None if fila.sin_costo else fila.costo_unitario,
        costo_fuente=(diferencias.SIN_COSTO if fila.sin_costo
                      else cruda.costo_fuente),
        valor=fila.valor, ubicaciones=fila.ubicaciones,
        con_reconteo=terminado, critico=fila.critico,
        confirmada=confirmada)


def _orden(linea: Linea):
    valor = CERO if linea.valor is None else abs(linea.valor)
    return (linea.valor is None, -valor, -abs(linea.diferencia),
            linea.codigo)


def ordenar(lineas: Iterable[Linea]) -> List[Linea]:
    """Largest |value| first; unvalued lines last, largest |quantity|
    first (same order as the live differences)."""
    return sorted(lineas, key=_orden)


def _centavos(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_kpi(lineas: Sequence[Linea]) -> Kpi:
    """The accuracy KPI (§7.9) over the result lines."""
    universo = [f for f in lineas if f.sistema != 0 or f.contado > 0]
    exactas = sum(1 for f in universo if f.diferencia == 0)
    pct = None
    if universo:
        pct = _centavos(CIEN * exactas / len(universo))
    valores = [f.valor for f in lineas if f.valor is not None]
    stock = sum(
        (f.sistema * f.costo_unitario for f in lineas
         if f.costo_unitario is not None and f.sistema > 0), CERO)
    return Kpi(
        refs_universo=len(universo), refs_exactas=exactas,
        exactitud_pct=pct, valor_sistema=_centavos(stock),
        valor_diferencia_neta=_centavos(sum(valores, CERO)),
        valor_diferencia_abs=_centavos(sum(
            (abs(v) for v in valores), CERO)))


def kpi_de(conteo: Conteo) -> Kpi:
    """The KPI frozen on a closed conteo."""
    return Kpi(
        refs_universo=conteo.refs_universo or 0,
        refs_exactas=conteo.refs_exactas or 0,
        exactitud_pct=conteo.exactitud_pct,
        valor_sistema=conteo.valor_sistema or CERO,
        valor_diferencia_neta=conteo.valor_diferencia_neta or CERO,
        valor_diferencia_abs=conteo.valor_diferencia_abs or CERO)


# --- reads ------------------------------------------------------------------


async def bodega_principal(
        db: AsyncSession, sucursal_id: uuid.UUID) -> Optional[Bodega]:
    """The store's principal bodega record: the `bodega` whose code is
    `sucursal.bodega_principal` and that belongs to the store."""
    return (await db.execute(
        select(Bodega).join(Sucursal, and_(
            Sucursal.id == Bodega.sucursal_id,
            Sucursal.bodega_principal == Bodega.codigo))
        .where(Sucursal.id == sucursal_id))).scalars().first()


async def _costos_fuera(
        db: AsyncSession, conteo: Conteo,
        ids: Sequence[uuid.UUID]) -> Dict[uuid.UUID, tuple]:
    """referencia id -> (cost, source) for codes outside the snapshot."""
    if not ids:
        return {}
    filas = (await db.execute(_SQL_COSTO_FUERA, {
        "carga_id": conteo.snapshot_carga_id,
        "fecha_corte": conteo.snapshot_fecha_corte,
        "ids": list(ids)})).all()
    return {f[0]: (f[1], f[2]) for f in filas}


async def _lineas(db: AsyncSession, conteo: Conteo) -> List[Linea]:
    """Every code of the conteo as a result line, live."""
    crudas = await diferencias.filas(db, conteo.id, solo_diferencias=False)
    fuera = [c.referencia_id for c in crudas
             if c.costo_fuente is None and c.referencia_id is not None]
    costos = await _costos_fuera(db, conteo, fuera)
    salida = []
    for cruda in crudas:
        if cruda.costo_fuente is None:
            costo, fuente = costos.get(
                cruda.referencia_id, (None, diferencias.SIN_COSTO))
            cruda = con_costo(cruda, costo, fuente)
        salida.append(linea_de(cruda, conteo.umbral_critico_pesos))
    return salida


async def avance(db: AsyncSession, conteo: Conteo) -> List[Linea]:
    """The live lines of an open conteo, sorted, with the principal
    bodega's code when the store has one."""
    bodega = await bodega_principal(db, conteo.sucursal_id)
    codigo = None if bodega is None else bodega.codigo
    return ordenar(
        f._replace(bodega=codigo) for f in await _lineas(db, conteo))


async def resultado(db: AsyncSession, conteo: Conteo) -> List[Linea]:
    """The stored result lines of a closed conteo, sorted."""
    r = ConteoResultado
    filas = (await db.execute(
        select(r, Referencia.nombre, Bodega.codigo)
        .outerjoin(Referencia, Referencia.id == r.referencia_id)
        .outerjoin(Bodega, Bodega.id == r.bodega_ajuste_id)
        .where(r.conteo_id == conteo.id))).all()
    return ordenar(Linea(
        referencia_id=f[0].referencia_id, codigo=f[0].codigo,
        descripcion=f[1], sistema=f[0].existencia_sistema,
        contado=f[0].cantidad_contada, diferencia=f[0].diferencia,
        costo_unitario=f[0].costo_unitario, costo_fuente=f[0].costo_fuente,
        valor=f[0].valor_diferencia, ubicaciones=list(f[0].ubicaciones),
        con_reconteo=f[0].con_reconteo, critico=f[0].critico,
        confirmada=f[0].confirmada, bodega=f[2]) for f in filas)


async def encabezado(
        db: AsyncSession, conteo: Conteo,
        lineas: Sequence[Linea]) -> Encabezado:
    """The summary facts: the frozen KPI of a closed conteo, or the live
    one computed over `lineas`."""
    sucursal = await db.get(Sucursal, conteo.sucursal_id)
    lider = None
    if conteo.lider_id is not None:
        lider = await db.get(Usuario, conteo.lider_id)
    cerrado = conteo.estado == CERRADO
    return Encabezado(
        tienda=sucursal.nombre, codigo_co=sucursal.codigo_co,
        lider=None if lider is None else lider.nombre,
        estado=conteo.estado, fecha_programada=conteo.fecha_programada,
        iniciado_en=conteo.iniciado_en,
        ronda_terminada_en=conteo.ronda_terminada_en,
        cerrado_en=conteo.cerrado_en,
        fecha_corte=conteo.snapshot_fecha_corte,
        bodega=lineas[0].bodega if lineas else None,
        kpi=kpi_de(conteo) if cerrado else calcular_kpi(lineas),
        motivo_cierre_forzado=conteo.motivo_cierre_forzado)


# --- the close --------------------------------------------------------------


async def _abiertos(
        db: AsyncSession, conteo_id: uuid.UUID) -> Dict[str, int]:
    filas = (await db.execute(
        select(ConteoReconteo.estado, func.count(ConteoReconteo.id))
        .where(ConteoReconteo.conteo_id == conteo_id,
               ConteoReconteo.estado.in_(ABIERTOS))
        .group_by(ConteoReconteo.estado))).all()
    return {f[0]: int(f[1]) for f in filas}


async def _cancelar_abiertos(
        db: AsyncSession, conteo_id: uuid.UUID, ahora: datetime) -> int:
    """A reconteo a pair finishes meanwhile is no longer open when this
    statement gets its row lock, so it stays TERMINADO."""
    hecho = await db.execute(
        update(ConteoReconteo)
        .where(ConteoReconteo.conteo_id == conteo_id,
               ConteoReconteo.estado.in_(ABIERTOS))
        .values(estado="CANCELADO", cancelado_en=ahora))
    return int(hecho.rowcount or 0)


def _registro(
        conteo: Conteo, bodega_id: uuid.UUID, linea: Linea,
        ahora: datetime) -> dict:
    return dict(
        id=uuid.uuid4(), conteo_id=conteo.id,
        sucursal_id=conteo.sucursal_id, referencia_id=linea.referencia_id,
        codigo=linea.codigo, bodega_ajuste_id=bodega_id,
        existencia_sistema=linea.sistema, cantidad_contada=linea.contado,
        diferencia=linea.diferencia, costo_unitario=linea.costo_unitario,
        costo_fuente=linea.costo_fuente, valor_diferencia=linea.valor,
        ubicaciones=linea.ubicaciones, con_reconteo=linea.con_reconteo,
        critico=linea.critico, confirmada=linea.confirmada,
        cerrado_en=ahora)


def _marcar_cerrado(
        conteo: Conteo, kpi: Kpi, cerrado_por: uuid.UUID,
        motivo: Optional[str], ahora: datetime) -> None:
    conteo.estado = CERRADO
    conteo.cerrado_por = cerrado_por
    conteo.cerrado_en = ahora
    conteo.motivo_cierre_forzado = motivo
    conteo.codigo_hash = None
    for campo, valor in kpi._asdict().items():
        setattr(conteo, campo, valor)


async def cerrar(
        db: AsyncSession, conteo_id: uuid.UUID, cerrado_por: uuid.UUID,
        *, forzar: bool, motivo: Optional[str],
        ahora: datetime) -> Cierre:
    """EN_RECONTEO -> CERRADO: the result lines, the KPI, the link and
    every device session closed (see module)."""
    conteo = await acceso.bloquear_conteo(db, conteo_id)
    exigir_fase(conteo)
    limpio = decidir_cierre(
        await _abiertos(db, conteo.id), forzar=forzar, motivo=motivo)
    bodega = await bodega_principal(db, conteo.sucursal_id)
    if bodega is None:
        raise errores.SinBodegaPrincipal()
    cancelados = 0
    if forzar:
        cancelados = await _cancelar_abiertos(db, conteo.id, ahora)
    lineas = await _lineas(db, conteo)
    if lineas:
        await db.execute(insert(ConteoResultado), [
            _registro(conteo, bodega.id, f, ahora) for f in lineas])
    kpi = calcular_kpi(lineas)
    _marcar_cerrado(conteo, kpi, cerrado_por, limpio, ahora)
    await db.execute(
        update(ConteoSesion)
        .where(ConteoSesion.conteo_id == conteo.id,
               ConteoSesion.estado != "CERRADA")
        .values(estado="CERRADA"))
    await db.flush()
    return Cierre(conteo, kpi, cancelados)
