"""
Motored -- the daily Lore message with each asesor's report link
(odd/motored-reporte-diario-asesor, T3b).

Readiness: an APLICADO VENTAS carga whose `periodo_hasta` reaches
yesterday (Bogotá). `fecha_datos` is the latest `periodo_hasta`, capped at
yesterday. No such carga (Sunday, holiday, not loaded yet) means nothing is
sent that day.

When: never before `reporte_asesor_hora_minima`; then as soon as the KPI
summary is up to date (`resumen_al_dia`), or anyway after
`reporte_asesor_hora_limite`. While the summary is dirty the month read
answers live (`kpi_resumen_lectura.usar_resumen`), so the deadline path
never reads stale figures.

Who: an active, approved usuario with an approved cédula, a Telegram, an
active `ReporteAsesorLink`, a report in `ventas_del_mes(...)` (called ONCE
per run) and no 'enviado' ledger row for that date (`pendientes`). The
ledger (`models/reporte_asesor_envio.py`) gets one committed row per send.

Cost: `ventas_del_mes` (`reporte_asesor_ventas`) is the light read of the
month: the same liquidation as the full report builder
(`reportes_asesores`) and the same asesores, without the KPI board, the
year trend or any asesor detail. The message only needs
`cumplimiento_pct` and `total_a_pagar`, so nothing here runs the full
builder; the report page builds it when the asesor opens the link.

Telegram: `avisos_telegram.enviar_mensaje` does the call; an httpx event
hook reads the status so a 403 becomes 'bloqueado' (no retry) and a 429 is
retried with backoff (`enviar_con_reintentos`). About one message per
second.

The ADMIN table (T3d): one row per asesor with sales (`filas_asesores`,
from the same light read as the counts) with an `estado` code, and
`enviar_a_uno`, the "Enviar ahora" of one asesor, which bypasses the
once-per-date rule and records a `reenvio` ledger row.

Secrets: the token, the URL and the cédula are never logged nor stored in
`detalle`; logs carry usuario ids and counts only. The table shows the
cédula masked to its last 4 digits.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import (
    Awaitable, Callable, Dict, Iterable, List, Optional, Set,
)

import httpx
from sqlalchemy import and_, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.reporte_asesor_envio import ReporteAsesorEnvio
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.services import avisos_telegram, kpi_resumen, parametros
from app.motored.services import reporte_asesor_link as enlaces
from app.motored.services.reloj import BOGOTA_OFFSET, hoy_bogota
from app.motored.services.reporte_asesor_ventas import (
    VentasDelMes, ventas_del_mes,
)

logger = logging.getLogger("motored.reporte_asesor_envio")

CLAVE_ACTIVO = "reporte_asesor_envio_activo"
CLAVE_HORA_LIMITE = "reporte_asesor_hora_limite"
CLAVE_HORA_MINIMA = "reporte_asesor_hora_minima"
HORA_LIMITE = "10:00"
HORA_MINIMA = "06:00"

ENVIADO = "enviado"
FALLIDO = "fallido"
BLOQUEADO = "bloqueado"
MAX_FALLIDOS_POR_FECHA = 3
DETALLE_MAX = 80

RES_OK = "ok"
RES_BLOQUEADO = "bloqueado"
RES_LIMITE = "limite"
RES_ERROR = "error"
INTENTOS_429 = 3
ESPERA_429_MAX = 30.0
PAUSA_ENTRE_ENVIOS = 1.0

# Advisory-lock keys (kpi_resumen uses 7_203_581_101).
LOCK_ENVIO = 7_203_581_201
LOCK_REENVIO = 7_203_581_202

ESTADO_APLICADO = "APLICADO"
TIPO_VENTAS = "VENTAS"

# `estado` of a table row, in precedence order (T3d), plus two codes only
# the single send uses.
SIN_USUARIO = "sin_usuario"
CEDULA_PENDIENTE = "cedula_pendiente"
USUARIO_INACTIVO = "usuario_inactivo"
SIN_TELEGRAM = "sin_telegram"
SIN_ENLACE = "sin_enlace"
SIN_PRESUPUESTO = "sin_presupuesto"
LISTO = "listo"
SIN_CEDULA = "sin_cedula"
SIN_VENTAS = "sin_ventas"


# --- Configuración ---------------------------------------------------------

@dataclass(frozen=True)
class ConfigEnvio:
    activo: bool
    hora_limite: time
    hora_minima: time


def respaldos() -> Dict[str, object]:
    return {
        CLAVE_ACTIVO: False,
        CLAVE_HORA_LIMITE: HORA_LIMITE,
        CLAVE_HORA_MINIMA: HORA_MINIMA,
    }


def _hora(texto: str) -> time:
    horas, minutos = texto.split(":")
    return time(int(horas), int(minutos))


async def leer_config(db, ahora: datetime, memoria: dict) -> ConfigEnvio:
    """One read per tick; never raises (last known value, then defaults)."""
    valores = await parametros.leer_con_memoria(
        db, hoy_bogota(ahora), respaldos(), memoria)
    return ConfigEnvio(
        bool(valores[CLAVE_ACTIVO]),
        _hora(valores[CLAVE_HORA_LIMITE]),
        _hora(valores[CLAVE_HORA_MINIMA]),
    )


# --- Readiness -------------------------------------------------------------

def fecha_de_datos(maximo: Optional[date], hoy: date) -> Optional[date]:
    """The latest `periodo_hasta`, capped at yesterday."""
    if maximo is None:
        return None
    return min(maximo, hoy - timedelta(days=1))


def esta_lista(fecha: Optional[date], hoy: date) -> bool:
    return fecha is not None and fecha == hoy - timedelta(days=1)


async def ultima_fecha_datos(db, hoy: date) -> Optional[date]:
    stmt = select(func.max(CargaArchivo.periodo_hasta)).where(
        CargaArchivo.tipo == TIPO_VENTAS,
        CargaArchivo.estado == ESTADO_APLICADO,
    )
    return fecha_de_datos((await db.execute(stmt)).scalars().first(), hoy)


def resumen_al_dia(estado: Optional[kpi_resumen.Estado]) -> bool:
    """The KPI summary is built, not dirty and not being rebuilt."""
    return (
        estado is not None
        and estado.ultima_reconstruccion_total is not None
        and not estado.sucio
        and not estado.reconstruyendo
    )


async def resumen_listo(db) -> bool:
    """With the summaries switched off the month read is live, which
    is always up to date: no query."""
    if not settings.MOTORED_KPI_RESUMEN_ENABLED:
        return True
    return resumen_al_dia(await kpi_resumen.estado(db))


def toca_enviar(hora: time, config: ConfigEnvio, resumen_ok: bool) -> bool:
    if hora < config.hora_minima:
        return False
    return resumen_ok or hora >= config.hora_limite


# --- Eligibility -----------------------------------------------------------

@dataclass(frozen=True)
class Asesor:
    usuario_id: uuid.UUID
    nombre: str
    cedula: str
    cedula_aprobada: bool
    telegram_id: Optional[int]
    token: Optional[str] = field(default=None, repr=False)

    @property
    def completo(self) -> bool:
        return bool(self.cedula_aprobada and self.telegram_id is not None
                    and self.token)


@dataclass
class Clasificacion:
    elegibles: List[Asesor] = field(default_factory=list)
    sin_enlace: List[str] = field(default_factory=list)
    sin_cedula_aprobada: List[str] = field(default_factory=list)
    sin_telegram: List[str] = field(default_factory=list)
    sin_usuario: List[str] = field(default_factory=list)


async def leer_asesores(db) -> List[Asesor]:
    """Active, approved usuarios with a cédula, with their active link's
    token (None without one). One query."""
    stmt = select(
        Usuario.id, Usuario.nombre, Usuario.cedula,
        Usuario.cedula_aprobada, Usuario.telegram_id,
        ReporteAsesorLink.token,
    ).outerjoin(ReporteAsesorLink, and_(
        ReporteAsesorLink.usuario_id == Usuario.id,
        ReporteAsesorLink.revocado_en.is_(None),
    )).where(
        Usuario.cedula.is_not(None),
        Usuario.activo.is_(True),
        Usuario.status == "approved",
    ).order_by(Usuario.nombre)
    filas = (await db.execute(stmt)).all()
    return [Asesor(f[0], f[1], f[2], bool(f[3]), f[4], f[5]) for f in filas]


def _motivo(asesor: Asesor) -> Optional[str]:
    if not asesor.cedula_aprobada:
        return "sin_cedula_aprobada"
    if asesor.telegram_id is None:
        return "sin_telegram"
    if not asesor.token:
        return "sin_enlace"
    return None


def clasificar(asesores: Iterable[Asesor], reportes: dict) -> Clasificacion:
    """Splits the usuarios whose cédula has sales in `reportes`."""
    asesores = list(asesores)
    aprobadas = {a.cedula for a in asesores if a.cedula_aprobada}
    clas = Clasificacion()
    for asesor in asesores:
        if asesor.cedula not in reportes:
            continue
        motivo = _motivo(asesor)
        if motivo is None:
            clas.elegibles.append(asesor)
        elif not (motivo == "sin_cedula_aprobada"
                  and asesor.cedula in aprobadas):
            getattr(clas, motivo).append(asesor.nombre)
    con_usuario = {a.cedula for a in asesores}
    clas.sin_usuario = sorted(
        r.get("nombre") or "?" for c, r in reportes.items()
        if c not in con_usuario)
    return clas


# --- Ledger ----------------------------------------------------------------

@dataclass(frozen=True)
class FilaLedger:
    usuario_id: uuid.UUID
    nombre: str
    estado: str
    reenvio: bool
    n: int


async def leer_ledger(db, fecha: date) -> List[FilaLedger]:
    """Rows of `fecha` grouped by usuario, estado and reenvio."""
    stmt = select(
        ReporteAsesorEnvio.usuario_id, Usuario.nombre,
        ReporteAsesorEnvio.estado, ReporteAsesorEnvio.reenvio,
        func.count(),
    ).join(Usuario, Usuario.id == ReporteAsesorEnvio.usuario_id).where(
        ReporteAsesorEnvio.fecha_datos == fecha,
    ).group_by(
        ReporteAsesorEnvio.usuario_id, Usuario.nombre,
        ReporteAsesorEnvio.estado, ReporteAsesorEnvio.reenvio,
    )
    return [FilaLedger(*fila) for fila in (await db.execute(stmt)).all()]


def _estados(filas: Iterable[FilaLedger]) -> Dict[uuid.UUID, Set[str]]:
    por_usuario: Dict[uuid.UUID, Set[str]] = {}
    for fila in filas:
        por_usuario.setdefault(fila.usuario_id, set()).add(fila.estado)
    return por_usuario


def pendientes(asesores: Iterable[Asesor],
               filas: Iterable[FilaLedger]) -> List[Asesor]:
    """Once per date: drop whoever already got it (automatic or resend),
    blocked the bot, or failed `MAX_FALLIDOS_POR_FECHA` automatic tries."""
    filas = list(filas)
    estados = _estados(filas)
    fallos: Dict[uuid.UUID, int] = {}
    for fila in filas:
        if fila.estado == FALLIDO and not fila.reenvio:
            fallos[fila.usuario_id] = fallos.get(fila.usuario_id, 0) + fila.n
    salida = []
    for asesor in asesores:
        vistos = estados.get(asesor.usuario_id, set())
        if ENVIADO in vistos or BLOQUEADO in vistos:
            continue
        if fallos.get(asesor.usuario_id, 0) >= MAX_FALLIDOS_POR_FECHA:
            continue
        salida.append(asesor)
    return salida


def resumir_ledger(filas: Iterable[FilaLedger]) -> dict:
    """Final state per asesor: enviado > bloqueado > fallido."""
    filas = list(filas)
    nombres = {f.usuario_id: f.nombre for f in filas}
    conteo = {ENVIADO: 0, BLOQUEADO: 0, FALLIDO: 0}
    bloqueados = []
    for usuario_id, vistos in _estados(filas).items():
        final = next(e for e in (ENVIADO, BLOQUEADO, FALLIDO) if e in vistos)
        conteo[final] += 1
        if final == BLOQUEADO:
            bloqueados.append(nombres[usuario_id])
    return {
        "enviados": conteo[ENVIADO], "fallidos": conteo[FALLIDO],
        "bloqueados": conteo[BLOQUEADO],
        "nombres_bloqueados": sorted(bloqueados),
    }


# --- Message ---------------------------------------------------------------

def formato_pesos(valor) -> str:
    return "$" + f"{int(round(valor or 0)):,}".replace(",", ".")


def formato_pct(fraccion: Optional[float]) -> str:
    if fraccion is None:
        return "sin dato"
    pct = (Decimal(str(fraccion)) * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{pct}".replace(".", ",") + "%"


def texto_mensaje(nombre: str, fecha: date, reporte: dict, url: str) -> str:
    return (
        f"Hola {nombre}, tu informe con ventas al {fecha:%d/%m/%Y}: "
        f"cumplimiento {formato_pct(reporte.get('cumplimiento_pct'))} · "
        "total estimado a pagar "
        f"{formato_pesos(reporte.get('total_a_pagar'))} "
        "(comisión estimada, no es un pago). Ábrelo con tu cédula: "
        f"{url}"
    )


@dataclass(frozen=True)
class Destino:
    asesor: Asesor
    texto: str = field(repr=False)


def armar_destinos(asesores: Iterable[Asesor], reportes: dict,
                   fecha: date) -> List[Destino]:
    """One message per asesor; raises `FaltaConfiguracion` without
    `MOTORED_PUBLIC_URL`."""
    return [
        Destino(a, texto_mensaje(a.nombre, fecha, reportes[a.cedula],
                                 enlaces.url_del_link(a.token)))
        for a in asesores
    ]


async def preparar_destinos(db, fecha: date) -> List[Destino]:
    """Every eligible asesor's message for `fecha` (the ADMIN resend):
    the light month read runs once."""
    reportes = (await ventas_del_mes(db, fecha)).reportes
    clas = clasificar(await leer_asesores(db), reportes)
    return armar_destinos(clas.elegibles, reportes, fecha)


# --- Telegram --------------------------------------------------------------

@dataclass(frozen=True)
class Respuesta:
    resultado: str
    espera: Optional[float] = None
    detalle: Optional[str] = None


Enviar = Callable[[int, str], Awaitable[Respuesta]]


def _segundos(valor: Optional[str]) -> Optional[float]:
    try:
        return float(valor) if valor is not None else None
    except ValueError:
        return None


def _respuesta(ok: bool, visto: dict) -> Respuesta:
    if ok:
        return Respuesta(RES_OK)
    status = visto.get("status")
    if status == 403:
        return Respuesta(RES_BLOQUEADO, detalle="Telegram 403")
    if status == 429:
        return Respuesta(RES_LIMITE, espera=_segundos(visto.get("espera")),
                         detalle="Telegram 429")
    if status is None:
        return Respuesta(RES_ERROR, detalle="Telegram sin respuesta")
    return Respuesta(RES_ERROR, detalle=f"Telegram {status}")


async def enviar_telegram(token: str, chat_id: int, texto: str,
                          transporte=None) -> Respuesta:
    """`enviar_mensaje` (never raises, never logs the token) plus the HTTP
    status, read by a response hook."""
    visto: dict = {}

    async def ver(respuesta: httpx.Response) -> None:
        visto["status"] = respuesta.status_code
        visto["espera"] = respuesta.headers.get("retry-after")

    async with httpx.AsyncClient(
            timeout=avisos_telegram.TIMEOUT_SEGUNDOS, transport=transporte,
            event_hooks={"response": [ver]}) as cliente:
        ok = await avisos_telegram.enviar_mensaje(
            token, chat_id, texto, cliente=cliente)
    return _respuesta(ok, visto)


def _espera_429(respuesta: Respuesta, intento: int) -> float:
    if respuesta.espera is not None and respuesta.espera > 0:
        return min(respuesta.espera, ESPERA_429_MAX)
    return float(2 ** intento)


async def enviar_con_reintentos(enviar: Enviar, chat_id: int, texto: str,
                                dormir) -> Respuesta:
    """A 429 is retried with backoff, `INTENTOS_429` tries in all; then it
    counts as an error (the daily loop tries again on a later tick)."""
    respuesta = Respuesta(RES_ERROR)
    for intento in range(INTENTOS_429):
        respuesta = await enviar(chat_id, texto)
        if respuesta.resultado != RES_LIMITE:
            return respuesta
        if intento < INTENTOS_429 - 1:
            await dormir(_espera_429(respuesta, intento))
    return Respuesta(RES_ERROR, detalle="Telegram 429 x3")


# --- Batch -----------------------------------------------------------------

@dataclass
class Conteo:
    enviados: int = 0
    fallidos: int = 0
    bloqueados: int = 0

    def sumar(self, estado: str) -> None:
        if estado == ENVIADO:
            self.enviados += 1
        elif estado == BLOQUEADO:
            self.bloqueados += 1
        else:
            self.fallidos += 1


def _estado_de(respuesta: Respuesta) -> str:
    if respuesta.resultado == RES_OK:
        return ENVIADO
    if respuesta.resultado == RES_BLOQUEADO:
        return BLOQUEADO
    return FALLIDO


def _detalle(respuesta: Respuesta, destino: Destino) -> Optional[str]:
    """Short and free of secrets: dropped when it mentions the token, the
    link path or the cédula."""
    texto = respuesta.detalle
    if not texto:
        return None
    secretos = (destino.asesor.token or "", enlaces.RUTA_PUBLICA,
                destino.asesor.cedula, "informe")
    if any(s and s in texto for s in secretos):
        return "Telegram error"
    return texto[:DETALLE_MAX]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _registrar(db, destino: Destino, fecha: date, estado: str,
                     detalle: Optional[str], reenvio: bool,
                     solicitado_por, cuando: datetime) -> None:
    asesor = destino.asesor
    db.add(ReporteAsesorEnvio(
        id=uuid.uuid4(), usuario_id=asesor.usuario_id, cedula=asesor.cedula,
        fecha_datos=fecha, enviado_en=cuando, estado=estado,
        detalle=detalle, reenvio=reenvio, solicitado_por=solicitado_por))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "reporte asesor: el envío del usuario %s ya estaba registrado",
            asesor.usuario_id)


async def enviar_lote(db, destinos: List[Destino], fecha: date,
                      enviar: Enviar, dormir, *, reenvio: bool = False,
                      solicitado_por=None, reloj=_ahora) -> Conteo:
    """Sends each message (about one per second) and commits its ledger
    row right away."""
    conteo = Conteo()
    for posicion, destino in enumerate(destinos):
        if posicion:
            await dormir(PAUSA_ENTRE_ENVIOS)
        respuesta = await enviar_con_reintentos(
            enviar, destino.asesor.telegram_id, destino.texto, dormir)
        estado = _estado_de(respuesta)
        if estado != ENVIADO:
            logger.warning("reporte asesor: usuario %s quedó %s",
                           destino.asesor.usuario_id, estado)
        await _registrar(db, destino, fecha, estado,
                         _detalle(respuesta, destino), reenvio,
                         solicitado_por, reloj())
        conteo.sumar(estado)
    logger.info(
        "reporte asesor %s (reenvío=%s): %d enviados, %d fallidos, "
        "%d bloqueados", fecha.isoformat(), reenvio, conteo.enviados,
        conteo.fallidos, conteo.bloqueados)
    return conteo


# --- The daily run ---------------------------------------------------------

async def tomar_candado(db, clave: int) -> bool:
    """Transaction-level advisory lock, without waiting. It is held until
    `db`'s transaction ends, so `db` must not be the one that commits."""
    stmt = select(func.pg_try_advisory_xact_lock(clave))
    return bool((await db.execute(stmt)).scalars().first())


