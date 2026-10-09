"""
Inventory counts -- bin locations of a store (odd/motored-conteos-
inventario, WU8; design §4.3, §6.1, §6.2, §7.2-§7.3).

Locations belong to a STORE (owner override: no bodega) and persist
across counts, so printed labels are reused. A label's barcode value is
`UBI-` + `codigo`; a scan with that prefix is a location change, never a
reading. Codes are stored normalized: trimmed, upper case, inner spaces
collapsed (the model CHECK guarantees the first two).

A leader prepares locations ahead (`origen` 'LIDER'); a pair that sets a
code the store does not have creates it on the spot (`origen` 'PAREJA'),
which the leader sees in its list. Creating a location whose label would
equal a referencia code is refused, so the scanner never mistakes one for
the other. A reading may also carry its own location code (WU13b, a pair
that moved shelves offline): `ubicar` resolves a batch's codes in one
SELECT and creates the missing ones the same way, set-based. Nothing here
commits: the API owns the transaction.
"""
import uuid
from typing import Dict, List, NamedTuple, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.referencia import Referencia
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import errores

PREFIJO_ETIQUETA = "UBI-"
LARGO_CODIGO = 30
LARGO_NOMBRE = 60


class Fijada(NamedTuple):
    """The session's new current location; `creada` when a pair made
    it just now."""

    ubicacion: UbicacionInventario
    creada: bool


class Lugar(NamedTuple):
    """Where a reading with this code goes: `ubicacion_id`, or why not
    (`motivo`, a per-reading refusal)."""

    ubicacion_id: Optional[uuid.UUID]
    motivo: Optional[str] = None


# --- pure rules -------------------------------------------------------------


def _compactar(texto: str) -> str:
    return " ".join((texto or "").split())


def es_etiqueta(texto: str) -> bool:
    """A scanned value with the location label prefix."""
    return _compactar(texto).upper().startswith(PREFIJO_ETIQUETA)


def codigo_ubicacion(texto: str) -> str:
    """The stored form of a typed or scanned location code: without the
    `UBI-` prefix, trimmed, upper case, inner spaces collapsed.
    UbicacionInvalida when it ends up empty or longer than 30."""
    codigo = _compactar(texto).upper()
    if codigo.startswith(PREFIJO_ETIQUETA):
        codigo = codigo[len(PREFIJO_ETIQUETA):].strip()
    if not codigo or len(codigo) > LARGO_CODIGO:
        raise errores.UbicacionInvalida()
    return codigo


def nombre_ubicacion(texto: Optional[str], codigo: str) -> str:
    """A trimmed name; the code itself when none is given."""
    nombre = _compactar(texto or "") or codigo
    return nombre[:LARGO_NOMBRE]


# --- reads ------------------------------------------------------------------


async def listar(
        db: AsyncSession, sucursal_id: uuid.UUID,
        solo_activas: bool) -> List[UbicacionInventario]:
    """The store's locations by code (the active ones for a pair)."""
    consulta = (
        select(UbicacionInventario)
        .where(UbicacionInventario.sucursal_id == sucursal_id)
        .order_by(UbicacionInventario.codigo))
    if solo_activas:
        consulta = consulta.where(UbicacionInventario.activa.is_(True))
    return list((await db.execute(consulta)).scalars().all())


async def _por_codigo(
        db: AsyncSession, sucursal_id: uuid.UUID,
        codigo: str) -> Optional[UbicacionInventario]:
    return (await db.execute(
        select(UbicacionInventario).where(
            UbicacionInventario.sucursal_id == sucursal_id,
            UbicacionInventario.codigo == codigo))).scalars().first()


async def _por_codigos(
        db: AsyncSession, sucursal_id: uuid.UUID,
        codigos: Set[str]) -> Dict[str, Lugar]:
    """code -> Lugar of the store's locations among `codigos`; an
    inactive one is refused as UBICACION_INACTIVA."""
    filas = (await db.execute(
        select(UbicacionInventario.id, UbicacionInventario.codigo,
               UbicacionInventario.activa)
        .where(UbicacionInventario.sucursal_id == sucursal_id,
               UbicacionInventario.codigo.in_(sorted(codigos))))).all()
    return {
        codigo: (Lugar(ident) if activa
                 else Lugar(None, errores.UbicacionInactiva.codigo))
        for ident, codigo, activa in filas}


async def _chocan_con_referencias(
        db: AsyncSession, codigos: Set[str]) -> Set[str]:
    """The codes whose label equals a referencia code."""
    etiquetas = {PREFIJO_ETIQUETA + c: c for c in codigos}
    halladas = (await db.execute(
        select(func.upper(func.btrim(Referencia.codigo)))
        .where(func.upper(func.btrim(Referencia.codigo))
               .in_(sorted(etiquetas))))).scalars().all()
    return {etiquetas[e] for e in halladas if e in etiquetas}


async def _choca_con_referencia(db: AsyncSession, codigo: str) -> bool:
    etiqueta = PREFIJO_ETIQUETA + codigo
    hallada = (await db.execute(
        select(Referencia.id).where(
            func.upper(func.btrim(Referencia.codigo)) == etiqueta)
        .limit(1))).scalars().first()
    return hallada is not None


# --- writes -----------------------------------------------------------------


