"""
Inventory counts -- a pair's readings (odd/motored-conteos-inventario,
WU8; design §4.5, §6.2, §7, ADR-5, §9.2).

A device sends batches of up to 100 readings, each with its own client
UUID. The batch is ONE `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING
id`: a resend after a network failure stores nothing twice, and the
answer tells which ids are new and which were already stored.

Rules (design §7):
- every reading takes the session's CURRENT location; with none set the
  whole batch is SinUbicacion (409);
- codes are normalized `strip().upper()` and matched against ALL
  referencias (inactive included) by `upper(btrim(codigo))`. The exact
  stored code is tried first (unique index); only the misses pay the
  case-insensitive scan, and a code two referencias share is unknown;
- an unknown code is NOT stored: it comes back under `desconocidos` so
  the device beeps differently and asks "¿Registrar igual?". Sent again
  with `forzar_desconocido`, it is stored with `referencia_id` NULL;
- a `UBI-…` code that is not a referencia is a location label, refused
  as ES_UBICACION (the device must set it as the location);
- quantities follow the model CHECK (> 0, <= 99999, 2 decimals);
- this unit only writes round 1, while the conteo is EN_CONTEO; the
  `ronda` / `reconteo_id` columns are filled for round 2 by WU9.

Nothing here commits: the API owns the transaction. Nothing returned
carries an expected quantity, a cost or a difference (blind count).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import (
    Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple,
)

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import Conteo
from app.motored.models.conteo_lectura import CANTIDAD_MAXIMA, ConteoLectura
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.referencia import Referencia
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import errores, ubicaciones

RONDA_CONTEO = 1
ESTADO_RONDA_CONTEO = "EN_CONTEO"
LARGO_CODIGO = 100
CENTAVO = Decimal("0.01")

Resueltas = Dict[str, Tuple[uuid.UUID, Optional[str]]]


class Entrada(NamedTuple):
    """One reading as the device sent it."""

    id: uuid.UUID
    codigo_leido: str
    cantidad: Decimal
    leida_en: datetime
    metodo: str
    forzar_desconocido: bool = False


class Lote(NamedTuple):
    """A batch sorted out: `filas` to insert (round-agnostic columns),
    ids repeated inside the batch, unknown codes and refusals."""

    filas: List[dict]
    repetidas: List[uuid.UUID]
    desconocidos: List[Tuple[uuid.UUID, str]]
    rechazadas: List[Tuple[uuid.UUID, str]]


class Resultado(NamedTuple):
    aceptadas: List[uuid.UUID]
    duplicadas: List[uuid.UUID]
    desconocidos: List[Tuple[uuid.UUID, str]]
    rechazadas: List[Tuple[uuid.UUID, str]]
    referencias: Dict[str, str]


class Recientes(NamedTuple):
    """`lecturas` and `resumen` are rows (see `recientes`)."""

    ubicacion: Optional[UbicacionInventario]
    lecturas: list
    resumen: list


# --- pure rules -------------------------------------------------------------


def normalizar_codigo(texto: str) -> str:
    """A scanned or typed code as it is matched and stored."""
    return (texto or "").strip().upper()


def _motivo(entrada: Entrada, codigo: str) -> Optional[str]:
    """Why a reading is refused before looking its code up, if it is."""
    if not codigo or len(codigo) > LARGO_CODIGO:
        return "CODIGO_INVALIDO"
    cantidad = entrada.cantidad
    if (not cantidad.is_finite() or cantidad <= 0
            or cantidad > CANTIDAD_MAXIMA
            or cantidad != cantidad.quantize(CENTAVO)):
        return "CANTIDAD_INVALIDA"
    return None


def codigos_a_resolver(items: Iterable[Entrada]) -> Set[str]:
    """The distinct normalized codes worth a lookup."""
    codigos = set()
    for entrada in items:
        codigo = normalizar_codigo(entrada.codigo_leido)
        if _motivo(entrada, codigo) is None:
            codigos.add(codigo)
    return codigos


def _fila(entrada: Entrada, codigo: str, referencia_id) -> dict:
    return dict(
        id=entrada.id, codigo_leido=codigo, referencia_id=referencia_id,
        cantidad=entrada.cantidad, metodo=entrada.metodo,
        leida_en=entrada.leida_en)


def clasificar(items: Sequence[Entrada], resueltas: Resueltas) -> Lote:
    """Sorts a batch in its order; the first of a repeated id wins."""
    lote = Lote([], [], [], [])
    vistos = set()
    for entrada in items:
        if entrada.id in vistos:
            lote.repetidas.append(entrada.id)
            continue
        vistos.add(entrada.id)
        codigo = normalizar_codigo(entrada.codigo_leido)
        motivo = _motivo(entrada, codigo)
        hallada = resueltas.get(codigo)
        if motivo is None and hallada is None:
            if ubicaciones.es_etiqueta(codigo):
                motivo = "ES_UBICACION"
            elif not entrada.forzar_desconocido:
                lote.desconocidos.append((entrada.id, codigo))
                continue
        if motivo is not None:
            lote.rechazadas.append((entrada.id, motivo))
            continue
        referencia_id = None if hallada is None else hallada[0]
        lote.filas.append(_fila(entrada, codigo, referencia_id))
    return lote


# --- code lookup ------------------------------------------------------------


async def resolver(db: AsyncSession, codigos: Set[str]) -> Resueltas:
    """normalized code -> (referencia id, name). Exact stored code first;
    the misses by `upper(btrim(codigo))`, where two hits are no hit."""
    if not codigos:
        return {}
    resueltas: Resueltas = {}
    exactas = (await db.execute(
        select(Referencia.id, Referencia.codigo, Referencia.nombre)
        .where(Referencia.codigo.in_(sorted(codigos))))).all()
    for ident, codigo, nombre in exactas:
        resueltas[codigo] = (ident, nombre)
    faltan = codigos - set(resueltas)
    if not faltan:
        return resueltas
    normal = func.upper(func.btrim(Referencia.codigo))
    filas = (await db.execute(
        select(Referencia.id, Referencia.codigo, Referencia.nombre)
        .where(normal.in_(sorted(faltan))))).all()
    hallazgos: Dict[str, list] = {}
    for ident, codigo, nombre in filas:
        hallazgos.setdefault(normalizar_codigo(codigo), []).append(
            (ident, nombre))
    for codigo, lista in hallazgos.items():
        if len(lista) == 1:
            resueltas[codigo] = lista[0]
    return resueltas


# --- writes -----------------------------------------------------------------


async def _insertar(
        db: AsyncSession, sesion: ConteoSesion,
        filas: List[dict]) -> Set[uuid.UUID]:
    """One set-based INSERT; returns the ids that were new."""
    if not filas:
        return set()
    valores = [
        dict(fila, conteo_id=sesion.conteo_id, sesion_id=sesion.id,
             ubicacion_id=sesion.ubicacion_actual_id,
             ronda=RONDA_CONTEO, reconteo_id=None)
        for fila in filas]
    nuevas = (await db.execute(
        insert(ConteoLectura).values(valores)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(ConteoLectura.id))).scalars().all()
    return set(nuevas)


async def registrar(
        db: AsyncSession, sesion: ConteoSesion, conteo: Conteo,
        items: Sequence[Entrada]) -> Resultado:
    """Stores a batch at the session's current location (see module)."""
    if sesion.ubicacion_actual_id is None:
        raise errores.SinUbicacion()
    if conteo.estado != ESTADO_RONDA_CONTEO:
        cerradas = [(i.id, "RONDA_CERRADA") for i in items]
        return Resultado([], [], [], cerradas, {})
    resueltas = await resolver(db, codigos_a_resolver(items))
    lote = clasificar(items, resueltas)
    nuevas = await _insertar(db, sesion, lote.filas)
    ids = [f["id"] for f in lote.filas]
    return Resultado(
        aceptadas=[i for i in ids if i in nuevas],
        duplicadas=[i for i in ids if i not in nuevas] + lote.repetidas,
        desconocidos=lote.desconocidos, rechazadas=lote.rechazadas,
        referencias={c: (r[1] or "") for c, r in resueltas.items()})