async def esperar_candado(db, clave: int, segundos: int) -> bool:
    """Like `tomar_candado`, but waits up to `segundos`."""
    await db.execute(select(func.set_config(
        "lock_timeout", f"{int(segundos)}s", True)))
    try:
        await db.execute(select(func.pg_advisory_xact_lock(clave)))
    except DBAPIError:
        return False
    return True


async def _por_enviar(db, fecha: date,
                      sin_reporte: Dict[date, Set[uuid.UUID]]):
    """Complete asesores not yet served for `fecha` and not known to lack
    sales; None when there is nobody (no month read)."""
    completos = [a for a in await leer_asesores(db) if a.completo]
    olvidar = sin_reporte.setdefault(fecha, set())
    candidatos = [a for a in pendientes(completos, await leer_ledger(
        db, fecha)) if a.usuario_id not in olvidar]
    return candidatos or None


async def envio_diario(db, ahora: datetime, config: ConfigEnvio,
                       enviar: Enviar, dormir,
                       sin_reporte: Dict[date, Set[uuid.UUID]]
                       ) -> Optional[Conteo]:
    """The automatic send of one tick (the caller holds `LOCK_ENVIO`).
    `sin_reporte` remembers, per date, who has no sales, so the month
    read does not run again every tick for them."""
    local = ahora.astimezone(BOGOTA_OFFSET)
    fecha = await ultima_fecha_datos(db, local.date())
    if not esta_lista(fecha, local.date()):
        return None
    resumen_ok = await resumen_listo(db)
    if not toca_enviar(local.time(), config, resumen_ok):
        return None
    candidatos = await _por_enviar(db, fecha, sin_reporte)
    if candidatos is None:
        return None
    reportes = (await ventas_del_mes(db, fecha)).reportes
    con_reporte = [a for a in candidatos if a.cedula in reportes]
    sin_reporte[fecha].update(
        a.usuario_id for a in candidatos if a.cedula not in reportes)
    if not con_reporte:
        return None
    destinos = armar_destinos(con_reporte, reportes, fecha)
    return await enviar_lote(db, destinos, fecha, enviar, dormir)


