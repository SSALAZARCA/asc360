"""
Inventory counts -- pair device sessions (odd/motored-conteos-inventario,
WU7; design §4.4, §4.7, §5.3, §8.1-§8.3, ADR-3, ADR-7).

Joining (`unirse`) needs the conteo's link slug, its 6-digit code and 2-3
members (name + cédula). Every failure is the same AccesoInvalido. Wrong
codes are counted twice, both under the conteo row lock:

- per client (sha256 of the IP, never the raw IP; `conteo_acceso_intento`):
  5 failures in 15 minutes lock that client for 15 minutes;
- per conteo: 30 failures in an hour rotate the code by themselves.
  Connected pairs keep counting: their device tokens do not depend on the
  code.

The counters are COMMITTED before AccesoInvalido is raised: the request
session rolls back on an exception, which would erase them.

A device session token is `secrets.token_urlsafe(32)`; only its sha256 is
stored. Cédulas are stored for traceability and the different-pair rule,
and never returned (Ley 1581). Apart from that failure commit, nothing
here commits: the API owns the transaction.
"""
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.conteo import ESTADOS_ABIERTOS, Conteo
from app.motored.models.conteo_acceso_intento import ConteoAccesoIntento
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.models.sucursal import Sucursal
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import acceso, errores

MAX_FALLOS_CLIENTE = 5
VENTANA_CLIENTE = timedelta(minutes=15)
BLOQUEO_CLIENTE = timedelta(minutes=15)
MAX_FALLOS_CONTEO = 30
VENTANA_CONTEO = timedelta(hours=1)
ACTIVIDAD_CADA = timedelta(seconds=20)
BYTES_TOKEN = 32


class FilaSesion(NamedTuple):
    """A session with what its views need. `integrantes` are ORM rows
    (they hold the cédula): callers serialize names only."""

    sesion: ConteoSesion
    numero: int
    integrantes: List[ConteoIntegrante]
    ubicacion: Optional[UbicacionInventario]


class Pareja(NamedTuple):
    """The active session behind a device token."""

    sesion: ConteoSesion
    conteo: Conteo
    sucursal: str


@dataclass(frozen=True)
class Ingreso:
    """A successful join. `token` is the plain device token: it is never
    stored, so this is the only time it exists."""

    fila: FilaSesion
    token: str
    sucursal: str
    estado_conteo: str


# --- pure rules -------------------------------------------------------------


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def nombre_corto(nombre: str) -> str:
    """'Ana Ruiz Gil' -> 'Ana R.'; a single word stays as it is."""
    partes = nombre.split()
    if len(partes) < 2:
        return nombre.strip()
    return f"{partes[0]} {partes[1][0]}."


def etiqueta(numero: int, nombres: Sequence[str]) -> str:
    """'Pareja 3 · Ana R. y Luis G.' (the prototype's pair label)."""
    cortos = [nombre_corto(n) for n in nombres]
    if len(cortos) > 1:
        personas = ", ".join(cortos[:-1]) + " y " + cortos[-1]
    else:
        personas = "".join(cortos)
    return f"Pareja {numero} · {personas}"


def registrar_fallo_cliente(
        intento: ConteoAccesoIntento, ahora: datetime) -> None:
    """One more failure for this client; the 5th inside 15 minutes locks
    it for 15 minutes and restarts its count."""
    inicio = intento.ventana_inicio
    if inicio is None or ahora - inicio >= VENTANA_CLIENTE:
        intento.fallidos = 0
        intento.ventana_inicio = ahora
    intento.fallidos = (intento.fallidos or 0) + 1
    if intento.fallidos >= MAX_FALLOS_CLIENTE:
        intento.bloqueado_hasta = ahora + BLOQUEO_CLIENTE
        intento.fallidos = 0
        intento.ventana_inicio = ahora


def registrar_fallo_conteo(conteo: Conteo, ahora: datetime) -> bool:
    """One more failure on this conteo; the 30th inside an hour rotates
    its code (returns True). Connected sessions are untouched."""
    inicio = conteo.acceso_ventana_inicio
    if inicio is None or ahora - inicio >= VENTANA_CONTEO:
        conteo.acceso_fallidos_hora = 0
        conteo.acceso_ventana_inicio = ahora
    conteo.acceso_fallidos_hora = (conteo.acceso_fallidos_hora or 0) + 1
    if conteo.acceso_fallidos_hora < MAX_FALLOS_CONTEO:
        return False
    acceso.asignar_codigo(conteo, ahora)
    conteo.acceso_fallidos_hora = 0
    conteo.acceso_ventana_inicio = None
    return True


