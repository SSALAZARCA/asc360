"""
Inventory counts -- a pair's readings (odd/motored-conteos-inventario,
WU8; design §4.5, §6.2, §7, ADR-5, §9.2).

A device sends batches of up to 100 readings, each with its own client
UUID. The batch is ONE `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING
id`: a resend after a network failure stores nothing twice, and the
answer tells which ids are new and which were already stored.

Rules (design §7):
- a reading goes to its own `ubicacion_codigo` when it carries one
  (WU13b: the location in effect when it was scanned, so a pair can move
  shelves offline; `UBI-` accepted). A code the store lacks is created as
  'PAREJA' like `PUT /ubicacion`; an inactive one refuses that reading
  (UBICACION_INACTIVA), the rest of the batch goes on. All the batch's
  codes are resolved set-based (`ubicaciones.ubicar`);
- a reading without one takes the session's CURRENT location; with none
  set the whole batch is SinUbicacion (409), as for older clients;
- the session's current location follows the newest reading stored by
  the batch, so the leader panel is right after an offline move;
- codes are normalized `strip().upper()` and matched against ALL
  referencias (inactive included) by `upper(btrim(codigo))`. The exact
  stored code is tried first (unique index); only the misses pay the
  case-insensitive scan, and a code two referencias share is unknown;
- a miss is then matched by its key (`clave_codigo`: upper case, only
  `A-Z0-9`), so `9410912000S` finds `94109-12000S`. A key two master
  codes share is unknown; a `UBI-` label is never matched by key. A
  resolved reading is stored under its master code, so it lines up with
  the snapshot, the differences, the reconteos and the Excel
  (odd/tasks/motored-conteo-codigo-sin-guiones.md);
- an unknown code is NOT stored: it comes back under `desconocidos` so
  the device beeps differently and asks "¿Registrar igual?". Sent again
  with `forzar_desconocido`, it is stored with `referencia_id` NULL;
- a `UBI-…` code that is not a referencia is a location label, refused
  as ES_UBICACION (the device must set it as the location);
- quantities follow the model CHECK (> 0, <= 99999, 2 decimals);
- round 1 (no `reconteo_id`) only while the conteo is EN_CONTEO;
- round 2 (WU9, with `reconteo_id`) only while it is EN_RECONTEO, for a
  reconteo ASIGNADO to THIS session, and only for that reconteo's code
  (RECONTEO_NO_ASIGNADO / RECONTEO_OTRO_CODIGO otherwise); a master
  reconteo also takes a code that resolves to it by key. A reconteo of
  a code that is not in the master takes it without `forzar_desconocido`.

The conteo row is read `FOR SHARE` first, so a batch in flight and the
leader's "terminar ronda" (`FOR UPDATE`) never overlap: a batch either
lands before the differences are computed or sees the round closed.

Nothing here commits: the API owns the transaction. Nothing returned
carries an expected quantity, a cost or a difference (blind count).
"""
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import (
    Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple,
)

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import Conteo
from app.motored.models.conteo_lectura import CANTIDAD_MAXIMA, ConteoLectura
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.referencia import Referencia
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import errores, ubicaciones

RONDA_CONTEO = 1
RONDA_RECONTEO = 2
ESTADO_RONDA_CONTEO = "EN_CONTEO"
ESTADO_RONDA_RECONTEO = "EN_RECONTEO"
LARGO_CODIGO = 100
CENTAVO = Decimal("0.01")

# normalized code -> (referencia id, name, normalized master code)
Resueltas = Dict[str, Tuple[uuid.UUID, Optional[str], str]]
# reconteo id -> (its normalized code, whether it has a referencia)
Propios = Dict[uuid.UUID, Tuple[str, bool]]
Rechazo = Tuple[uuid.UUID, str]


class Entrada(NamedTuple):
    """One reading as the device sent it."""

    id: uuid.UUID
    codigo_leido: str
    cantidad: Decimal
    leida_en: datetime
    metodo: str
    forzar_desconocido: bool = False
    reconteo_id: Optional[uuid.UUID] = None
    ubicacion_codigo: Optional[str] = None


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


_FUERA_DE_CLAVE = re.compile(r"[^A-Z0-9]")


def clave_codigo(texto: Optional[str]) -> str:
    """The match key of a code: upper case, only `A-Z0-9` kept, so
    `94109-12000S`, `9410912000S` and `94109 12000s` share one key.
    Mirrors `claveCodigo` on the device and `_CLAVE_SQL` below."""
    return _FUERA_DE_CLAVE.sub("", (texto or "").upper())


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
        leida_en=entrada.leida_en, reconteo_id=entrada.reconteo_id)


