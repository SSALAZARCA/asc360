"""
Inventory counts -- the reconteo round (odd/motored-conteos-inventario,
WU9; design §5.1, §5.2, §6.1, §6.2, §7, ADR-4).

Leader side:

- `terminar_ronda`: EN_CONTEO -> EN_RECONTEO under the conteo row lock.
  The differences are computed once (`diferencias`) and every one that
  reaches the frozen reconteo amount, or has no cost, becomes a
  PENDIENTE reconteo with origen 'UMBRAL' and its round-1 difference and
  value frozen. Round-1 readings are refused from then on;
- `crear_manual`: the leader sends any master referencia (or a code
  read in round 1 that is not in the master) to reconteo, under the
  amount or not (origen 'LIDER'); one live reconteo per code;
- `asignar`: "a different pair" means DISJOINT cédula sets (ADR-4): the
  target session shares no cédula with any session that has a
  non-voided round-1 reading of that code, so the same people on a new
  device are still the same pair. The leader may authorize the same
  pair only when no eligible session is connected, with a reason, which
  is stored;
- `auto_asignar`: spreads the PENDIENTE reconteos over the eligible
  connected sessions, the most constrained first, each to the least
  loaded eligible session. Those with no eligible session stay
  PENDIENTE and are reported;
- `cancelar`: PENDIENTE or ASIGNADO -> CANCELADO.

Pair side: `tareas` (code, name and the round-1 locations; never a
quantity) and `terminar` (ASIGNADO -> TERMINADO; zero readings means it
was found 0).

Locks, always in this order: connected sessions FOR SHARE, then the
reconteo rows FOR UPDATE (a disconnect updates the session, then its
reconteos), so an assignment never lands on a session that just left.
Nothing here commits: the API owns the transaction.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Mapping, NamedTuple, Optional, Sequence, Set

from sqlalchemy import and_, bindparam, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import Conteo
from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.referencia import Referencia
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import diferencias, errores, lecturas

EN_CONTEO = "EN_CONTEO"
EN_RECONTEO = "EN_RECONTEO"
ASIGNABLES = ("PENDIENTE", "ASIGNADO")
VISIBLES_PAREJA = ("ASIGNADO", "TERMINADO")

_SQL_ELEGIBLES = text("""
WITH rec AS (
    SELECT id, referencia_id, codigo FROM conteo_reconteo
    WHERE conteo_id = :conteo_id AND id IN :ids
),
previas AS (
    SELECT DISTINCT rec.id AS reconteo_id, i.cedula
    FROM rec
    JOIN conteo_lectura lec1
      ON lec1.conteo_id = :conteo_id AND lec1.ronda = 1
     AND lec1.anulada_en IS NULL
     AND (lec1.referencia_id = rec.referencia_id
          OR (rec.referencia_id IS NULL
              AND lec1.referencia_id IS NULL
              AND lec1.codigo_leido = rec.codigo))
    JOIN conteo_integrante i ON i.sesion_id = lec1.sesion_id
)
SELECT rec.id, s.id
FROM rec
CROSS JOIN conteo_sesion s
WHERE s.conteo_id = :conteo_id AND s.estado = 'CONECTADA'
  AND NOT EXISTS (
      SELECT 1 FROM conteo_integrante i
      JOIN previas p ON p.cedula = i.cedula AND p.reconteo_id = rec.id
      WHERE i.sesion_id = s.id)
ORDER BY s.conectada_en, s.id
""").bindparams(bindparam("ids", expanding=True))


class FinRonda(NamedTuple):
    conteo: Conteo
    diferencias: int
    reconteos: int


class Reparto(NamedTuple):
    """reconteo id -> session id, and the reconteos left without one."""

    asignaciones: Dict[uuid.UUID, uuid.UUID]
    sin_pareja: List[uuid.UUID]


class ResultadoReparto(NamedTuple):
    asignados: List[ConteoReconteo]
    sin_pareja: List[ConteoReconteo]


class Tarea(NamedTuple):
    """A pair's reconteo task: nothing about quantities."""

    id: uuid.UUID
    codigo: str
    descripcion: Optional[str]
    ubicaciones: List[str]
    estado: str


# --- pure rules -------------------------------------------------------------


def decidir_asignacion(
        *, elegible: bool, hay_elegibles: bool, autorizar: bool,
        motivo: Optional[str]) -> bool:
    """True when the assignment is the leader's same-pair override.
    `hay_elegibles`: some connected session is eligible."""
    if elegible:
        return False
    if not autorizar:
        raise errores.MismaPareja()
    if hay_elegibles:
        raise errores.HayParejaElegible()
    if not (motivo or "").strip():
        raise errores.MotivoRequerido(
            "Escriba por qué autoriza a la misma pareja.")
    return True