# --- ADMIN state -----------------------------------------------------------

async def _ultima_fecha_enviada(db) -> Optional[date]:
    stmt = select(func.max(ReporteAsesorEnvio.fecha_datos))
    return (await db.execute(stmt)).scalars().first()


async def _ultimo_envio(db) -> dict:
    fecha = await _ultima_fecha_enviada(db)
    filas = await leer_ledger(db, fecha) if fecha else []
    resumen = resumir_ledger(filas)
    return {"fecha_datos": fecha.isoformat() if fecha else None, **resumen}


async def _disponible(db, fecha: Optional[date]) -> dict:
    """Counts and rows of `fecha` from ONE light month read (never the
    full report builder: this runs on every open of the screen)."""
    vacio = {"elegibles": 0, "sin_enlace": [], "sin_cedula_aprobada": [],
             "sin_telegram": [], "sin_usuario": [], "sin_presupuesto": 0,
             "sin_cedula": 0, "asesores": []}
    if fecha is None:
        return vacio
    ventas = await ventas_del_mes(db, fecha)
    clas = clasificar(await leer_asesores(db), ventas.reportes)
    return {
        "elegibles": len(clas.elegibles), "sin_enlace": clas.sin_enlace,
        "sin_cedula_aprobada": clas.sin_cedula_aprobada,
        "sin_telegram": clas.sin_telegram, "sin_usuario": clas.sin_usuario,
        "sin_presupuesto": ventas.sin_presupuesto,
        "sin_cedula": ventas.sin_cedula,
        "asesores": await filas_asesores(db, ventas.asesores),
    }