async def anular(
        db: AsyncSession, sesion: ConteoSesion, conteo: Conteo,
        lectura_id: uuid.UUID, ahora: datetime) -> ConteoLectura:
    """Voids one of the session's own readings while its round is open.
    Voiding twice keeps the first time (a retry is harmless)."""
    lectura = (await db.execute(
        select(ConteoLectura).where(
            ConteoLectura.id == lectura_id,
            ConteoLectura.sesion_id == sesion.id)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if lectura is None:
        raise errores.LecturaNoEncontrada()
    if (lectura.ronda != RONDA_CONTEO
            or conteo.estado != ESTADO_RONDA_CONTEO):
        raise errores.RondaCerrada()
    if lectura.anulada_en is None:
        lectura.anulada_en = ahora
        await db.flush()
    return lectura


# --- reads ------------------------------------------------------------------


async def _ubicacion(
        db: AsyncSession,
        ubicacion_id: Optional[uuid.UUID]) -> Optional[UbicacionInventario]:
    if ubicacion_id is None:
        return None
    return (await db.execute(
        select(UbicacionInventario).where(
            UbicacionInventario.id == ubicacion_id))).scalars().first()


async def _ultimas(
        db: AsyncSession, sesion_id: uuid.UUID, limite: int) -> list:
    """(id, code, name, qty, metodo, location code, location name,
    leida_en, anulada_en), newest first; voided ones included."""
    return list((await db.execute(
        select(
            ConteoLectura.id, ConteoLectura.codigo_leido,
            Referencia.nombre, ConteoLectura.cantidad,
            ConteoLectura.metodo, UbicacionInventario.codigo,
            UbicacionInventario.nombre, ConteoLectura.leida_en,
            ConteoLectura.anulada_en)
        .join(UbicacionInventario,
              UbicacionInventario.id == ConteoLectura.ubicacion_id)
        .outerjoin(Referencia, Referencia.id == ConteoLectura.referencia_id)
        .where(ConteoLectura.sesion_id == sesion_id)
        .order_by(ConteoLectura.seq.desc())
        .limit(limite))).all())


async def _resumen(
        db: AsyncSession, sesion_id: uuid.UUID,
        ubicacion_id: uuid.UUID) -> list:
    """(code, name, counted qty, readings) of this session in one
    location, round 1, voided readings excluded."""
    return list((await db.execute(
        select(
            ConteoLectura.codigo_leido, Referencia.nombre,
            func.sum(ConteoLectura.cantidad),
            func.count(ConteoLectura.id))
        .outerjoin(Referencia, Referencia.id == ConteoLectura.referencia_id)
        .where(
            ConteoLectura.sesion_id == sesion_id,
            ConteoLectura.ubicacion_id == ubicacion_id,
            ConteoLectura.ronda == RONDA_CONTEO,
            ConteoLectura.anulada_en.is_(None))
        .group_by(
            ConteoLectura.referencia_id, ConteoLectura.codigo_leido,
            Referencia.nombre)
        .order_by(ConteoLectura.codigo_leido))).all())


async def recientes(
        db: AsyncSession, sesion: ConteoSesion, limite: int) -> Recientes:
    """The session's last readings plus what it counted in its current
    location."""
    ubicacion = await _ubicacion(db, sesion.ubicacion_actual_id)
    ultimas = await _ultimas(db, sesion.id, limite)
    resumen = []
    if ubicacion is not None:
        resumen = await _resumen(db, sesion.id, ubicacion.id)
    return Recientes(ubicacion, ultimas, resumen)