def bloqueado(intento: Optional[ConteoAccesoIntento], ahora) -> bool:
    return bool(
        intento is not None and intento.bloqueado_hasta is not None
        and intento.bloqueado_hasta > ahora)


# --- joining ----------------------------------------------------------------


async def _conteo_por_slug(
        db: AsyncSession, slug: str) -> Optional[Tuple[Conteo, str]]:
    fila = (await db.execute(
        select(Conteo, Sucursal.nombre)
        .join(Sucursal, Sucursal.id == Conteo.sucursal_id)
        .where(Conteo.enlace_slug == slug, Conteo.tipo == "TOTAL")
        .with_for_update(of=Conteo)
        .execution_options(populate_existing=True))).first()
    return None if fila is None else (fila[0], fila[1])


async def _intento(
        db: AsyncSession, conteo_id: uuid.UUID,
        cliente: str) -> Optional[ConteoAccesoIntento]:
    return (await db.execute(
        select(ConteoAccesoIntento).where(
            ConteoAccesoIntento.conteo_id == conteo_id,
            ConteoAccesoIntento.cliente == cliente))).scalars().first()


async def _fallar(
        db: AsyncSession, conteo: Conteo, intento, cliente: str,
        ahora: datetime) -> None:
    """Counts a wrong code, COMMITS, then raises AccesoInvalido."""
    if intento is None:
        intento = ConteoAccesoIntento(
            conteo_id=conteo.id, cliente=cliente, fallidos=0,
            ventana_inicio=ahora)
        db.add(intento)
    registrar_fallo_cliente(intento, ahora)
    registrar_fallo_conteo(conteo, ahora)
    await db.commit()
    raise errores.AccesoInvalido()


async def _numero_siguiente(db: AsyncSession, conteo_id) -> int:
    previas = (await db.execute(
        select(func.count(ConteoSesion.id)).where(
            ConteoSesion.conteo_id == conteo_id))).scalars().first()
    return int(previas or 0) + 1


async def _crear_sesion(
        db: AsyncSession, conteo: Conteo, integrantes, dispositivo: str,
        ahora: datetime) -> Tuple[ConteoSesion, List, str]:
    """The session row is flushed BEFORE its members: the models have no
    ORM relationship, so the unit of work does not order the FK."""
    token = secrets.token_urlsafe(BYTES_TOKEN)
    sesion = ConteoSesion(
        id=uuid.uuid4(), conteo_id=conteo.id, tipo="PAREJA",
        token_hash=sha256(token), estado="CONECTADA",
        dispositivo=dispositivo, conectada_en=ahora,
        ultima_actividad_en=ahora)
    db.add(sesion)
    await db.flush()
    personas = [
        ConteoIntegrante(
            id=uuid.uuid4(), sesion_id=sesion.id, orden=orden,
            nombre=nombre, cedula=cedula)
        for orden, (nombre, cedula) in enumerate(integrantes, start=1)]
    for persona in personas:
        db.add(persona)
    return sesion, personas, token


async def unirse(
        db: AsyncSession, slug: str, codigo: str,
        integrantes: Sequence[Tuple[str, str]], dispositivo: str,
        cliente: str, ahora: Optional[datetime] = None) -> Ingreso:
    """A new pair session on a running conteo. `integrantes` are
    (name, cleaned cédula); `cliente` is the raw client address (only its
    hash is stored). AccesoInvalido / DemasiadosIntentos otherwise."""
    ahora = ahora or datetime.now(timezone.utc)
    encontrado = await _conteo_por_slug(db, slug)
    if encontrado is None:
        raise errores.AccesoInvalido()
    conteo, sucursal = encontrado
    huella = sha256(cliente)
    intento = await _intento(db, conteo.id, huella)
    if bloqueado(intento, ahora):
        raise errores.DemasiadosIntentos()
    if conteo.estado not in ESTADOS_ABIERTOS:
        raise errores.AccesoInvalido()
    if not acceso.verificar_codigo(conteo.id, codigo, conteo.codigo_hash):
        await _fallar(db, conteo, intento, huella, ahora)
    if intento is not None:
        intento.fallidos = 0
        intento.bloqueado_hasta = None
    numero = await _numero_siguiente(db, conteo.id)
    sesion, personas, token = await _crear_sesion(
        db, conteo, integrantes, dispositivo, ahora)
    await db.flush()
    fila = FilaSesion(sesion, numero, personas, None)
    return Ingreso(fila, token, sucursal, conteo.estado)


# --- the device session -----------------------------------------------------