async def estado_envio(db, hoy: date) -> dict:
    """What the ADMIN sees in Configuración: names, counts and the
    per-asesor rows, never a token, URL or full cédula."""
    ahora = datetime.combine(hoy, time(12), tzinfo=BOGOTA_OFFSET)
    config = await leer_config(db, ahora, {})
    ultimo = await _ultimo_envio(db)
    fecha = await ultima_fecha_datos(db, hoy)
    return {
        "envio_activo": config.activo,
        "hora_limite": config.hora_limite.strftime("%H:%M"),
        "hora_minima": config.hora_minima.strftime("%H:%M"),
        "ultimo_envio": {
            k: v for k, v in ultimo.items() if k != "nombres_bloqueados"},
        "bloqueados": ultimo["nombres_bloqueados"],
        "fecha_disponible": fecha.isoformat() if fecha else None,
        "lista_hoy": esta_lista(fecha, hoy),
        **await _disponible(db, fecha),
    }


# --- Per-asesor table (T3d) ------------------------------------------------

@dataclass(frozen=True)
class Titular:
    """A usuario holding a cédula, whatever the state of its account."""
    usuario_id: uuid.UUID
    nombre: str
    cedula: Optional[str]
    cedula_aprobada: bool
    activo: bool
    status: str
    telegram_id: Optional[int]
    token: Optional[str] = field(default=None, repr=False)

    def como_asesor(self) -> Asesor:
        return Asesor(self.usuario_id, self.nombre, self.cedula,
                      self.cedula_aprobada, self.telegram_id, self.token)