def repartir(
        pendientes: Sequence[uuid.UUID],
        elegibles: Mapping[uuid.UUID, Sequence[uuid.UUID]],
        carga: Mapping[uuid.UUID, int]) -> Reparto:
    """Balanced spread: the reconteo with the fewest eligible sessions
    goes first, to its least loaded session (ties: the session listed
    first). `carga` = reconteos each session already holds."""
    carga = dict(carga)
    orden = sorted(
        range(len(pendientes)),
        key=lambda i: (len(elegibles.get(pendientes[i], ())), i))
    asignaciones, sin_pareja = {}, set()
    for indice in orden:
        reconteo_id = pendientes[indice]
        opciones = list(elegibles.get(reconteo_id, ()))
        if not opciones:
            sin_pareja.add(reconteo_id)
            continue
        elegida = min(
            opciones, key=lambda s: (carga.get(s, 0), opciones.index(s)))
        asignaciones[reconteo_id] = elegida
        carga[elegida] = carga.get(elegida, 0) + 1
    return Reparto(
        asignaciones, [r for r in pendientes if r in sin_pareja])


def _exigir(conteo: Conteo, estado: str, mensaje: str) -> None:
    if conteo.estado != estado:
        raise errores.EstadoInvalido(mensaje, estado=conteo.estado)


def _exigir_reconteo(conteo: Conteo) -> None:
    _exigir(conteo, EN_RECONTEO,
            "Los reconteos se manejan después de terminar la primera "
            "ronda y antes de cerrar.")


def _nuevo(
        conteo_id: uuid.UUID, fila: diferencias.Diferencia,
        origen: str) -> ConteoReconteo:
    return ConteoReconteo(
        id=uuid.uuid4(), conteo_id=conteo_id,
        referencia_id=fila.referencia_id, codigo=fila.codigo,
        estado="PENDIENTE", origen=origen,
        diferencia_ronda1=fila.diferencia, valor_ronda1=fila.valor,
        misma_pareja_autorizada=False)


def _poner(reconteo: ConteoReconteo, sesion_id: uuid.UUID,
           usuario_id: uuid.UUID, ahora: datetime,
           motivo: Optional[str]) -> None:
    """Assigns; a `motivo` marks the leader's same-pair override."""
    reconteo.estado = "ASIGNADO"
    reconteo.sesion_id = sesion_id
    reconteo.asignado_por = usuario_id
    reconteo.asignado_en = ahora
    reconteo.misma_pareja_autorizada = motivo is not None
    reconteo.motivo_autorizacion = (
        None if motivo is None else motivo.strip())


# --- locks and lookups ------------------------------------------------------