def _ronda_dos(entrada: Entrada, estado: str,
               propios: Propios) -> Tuple[Optional[Entrada], str]:
    """A round-2 reading checked against this session's reconteos."""
    propio = propios.get(entrada.reconteo_id)
    if estado != ESTADO_RONDA_RECONTEO or propio is None:
        return None, "RECONTEO_NO_ASIGNADO"
    codigo, con_referencia = propio
    leido = normalizar_codigo(entrada.codigo_leido)
    por_clave = (con_referencia
                 and clave_codigo(leido) == clave_codigo(codigo))
    if leido != codigo and not por_clave:
        return None, "RECONTEO_OTRO_CODIGO"
    if not con_referencia:
        entrada = entrada._replace(forzar_desconocido=True)
    return entrada, ""


def por_ronda(
        items: Sequence[Entrada], estado: str,
        propios: Propios) -> Tuple[List[Entrada], List[Rechazo]]:
    """Splits a batch into readings its round accepts and refusals.
    `estado` is the conteo's, `propios` this session's ASIGNADO
    reconteos."""
    aptas, rechazadas = [], []
    for entrada in items:
        if entrada.reconteo_id is None:
            if estado == ESTADO_RONDA_CONTEO:
                aptas.append(entrada)
            else:
                rechazadas.append((entrada.id, "RONDA_CERRADA"))
            continue
        apta, motivo = _ronda_dos(entrada, estado, propios)
        if apta is None:
            rechazadas.append((entrada.id, motivo))
        else:
            aptas.append(apta)
    return aptas, rechazadas


def confirmar_ronda_dos(
        aptas: Sequence[Entrada], propios: Propios,
        resueltas: Resueltas) -> Tuple[List[Entrada], List[Rechazo]]:
    """A round-2 reading let through by key (`_ronda_dos`) stays only
    when it resolves to the reconteo's own master code; an ambiguous key
    or another master code is RECONTEO_OTRO_CODIGO."""
    buenas, malas = [], []
    for entrada in aptas:
        propio = propios.get(entrada.reconteo_id)
        leido = normalizar_codigo(entrada.codigo_leido)
        hallada = resueltas.get(leido)
        if (propio is None or leido == propio[0]
                or (hallada is not None and hallada[2] == propio[0])):
            buenas.append(entrada)
        else:
            malas.append((entrada.id, "RECONTEO_OTRO_CODIGO"))
    return buenas, malas


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
        if hallada is not None:
            codigo = hallada[2]
        referencia_id = None if hallada is None else hallada[0]
        lote.filas.append(_fila(entrada, codigo, referencia_id))
    return lote


def _codigos_de_lugar(
        aptas: Sequence[Entrada], filas: List[dict]
) -> Tuple[Dict[uuid.UUID, str], List[Rechazo]]:
    """id -> normalized location code of the rows that carry one, plus
    the rows whose code is not a valid location code."""
    pedidos: Dict[uuid.UUID, Optional[str]] = {}
    for entrada in aptas:
        pedidos.setdefault(entrada.id, entrada.ubicacion_codigo)
    codigos, rechazadas = {}, []
    for fila in filas:
        crudo = pedidos.get(fila["id"])
        if crudo is None:
            continue
        try:
            codigos[fila["id"]] = ubicaciones.codigo_ubicacion(crudo)
        except errores.UbicacionInvalida as error:
            rechazadas.append((fila["id"], error.codigo))
    return codigos, rechazadas


def asignar_lugar(
        filas: List[dict], codigos: Dict[uuid.UUID, str],
        lugares: Dict[str, ubicaciones.Lugar],
        actual: Optional[uuid.UUID],
        invalidas: List[Rechazo]) -> Tuple[List[dict], List[Rechazo]]:
    """Each row with its `ubicacion_id`: its own code's location, else
    the session's `actual`. Rows refused for their location are left
    out and reported."""
    malas = dict(invalidas)
    ubicadas, rechazadas = [], []
    for fila in filas:
        ident = fila["id"]
        if ident in malas:
            rechazadas.append((ident, malas[ident]))
            continue
        lugar_id, motivo = actual, None
        if ident in codigos:
            lugar = lugares.get(codigos[ident])
            lugar_id = None if lugar is None else lugar.ubicacion_id
            motivo = (lugar.motivo if lugar is not None
                      else errores.UbicacionInactiva.codigo)
        if lugar_id is None:
            rechazadas.append((ident, motivo))
            continue
        ubicadas.append(dict(fila, ubicacion_id=lugar_id))
    return ubicadas, rechazadas