@dataclass(frozen=True)
class UltimoEnvio:
    enviado_en: datetime
    estado: str


async def _leer_titulares(db, condicion) -> List[Titular]:
    """Usuarios matching `condicion`, with their active link's token
    (None without one). One query."""
    stmt = select(
        Usuario.id, Usuario.nombre, Usuario.cedula,
        Usuario.cedula_aprobada, Usuario.activo, Usuario.status,
        Usuario.telegram_id, ReporteAsesorLink.token,
    ).outerjoin(ReporteAsesorLink, and_(
        ReporteAsesorLink.usuario_id == Usuario.id,
        ReporteAsesorLink.revocado_en.is_(None),
    )).where(condicion).order_by(Usuario.nombre, Usuario.id)
    filas = (await db.execute(stmt)).all()
    return [Titular(f[0], f[1], f[2], bool(f[3]), bool(f[4]), f[5], f[6],
                    f[7]) for f in filas]


async def leer_titulares(db, cedulas: Iterable[str]) -> List[Titular]:
    """Every non-rejected usuario holding one of `cedulas`."""
    cedulas = sorted(set(cedulas))
    if not cedulas:
        return []
    return await _leer_titulares(db, and_(
        Usuario.cedula.in_(cedulas), Usuario.status != "rejected"))