async def _conteo_bloqueado(
        db: AsyncSession, conteo_id: uuid.UUID) -> Conteo:
    conteo = (await db.execute(
        select(Conteo).where(Conteo.id == conteo_id).with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if conteo is None:
        raise errores.ConteoNoEncontrado()
    return conteo


async def _conectadas(
        db: AsyncSession, conteo_id: uuid.UUID) -> Set[uuid.UUID]:
    """The connected sessions, locked FOR SHARE (see module)."""
    return set((await db.execute(
        select(ConteoSesion.id)
        .where(ConteoSesion.conteo_id == conteo_id,
               ConteoSesion.estado == "CONECTADA")
        .order_by(ConteoSesion.id)
        .with_for_update(read=True))).scalars().all())


async def _reconteo_bloqueado(
        db: AsyncSession, conteo_id: uuid.UUID,
        reconteo_id: uuid.UUID) -> ConteoReconteo:
    reconteo = (await db.execute(
        select(ConteoReconteo)
        .where(ConteoReconteo.id == reconteo_id,
               ConteoReconteo.conteo_id == conteo_id)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if reconteo is None:
        raise errores.ReconteoNoEncontrado(
            "El reconteo no existe en este conteo.")
    return reconteo


async def elegibles(
        db: AsyncSession, conteo_id: uuid.UUID,
        reconteo_ids: Sequence[uuid.UUID],
) -> Dict[uuid.UUID, List[uuid.UUID]]:
    """reconteo id -> the CONECTADA sessions whose cédulas are disjoint
    from every round-1 counter of that code (ADR-4), in join order."""
    salida = {r: [] for r in reconteo_ids}
    if not reconteo_ids:
        return salida
    filas = (await db.execute(_SQL_ELEGIBLES, {
        "conteo_id": conteo_id, "ids": list(reconteo_ids)})).all()
    for reconteo_id, sesion_id in filas:
        salida[reconteo_id].append(sesion_id)
    return salida


async def _carga(
        db: AsyncSession, conteo_id: uuid.UUID) -> Dict[uuid.UUID, int]:
    filas = (await db.execute(
        select(ConteoReconteo.sesion_id, func.count(ConteoReconteo.id))
        .where(ConteoReconteo.conteo_id == conteo_id,
               ConteoReconteo.estado == "ASIGNADO")
        .group_by(ConteoReconteo.sesion_id))).all()
    return {f[0]: int(f[1]) for f in filas}


async def _sesion_destino(
        db: AsyncSession, conteo_id: uuid.UUID, sesion_id: uuid.UUID,
        conectadas: Set[uuid.UUID]) -> None:
    if sesion_id in conectadas:
        return
    sesion = await db.get(ConteoSesion, sesion_id)
    if sesion is None or sesion.conteo_id != conteo_id:
        raise errores.SesionNoEncontrada()
    raise errores.SesionNoDisponible()


# --- leader side ------------------------------------------------------------


async def terminar_ronda(
        db: AsyncSession, conteo_id: uuid.UUID,
        ahora: datetime) -> FinRonda:
    """EN_CONTEO -> EN_RECONTEO plus the threshold reconteos."""
    conteo = await _conteo_bloqueado(db, conteo_id)
    _exigir(conteo, EN_CONTEO,
            "La primera ronda solo se termina con el conteo en curso.")
    lista = await diferencias.listar(db, conteo)
    umbral = conteo.umbral_reconteo_pesos
    nuevos = [
        _nuevo(conteo.id, fila, "UMBRAL") for fila in lista
        if diferencias.requiere_reconteo(fila.diferencia, fila.valor, umbral)]
    conteo.estado = EN_RECONTEO
    conteo.ronda_terminada_en = ahora
    for reconteo in nuevos:
        db.add(reconteo)
    await db.flush()
    return FinRonda(conteo, len(lista), len(nuevos))


def _coincide(fila: diferencias.FilaCruda, referencia_id, codigo) -> bool:
    if referencia_id is not None:
        return fila.referencia_id == referencia_id
    return fila.referencia_id is None and fila.codigo == codigo


async def _cruda_de(
        db: AsyncSession, conteo_id: uuid.UUID,
        codigo: str) -> diferencias.FilaCruda:
    """The aggregate row of one code; a master referencia nobody read
    and the system does not hold is an all-zero row."""
    hallada = (await lecturas.resolver(db, {codigo})).get(codigo)
    referencia_id = None if hallada is None else hallada[0]
    crudas = await diferencias.filas(db, conteo_id, solo_diferencias=False)
    for fila in crudas:
        if _coincide(fila, referencia_id, codigo):
            return fila
    if referencia_id is None:
        raise errores.CodigoDesconocido()
    referencia = await db.get(Referencia, referencia_id)
    return diferencias.FilaCruda(
        referencia_id, referencia.codigo, referencia.nombre,
        *([None] * 11))


async def crear_manual(
        db: AsyncSession, conteo_id: uuid.UUID,
        codigo: str) -> ConteoReconteo:
    """A leader's reconteo for any code, under the amount or not."""
    conteo = await _conteo_bloqueado(db, conteo_id)
    _exigir_reconteo(conteo)
    normal = lecturas.normalizar_codigo(codigo)
    if not normal:
        raise errores.CodigoDesconocido()
    cruda = await _cruda_de(db, conteo.id, normal)
    if cruda.reconteo_id is not None:
        raise errores.ReconteoDuplicado()
    fila = diferencias.calcular(cruda, conteo.umbral_critico_pesos)
    reconteo = _nuevo(conteo.id, fila, "LIDER")
    db.add(reconteo)
    try:
        await db.flush()
    except IntegrityError as error:
        raise errores.ReconteoDuplicado() from error
    return reconteo


async def asignar(
        db: AsyncSession, conteo: Conteo, reconteo_id: uuid.UUID,
        sesion_id: uuid.UUID, usuario_id: uuid.UUID, *, autorizar: bool,
        motivo: Optional[str], ahora: datetime) -> ConteoReconteo:
    """Assigns to a DIFFERENT pair (ADR-4), or to the same one with the
    leader's reason when no eligible session is connected."""
    _exigir_reconteo(conteo)
    conectadas = await _conectadas(db, conteo.id)
    reconteo = await _reconteo_bloqueado(db, conteo.id, reconteo_id)
    if reconteo.estado not in ASIGNABLES:
        raise errores.EstadoInvalido(
            "Solo se asigna un reconteo pendiente o asignado.",
            estado=reconteo.estado)
    await _sesion_destino(db, conteo.id, sesion_id, conectadas)
    opciones = (await elegibles(db, conteo.id, [reconteo.id]))[reconteo.id]
    misma = decidir_asignacion(
        elegible=sesion_id in opciones, hay_elegibles=bool(opciones),
        autorizar=autorizar, motivo=motivo)
    _poner(reconteo, sesion_id, usuario_id, ahora,
           motivo if misma else None)
    await db.flush()
    return reconteo


async def auto_asignar(
        db: AsyncSession, conteo: Conteo, usuario_id: uuid.UUID,
        ahora: datetime) -> ResultadoReparto:
    """Spreads every PENDIENTE reconteo (see `repartir`)."""
    _exigir_reconteo(conteo)
    conectadas = await _conectadas(db, conteo.id)
    pendientes = list((await db.execute(
        select(ConteoReconteo)
        .where(ConteoReconteo.conteo_id == conteo.id,
               ConteoReconteo.estado == "PENDIENTE")
        .order_by(ConteoReconteo.codigo)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().all())
    ids = [r.id for r in pendientes]
    opciones = await elegibles(db, conteo.id, ids) if conectadas else {}
    reparto = repartir(ids, opciones, await _carga(db, conteo.id))
    for reconteo in pendientes:
        sesion_id = reparto.asignaciones.get(reconteo.id)
        if sesion_id is not None:
            _poner(reconteo, sesion_id, usuario_id, ahora, None)
    await db.flush()
    return ResultadoReparto(
        [r for r in pendientes if r.id in reparto.asignaciones],
        [r for r in pendientes if r.id not in reparto.asignaciones])


async def cancelar(
        db: AsyncSession, conteo: Conteo, reconteo_id: uuid.UUID,
        ahora: datetime) -> ConteoReconteo:
    _exigir_reconteo(conteo)
    reconteo = await _reconteo_bloqueado(db, conteo.id, reconteo_id)
    if reconteo.estado not in ASIGNABLES:
        raise errores.EstadoInvalido(
            "Solo se cancela un reconteo pendiente o asignado.",
            estado=reconteo.estado)
    reconteo.estado = "CANCELADO"
    reconteo.cancelado_en = ahora
    await db.flush()
    return reconteo


# --- pair side --------------------------------------------------------------


def _lecturas_ronda1():
    """Round-1 readings of the reconteo's code (by referencia, or by the
    code read when it is not in the master)."""
    return and_(
        ConteoLectura.conteo_id == ConteoReconteo.conteo_id,
        ConteoLectura.ronda == 1, ConteoLectura.anulada_en.is_(None),
        or_(ConteoLectura.referencia_id == ConteoReconteo.referencia_id,
            and_(ConteoReconteo.referencia_id.is_(None),
                 ConteoLectura.referencia_id.is_(None),
                 ConteoLectura.codigo_leido == ConteoReconteo.codigo)))


async def tareas(db: AsyncSession, sesion: ConteoSesion) -> List[Tarea]:
    """The session's ASIGNADO (first) and TERMINADO reconteos with the
    locations where round 1 found the code. Blind: no quantities."""
    nombres = func.array_remove(
        func.array_agg(UbicacionInventario.nombre.distinct()), None)
    filas = (await db.execute(
        select(ConteoReconteo.id, ConteoReconteo.codigo, Referencia.nombre,
               ConteoReconteo.estado, nombres)
        .outerjoin(Referencia,
                   Referencia.id == ConteoReconteo.referencia_id)
        .outerjoin(ConteoLectura, _lecturas_ronda1())
        .outerjoin(UbicacionInventario,
                   UbicacionInventario.id == ConteoLectura.ubicacion_id)
        .where(ConteoReconteo.sesion_id == sesion.id,
               ConteoReconteo.conteo_id == sesion.conteo_id,
               ConteoReconteo.estado.in_(VISIBLES_PAREJA))
        .group_by(ConteoReconteo.id, Referencia.nombre)
        .order_by(ConteoReconteo.estado, ConteoReconteo.codigo))).all()
    return [Tarea(f[0], f[1], f[2], sorted(f[4] or []), f[3])
            for f in filas]


async def terminar(
        db: AsyncSession, sesion: ConteoSesion, reconteo_id: uuid.UUID,
        ahora: datetime) -> ConteoReconteo:
    """The assignee marks its task done; finishing twice is harmless."""
    reconteo = (await db.execute(
        select(ConteoReconteo)
        .where(ConteoReconteo.id == reconteo_id,
               ConteoReconteo.conteo_id == sesion.conteo_id,
               ConteoReconteo.sesion_id == sesion.id)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if reconteo is None:
        raise errores.ReconteoNoEncontrado()
    if reconteo.estado == "TERMINADO":
        return reconteo
    if reconteo.estado != "ASIGNADO":
        raise errores.EstadoInvalido(
            "El líder canceló ese reconteo.", estado=reconteo.estado)
    reconteo.estado = "TERMINADO"
    reconteo.terminado_en = ahora
    await db.flush()
    return reconteo