def mas_reciente(
        filas: List[dict], nuevas: Set[uuid.UUID]) -> Optional[uuid.UUID]:
    """The location of the newest row actually stored now, if any."""
    guardadas = [f for f in filas if f["id"] in nuevas]
    if not guardadas:
        return None
    return max(guardadas, key=lambda f: f["leida_en"])["ubicacion_id"]


# --- code lookup ------------------------------------------------------------


# The key of a stored code, written exactly like the functional index
# `ix_referencia_codigo_clave` (alembic_motored) so the planner uses it:
# literal constants, never bound parameters.
_CLAVE_SQL = func.regexp_replace(
    func.upper(Referencia.codigo), literal_column("'[^A-Z0-9]'"),
    literal_column("''"), literal_column("'g'"))


def elegir_referencias(
        codigos: Iterable[str],
        filas: Iterable[Tuple[uuid.UUID, str, Optional[str]]]
) -> Resueltas:
    """normalized code -> its one referencia among `filas` (id, stored
    code, name): by `upper(btrim)` first, else by key (never for a `UBI-`
    label). Two or more hits are no hit."""
    por_normal: Dict[str, list] = {}
    por_clave: Dict[str, list] = {}
    for ident, codigo, nombre in filas:
        maestro = normalizar_codigo(codigo)
        hallada = (ident, nombre, maestro)
        por_normal.setdefault(maestro, []).append(hallada)
        por_clave.setdefault(clave_codigo(maestro), []).append(hallada)
    resueltas: Resueltas = {}
    for codigo in codigos:
        lista = por_normal.get(codigo)
        if lista is None and not ubicaciones.es_etiqueta(codigo):
            lista = por_clave.get(clave_codigo(codigo))
        if lista is not None and len(lista) == 1:
            resueltas[codigo] = lista[0]
    return resueltas


def _condicion_faltantes(faltan: Set[str]):
    """The WHERE of the misses. Every row equal under `upper(btrim)`
    shares the key, so the key alone finds them through the functional
    index; only `UBI-` labels and key-less codes (never matched by key)
    still need the `upper(btrim)` scan."""
    claves = {clave_codigo(c) for c in faltan
              if not ubicaciones.es_etiqueta(c)} - {""}
    sin_clave = sorted(c for c in faltan
                       if ubicaciones.es_etiqueta(c) or not clave_codigo(c))
    condiciones = []
    if claves:
        condiciones.append(_CLAVE_SQL.in_(sorted(claves)))
    if sin_clave:
        condiciones.append(
            func.upper(func.btrim(Referencia.codigo)).in_(sin_clave))
    return or_(*condiciones)


async def resolver(db: AsyncSession, codigos: Set[str]) -> Resueltas:
    """normalized code -> (referencia id, name, master code). Exact
    stored code first (unique index); the misses in one query
    (`_condicion_faltantes`) sorted out by `elegir_referencias`."""
    if not codigos:
        return {}
    resueltas: Resueltas = {}
    exactas = (await db.execute(
        select(Referencia.id, Referencia.codigo, Referencia.nombre)
        .where(Referencia.codigo.in_(sorted(codigos))))).all()
    for ident, codigo, nombre in exactas:
        resueltas[codigo] = (ident, nombre, codigo)
    faltan = codigos - set(resueltas)
    if not faltan:
        return resueltas
    filas = (await db.execute(
        select(Referencia.id, Referencia.codigo, Referencia.nombre)
        .where(_condicion_faltantes(faltan)))).all()
    resueltas.update(elegir_referencias(faltan, filas))
    return resueltas


# --- writes -----------------------------------------------------------------


async def _insertar(
        db: AsyncSession, sesion: ConteoSesion,
        filas: List[dict]) -> Set[uuid.UUID]:
    """One set-based INSERT of located rows; returns the ids that were
    new."""
    if not filas:
        return set()
    valores = [
        dict(fila, conteo_id=sesion.conteo_id, sesion_id=sesion.id,
             ronda=(RONDA_CONTEO if fila["reconteo_id"] is None
                    else RONDA_RECONTEO))
        for fila in filas]
    nuevas = (await db.execute(
        insert(ConteoLectura).values(valores)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(ConteoLectura.id))).scalars().all()
    return set(nuevas)