async def leer_titular(db, usuario_id) -> Optional[Titular]:
    filas = await _leer_titulares(db, Usuario.id == usuario_id)
    return filas[0] if filas else None


async def leer_ultimos_envios(db, usuario_ids: Iterable[uuid.UUID]
                              ) -> Dict[uuid.UUID, UltimoEnvio]:
    """The latest ledger row of each usuario: latest `fecha_datos`, then
    latest `enviado_en`. One query."""
    ids = list(set(usuario_ids))
    if not ids:
        return {}
    orden = func.row_number().over(
        partition_by=ReporteAsesorEnvio.usuario_id,
        order_by=(ReporteAsesorEnvio.fecha_datos.desc(),
                  ReporteAsesorEnvio.enviado_en.desc()),
    ).label("orden")
    sub = select(
        ReporteAsesorEnvio.usuario_id, ReporteAsesorEnvio.enviado_en,
        ReporteAsesorEnvio.estado, orden,
    ).where(ReporteAsesorEnvio.usuario_id.in_(ids)).subquery()
    stmt = select(sub.c.usuario_id, sub.c.enviado_en, sub.c.estado).where(
        sub.c.orden == 1)
    return {f[0]: UltimoEnvio(f[1], f[2])
            for f in (await db.execute(stmt)).all()}