async def pareja_activa(
        db: AsyncSession, slug: str, token: Optional[str],
        ahora: Optional[datetime] = None) -> Pareja:
    """The CONECTADA session of a running conteo behind `token`, on the
    conteo of `slug`; SesionInactiva for anything else. Touches
    `ultima_actividad_en` at most every 20 s (the caller commits)."""
    if not token:
        raise errores.SesionInactiva()
    fila = (await db.execute(
        select(ConteoSesion, Conteo, Sucursal.nombre)
        .join(Conteo, Conteo.id == ConteoSesion.conteo_id)
        .join(Sucursal, Sucursal.id == Conteo.sucursal_id)
        .where(ConteoSesion.token_hash == sha256(token)))).first()
    if fila is None:
        raise errores.SesionInactiva()
    sesion, conteo, sucursal = fila[0], fila[1], fila[2]
    if (sesion.estado != "CONECTADA" or conteo.enlace_slug != slug
            or conteo.estado not in ESTADOS_ABIERTOS):
        raise errores.SesionInactiva()
    return Pareja(sesion, conteo, sucursal)


def tocar_actividad(sesion: ConteoSesion, ahora: datetime) -> bool:
    """True when `ultima_actividad_en` moved (older than 20 s)."""
    ultima = sesion.ultima_actividad_en
    if ultima is not None and ahora - ultima < ACTIVIDAD_CADA:
        return False
    sesion.ultima_actividad_en = ahora
    return True


def salir(sesion: ConteoSesion, ahora: datetime) -> None:
    """The device leaves by itself: DESCONECTADA, readings kept."""
    sesion.estado = "DESCONECTADA"
    sesion.desconectada_en = ahora
    sesion.desconectada_por = None


async def _integrantes(
        db: AsyncSession, ids: Sequence[uuid.UUID]) -> dict:
    por_sesion = {i: [] for i in ids}
    if not ids:
        return por_sesion
    filas = (await db.execute(
        select(ConteoIntegrante)
        .where(ConteoIntegrante.sesion_id.in_(ids))
        .order_by(ConteoIntegrante.sesion_id, ConteoIntegrante.orden)
    )).scalars().all()
    for persona in filas:
        por_sesion[persona.sesion_id].append(persona)
    return por_sesion


async def describir(db: AsyncSession, sesion: ConteoSesion) -> FilaSesion:
    """Number, members and current location of one session."""
    orden = tuple_(ConteoSesion.conectada_en, ConteoSesion.id)
    numero = (await db.execute(
        select(func.count(ConteoSesion.id)).where(
            ConteoSesion.conteo_id == sesion.conteo_id,
            orden <= tuple_(sesion.conectada_en, sesion.id))
    )).scalars().first()
    personas = await _integrantes(db, [sesion.id])
    ubicacion = None
    if sesion.ubicacion_actual_id is not None:
        ubicacion = await db.get(
            UbicacionInventario, sesion.ubicacion_actual_id)
    return FilaSesion(
        sesion, int(numero or 1), personas[sesion.id], ubicacion)


# --- leader side ------------------------------------------------------------


async def listar(db: AsyncSession, conteo_id: uuid.UUID) -> List[FilaSesion]:
    """Every session of a conteo, in join order (`numero` 1, 2, ...)."""
    filas = (await db.execute(
        select(ConteoSesion, UbicacionInventario)
        .outerjoin(
            UbicacionInventario,
            UbicacionInventario.id == ConteoSesion.ubicacion_actual_id)
        .where(ConteoSesion.conteo_id == conteo_id)
        .order_by(ConteoSesion.conectada_en, ConteoSesion.id))).all()
    personas = await _integrantes(db, [f[0].id for f in filas])
    return [
        FilaSesion(f[0], numero, personas[f[0].id], f[1])
        for numero, f in enumerate(filas, start=1)]


async def desconectar(
        db: AsyncSession, conteo_id: uuid.UUID, sesion_id: uuid.UUID,
        usuario_id: uuid.UUID, ahora: Optional[datetime] = None,
) -> FilaSesion:
    """The leader cuts a CONECTADA session (its readings are kept). An
    already disconnected or closed one is returned as it is."""
    ahora = ahora or datetime.now(timezone.utc)
    sesion = (await db.execute(
        select(ConteoSesion).where(
            ConteoSesion.id == sesion_id,
            ConteoSesion.conteo_id == conteo_id)
        .with_for_update()
        .execution_options(populate_existing=True))).scalars().first()
    if sesion is None:
        raise errores.SesionNoEncontrada()
    if sesion.estado == "CONECTADA":
        sesion.estado = "DESCONECTADA"
        sesion.desconectada_en = ahora
        sesion.desconectada_por = usuario_id
        await db.flush()
    return await describir(db, sesion)