async def _estado_vigente(db: AsyncSession, conteo_id: uuid.UUID) -> str:
    """The conteo's estado, read FOR SHARE (see module)."""
    return (await db.execute(
        select(Conteo.estado).where(Conteo.id == conteo_id)
        .with_for_update(read=True))).scalars().first()


async def _propios(
        db: AsyncSession, sesion: ConteoSesion,
        nombrados: Iterable[Optional[uuid.UUID]]) -> Propios:
    """This session's ASIGNADO reconteos among `nombrados`."""
    ids = sorted({i for i in nombrados if i is not None}, key=str)
    if not ids:
        return {}
    filas = (await db.execute(
        select(ConteoReconteo.id, ConteoReconteo.codigo,
               ConteoReconteo.referencia_id)
        .where(ConteoReconteo.id.in_(ids),
               ConteoReconteo.conteo_id == sesion.conteo_id,
               ConteoReconteo.sesion_id == sesion.id,
               ConteoReconteo.estado == "ASIGNADO")
        .with_for_update(read=True))).all()
    return {f[0]: (normalizar_codigo(f[1]), f[2] is not None)
            for f in filas}


async def _ubicar(
        db: AsyncSession, sesion: ConteoSesion, conteo: Conteo,
        aptas: Sequence[Entrada],
        filas: List[dict]) -> Tuple[List[dict], List[Rechazo]]:
    """The rows with their location (see module), resolving every
    distinct code of the batch at once."""
    codigos, invalidas = _codigos_de_lugar(aptas, filas)
    lugares = await ubicaciones.ubicar(
        db, conteo.sucursal_id, set(codigos.values()))
    return asignar_lugar(
        filas, codigos, lugares, sesion.ubicacion_actual_id, invalidas)


async def registrar(
        db: AsyncSession, sesion: ConteoSesion, conteo: Conteo,
        items: Sequence[Entrada]) -> Resultado:
    """Stores a batch, each reading at its own location or the
    session's current one (see module)."""
    if (sesion.ubicacion_actual_id is None
            and any(i.ubicacion_codigo is None for i in items)):
        raise errores.SinUbicacion()
    estado = await _estado_vigente(db, conteo.id)
    propios = await _propios(db, sesion, [i.reconteo_id for i in items])
    aptas, fuera = por_ronda(items, estado, propios)
    if not aptas:
        return Resultado([], [], [], fuera, {})
    resueltas = await resolver(db, codigos_a_resolver(aptas))
    aptas, otro_codigo = confirmar_ronda_dos(aptas, propios, resueltas)
    fuera += otro_codigo
    lote = clasificar(aptas, resueltas)
    filas, sin_lugar = await _ubicar(db, sesion, conteo, aptas, lote.filas)
    nuevas = await _insertar(db, sesion, filas)
    ultima = mas_reciente(filas, nuevas)
    if ultima is not None:
        sesion.ubicacion_actual_id = ultima
    ids = [f["id"] for f in filas]
    return Resultado(
        aceptadas=[i for i in ids if i in nuevas],
        duplicadas=[i for i in ids if i not in nuevas] + lote.repetidas,
        desconocidos=lote.desconocidos,
        rechazadas=fuera + lote.rechazadas + sin_lugar,
        referencias={c: (r[1] or "") for c, r in resueltas.items()})


async def _anulable(
        db: AsyncSession, sesion: ConteoSesion, conteo: Conteo,
        lectura: ConteoLectura) -> bool:
    """Round 1 while counting; round 2 while its reconteo is still
    ASIGNADO to this session."""
    if lectura.ronda == RONDA_CONTEO:
        return conteo.estado == ESTADO_RONDA_CONTEO
    if conteo.estado != ESTADO_RONDA_RECONTEO:
        return False
    return bool(await _propios(db, sesion, [lectura.reconteo_id]))


async def anular(
        db: AsyncSession, sesion: ConteoSesion, conteo: Conteo,
        lectura_id: uuid.UUID, ahora: datetime) -> ConteoLectura:
    """Voids one of the session's own readings while its round is open
    (`_anulable`). Voiding twice keeps the first time."""
    lectura = (await db.execute(
        select(ConteoLectura).where(
            ConteoLectura.id == lectura_id,
            ConteoLectura.sesion_id == sesion.id)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if lectura is None:
        raise errores.LecturaNoEncontrada()
    if not await _anulable(db, sesion, conteo, lectura):
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