def elegir_titular(titulares: Iterable[Titular]) -> Optional[Titular]:
    """The approved holder (unique by index), else the first pending."""
    titulares = list(titulares)
    aprobados = [t for t in titulares if t.cedula_aprobada]
    return (aprobados or titulares or [None])[0]


def estado_titular(titular: Optional[Titular], con_reporte: bool,
                   ultimo: Optional[UltimoEnvio]) -> str:
    """The first thing missing for the message, in precedence order."""
    if titular is None:
        return SIN_USUARIO
    if not titular.cedula_aprobada:
        return CEDULA_PENDIENTE
    if not titular.activo or titular.status != "approved":
        return USUARIO_INACTIVO
    if titular.telegram_id is None:
        return SIN_TELEGRAM
    if not titular.token:
        return SIN_ENLACE
    if not con_reporte:
        return SIN_PRESUPUESTO
    if ultimo is not None and ultimo.estado == BLOQUEADO:
        return BLOQUEADO
    return LISTO


def enmascarar(cedula: str) -> str:
    return "****" + (cedula or "")[-4:]


def _ultimo_json(ultimo: Optional[UltimoEnvio]) -> Optional[dict]:
    if ultimo is None:
        return None
    return {"en": ultimo.enviado_en.isoformat(), "estado": ultimo.estado}