async def _insertar(
        db: AsyncSession, sucursal_id: uuid.UUID, codigo: str,
        nombre: str, origen: str,
        usuario_id: Optional[uuid.UUID]) -> Optional[UbicacionInventario]:
    """INSERT ... ON CONFLICT DO NOTHING: None when the code appeared in
    between (another pair created it at the same moment)."""
    nueva = uuid.uuid4()
    creada = (await db.execute(
        insert(UbicacionInventario)
        .values(id=nueva, sucursal_id=sucursal_id, codigo=codigo,
                nombre=nombre, activa=True, origen=origen,
                created_by=usuario_id)
        .on_conflict_do_nothing(
            index_elements=["sucursal_id", "codigo"])
        .returning(UbicacionInventario.id))).scalars().first()
    if creada is None:
        return None
    return UbicacionInventario(
        id=creada, sucursal_id=sucursal_id, codigo=codigo, nombre=nombre,
        activa=True, origen=origen, created_by=usuario_id)


async def _insertar_de_pareja(
        db: AsyncSession, sucursal_id: uuid.UUID,
        codigos: Set[str]) -> Dict[str, Lugar]:
    """One INSERT ... ON CONFLICT DO NOTHING for `codigos` ('PAREJA',
    named after the code), in code order so two batches lock alike.
    Returns the ones THIS statement created."""
    valores = [
        dict(id=uuid.uuid4(), sucursal_id=sucursal_id, codigo=codigo,
             nombre=nombre_ubicacion(None, codigo), activa=True,
             origen="PAREJA", created_by=None)
        for codigo in sorted(codigos)]
    filas = (await db.execute(
        insert(UbicacionInventario).values(valores)
        .on_conflict_do_nothing(
            index_elements=["sucursal_id", "codigo"])
        .returning(UbicacionInventario.id,
                   UbicacionInventario.codigo))).all()
    return {codigo: Lugar(ident) for ident, codigo in filas}


async def ubicar(
        db: AsyncSession, sucursal_id: uuid.UUID,
        codigos: Set[str]) -> Dict[str, Lugar]:
    """normalized code -> Lugar for a batch of readings. Like `fijar`, a
    code the store lacks is created as 'PAREJA' (unless its label is a
    referencia code); a code another batch created at the same moment is
    read back. One SELECT when every code exists."""
    if not codigos:
        return {}
    lugares = await _por_codigos(db, sucursal_id, codigos)
    faltan = codigos - set(lugares)
    if not faltan:
        return lugares
    chocan = await _chocan_con_referencias(db, faltan)
    for codigo in chocan:
        lugares[codigo] = Lugar(
            None, errores.UbicacionChocaReferencia.codigo)
    nuevas = faltan - chocan
    if nuevas:
        lugares.update(await _insertar_de_pareja(db, sucursal_id, nuevas))
    entre_tanto = nuevas - set(lugares)
    if entre_tanto:
        lugares.update(await _por_codigos(db, sucursal_id, entre_tanto))
    return lugares


async def crear(
        db: AsyncSession, sucursal_id: uuid.UUID, texto: str,
        nombre: Optional[str],
        usuario_id: uuid.UUID) -> UbicacionInventario:
    """A location prepared by the leader ('LIDER')."""
    codigo = codigo_ubicacion(texto)
    if await _por_codigo(db, sucursal_id, codigo) is not None:
        raise errores.UbicacionDuplicada(codigo=codigo)
    if await _choca_con_referencia(db, codigo):
        raise errores.UbicacionChocaReferencia(codigo=codigo)
    ubicacion = await _insertar(
        db, sucursal_id, codigo, nombre_ubicacion(nombre, codigo),
        "LIDER", usuario_id)
    if ubicacion is None:
        raise errores.UbicacionDuplicada(codigo=codigo)
    return ubicacion


async def fijar(
        db: AsyncSession, sesion: ConteoSesion, sucursal_id: uuid.UUID,
        texto: str, nombre: Optional[str]) -> Fijada:
    """Sets the session's current location by code (typed or scanned
    `UBI-…`); creates it as 'PAREJA' when the store does not have it."""
    codigo = codigo_ubicacion(texto)
    ubicacion = await _por_codigo(db, sucursal_id, codigo)
    creada = False
    if ubicacion is None:
        if await _choca_con_referencia(db, codigo):
            raise errores.UbicacionChocaReferencia(codigo=codigo)
        ubicacion = await _insertar(
            db, sucursal_id, codigo, nombre_ubicacion(nombre, codigo),
            "PAREJA", None)
        creada = ubicacion is not None
        if ubicacion is None:
            ubicacion = await _por_codigo(db, sucursal_id, codigo)
    if ubicacion is None or not ubicacion.activa:
        raise errores.UbicacionInactiva(codigo=codigo)
    sesion.ubicacion_actual_id = ubicacion.id
    return Fijada(ubicacion, creada)


async def editar(
        db: AsyncSession, sucursal_id: uuid.UUID, ubicacion_id: uuid.UUID,
        nombre: Optional[str],
        activa: Optional[bool]) -> UbicacionInventario:
    """Renames and/or (de)activates a location of this store. The code
    never changes: labels with it may already be printed."""
    ubicacion = (await db.execute(
        select(UbicacionInventario).where(
            UbicacionInventario.id == ubicacion_id,
            UbicacionInventario.sucursal_id == sucursal_id)
        .with_for_update())).scalars().first()
    if ubicacion is None:
        raise errores.UbicacionNoEncontrada()
    if nombre is not None:
        ubicacion.nombre = nombre_ubicacion(nombre, ubicacion.codigo)
    if activa is not None:
        ubicacion.activa = activa
    await db.flush()
    return ubicacion