def fila_asesor(cedula: str, venta: dict, titular: Optional[Titular],
                ultimo: Optional[UltimoEnvio]) -> dict:
    estado = estado_titular(titular, venta["con_reporte"], ultimo)
    return {
        "cedula_mask": enmascarar(cedula),
        "nombre": titular.nombre if titular else (venta["nombre"] or "?"),
        "tienda": venta["tienda"],
        "usuario_id": str(titular.usuario_id) if titular else None,
        "estado": estado,
        "ultimo_envio": _ultimo_json(ultimo),
        "puede_enviar": estado == LISTO,
    }


async def filas_asesores(db, ventas: Dict[str, dict]) -> List[dict]:
    """One row per asesor of `ventas` (`VentasDelMes.asesores`: cédula to
    name, tienda and `con_reporte`), sorted by name. Two queries, whatever
    the number of asesores."""
    por_cedula: Dict[str, List[Titular]] = {}
    for titular in await leer_titulares(db, ventas):
        por_cedula.setdefault(titular.cedula, []).append(titular)
    elegidos = {c: elegir_titular(por_cedula.get(c, [])) for c in ventas}
    ultimos = await leer_ultimos_envios(
        db, [t.usuario_id for t in elegidos.values() if t])
    filas = [
        fila_asesor(cedula, ventas[cedula], titular,
                    ultimos.get(titular.usuario_id) if titular else None)
        for cedula, titular in elegidos.items()
    ]
    return sorted(filas, key=lambda f: (f["nombre"] or "").lower())


# --- Single send (T3d) -----------------------------------------------------

class NoListo(Exception):
    """The asesor cannot get the message now; `estado` says why."""

    def __init__(self, estado: str):
        super().__init__(estado)
        self.estado = estado


@dataclass(frozen=True)
class EnvioUno:
    estado: str
    nombre: str


async def _verificar_listo(db, titular: Titular,
                          ventas: VentasDelMes) -> None:
    venta = ventas.asesores.get(titular.cedula)
    if venta is None:
        raise NoListo(SIN_VENTAS)
    ultimos = await leer_ultimos_envios(db, [titular.usuario_id])
    estado = estado_titular(
        titular, venta["con_reporte"], ultimos.get(titular.usuario_id))
    if estado != LISTO:
        raise NoListo(estado)


async def enviar_a_uno(db, usuario_id: uuid.UUID, fecha: date,
                       enviar: Enviar, dormir,
                       solicitado_por: uuid.UUID) -> EnvioUno:
    """The "Enviar ahora" of one asesor: their message for `fecha`, sent
    now whatever the ledger says, recorded as a `reenvio` by
    `solicitado_por`. Raises `LookupError` for an unknown usuario and
    `NoListo` when the message cannot go out."""
    titular = await leer_titular(db, usuario_id)
    if titular is None:
        raise LookupError("usuario inexistente")
    if not titular.cedula:
        raise NoListo(SIN_CEDULA)
    ventas = await ventas_del_mes(db, fecha)
    await _verificar_listo(db, titular, ventas)
    destinos = armar_destinos(
        [titular.como_asesor()], ventas.reportes, fecha)
    conteo = await enviar_lote(
        db, destinos, fecha, enviar, dormir, reenvio=True,
        solicitado_por=solicitado_por)
    if conteo.enviados:
        return EnvioUno(ENVIADO, titular.nombre)
    if conteo.bloqueados:
        return EnvioUno(BLOQUEADO, titular.nombre)
    return EnvioUno(FALLIDO, titular.nombre)
