"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6b, ADR-5): la
ejecución de una corrida en segundo plano.

Tres piezas, todas sobre la tabla `corrida` (nunca `carga_archivo`):

1. `reclamar_siguiente` toma la corrida PENDIENTE elegible más antigua con UN
   `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING id`:
   con varias réplicas del backend cada una recibe una corrida distinta (o
   ninguna) y nunca dos toman la misma. El claim fija el latido, cuenta el
   intento y se confirma solo, antes de calcular.
2. `barrer_estancadas` recupera las corridas CALCULANDO cuyo latido venció
   (el proceso murió): vuelven a PENDIENTE con espera 30 s * 2^(intentos-1)
   o, agotados los intentos, quedan FALLIDA (E-CORRIDA-031). Reanudar es
   seguro: las sucursales terminadas no se recalculan y las líneas sueltas
   de la que quedó a medias se reemplazan.
3. `ejecutar_corrida` recorre las sucursales pendientes de una corrida ya
   reclamada. Cada sucursal es UNA transacción (carga, cálculo en el
   ejecutor, guardado con latido y progreso, commit). Una falla transitoria
   de base se reintenta 3 veces con espera de 1 s y 2 s; agotadas, esa
   sucursal queda FALLIDA (E-CORRIDA-099) y las demás siguen. Si la
   preparación misma falla (contexto imposible de armar) o algo inesperado
   rompe el recorrido, la corrida se devuelve con el mismo criterio del
   barrido, sin esperar el timeout. Ante un cierre del proceso
   (`CancelledError`) se devuelve a PENDIENTE sin gastar un intento.

El reloj, la espera y el ejecutor se inyectan para probarlo con un reloj
congelado. Los latidos que escribe la persistencia usan la hora de la base;
el barrido compara contra la hora del proceso: con el timeout en minutos, el
desfase normal entre ambos relojes no importa.
"""
import asyncio
import logging
from concurrent.futures import Executor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.motored.database import motored_session_maker
from app.motored.models.corrida import Corrida
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas import servicio as sv

logger = logging.getLogger("motored.corridas.ejecucion")

BACKOFF_BASE = timedelta(seconds=30)
INTENTOS_DBAPI = 3
ESPERAS_DBAPI = (1.0, 2.0)


class Decision(NamedTuple):
    """A dónde va una corrida estancada."""

    estado: str
    reintentar_despues_de: Optional[datetime]
    codigo: Optional[str]


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def espera_reintento(intentos: int) -> timedelta:
    """Espera tras `intentos` reclamos: 30 s, 60 s, 120 s, ..."""
    return BACKOFF_BASE * (2 ** (intentos - 1))


def decidir_estancada(
    intentos: int, max_intentos: int, ahora: datetime,
) -> Decision:
    """PENDIENTE con backoff mientras queden intentos; si no, FALLIDA."""
    if intentos >= max_intentos:
        return Decision(
            estados.FALLIDA, None, codigos.E_CORRIDA_REINTENTOS_AGOTADOS)
    return Decision(
        estados.PENDIENTE, ahora + espera_reintento(intentos), None)


# --- Claim ------------------------------------------------------------------


async def reclamar_siguiente(db, ahora: datetime) -> Optional[UUID]:
    """PENDIENTE -> CALCULANDO de la corrida más antigua cuya espera venció.

    Atómico entre réplicas (`SKIP LOCKED` + guarda de estado en el mismo
    UPDATE). Confirma siempre: el claim tiene que ser visible antes de que
    empiece el cálculo. `None` si no había ninguna elegible.
    """
    candidata = (
        select(Corrida.id)
        .where(
            Corrida.estado == estados.PENDIENTE,
            or_(Corrida.reintentar_despues_de.is_(None),
                Corrida.reintentar_despues_de <= ahora))
        .order_by(Corrida.created_at, Corrida.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery())
    resultado = await db.execute(
        update(Corrida)
        .where(Corrida.id == candidata,
               Corrida.estado == estados.PENDIENTE)
        .values(
            estado=estados.CALCULANDO,
            latido_en=ahora,
            intentos=Corrida.intentos + 1,
            iniciado_en=func.coalesce(Corrida.iniciado_en, ahora),
            reintentar_despues_de=None)
        .returning(Corrida.id)
        .execution_options(synchronize_session=False))
    corrida_id = resultado.scalars().first()
    await db.commit()
    return corrida_id


# --- Barrido y devolución ----------------------------------------------------


async def _transicionar(
    db, corrida_id: UUID, intentos: int, ahora: datetime, max_intentos: int,
    motivo: str,
) -> Optional[str]:
    """Aplica `decidir_estancada` a una corrida CALCULANDO. Guardado por el
    estado y por los `intentos` leídos: si otra réplica la reclamó entretanto
    no toca nada y devuelve `None`."""
    decision = decidir_estancada(intentos, max_intentos, ahora)
    evento: Dict[str, Any] = {
        "evento": "BARRIDA", "en": ahora.isoformat(), "motivo": motivo,
        "intentos": intentos, "resultado": decision.estado}
    valores: Dict[str, Any] = {"estado": decision.estado}
    if decision.estado == estados.PENDIENTE:
        valores["reintentar_despues_de"] = decision.reintentar_despues_de
    else:
        evento["codigo"] = decision.codigo
        valores["terminado_en"] = ahora
    valores["log"] = sv.con_evento(evento)
    resultado = await db.execute(
        update(Corrida)
        .where(Corrida.id == corrida_id,
               Corrida.estado == estados.CALCULANDO,
               Corrida.intentos == intentos)
        .values(**valores)
        .returning(Corrida.id)
        .execution_options(synchronize_session=False))
    return decision.estado if resultado.first() is not None else None


async def barrer_estancadas(
    db, ahora: datetime, *, timeout_min: int, max_intentos: int,
) -> List[Tuple[UUID, str]]:
    """Recupera las corridas CALCULANDO sin latido desde `timeout_min`.

    Devuelve `(corrida_id, estado nuevo)` de cada una que movió. Las filas
    bloqueadas por otra transacción (una réplica que sí está latiendo) se
    saltan con `SKIP LOCKED`.
    """
    limite = ahora - timedelta(minutes=timeout_min)
    filas = (await db.execute(
        select(Corrida.id, Corrida.intentos)
        .where(Corrida.estado == estados.CALCULANDO,
               Corrida.latido_en.isnot(None),
               Corrida.latido_en < limite)
        .with_for_update(skip_locked=True))).all()
    movidas = []
    for corrida_id, intentos in filas:
        estado = await _transicionar(
            db, corrida_id, intentos, ahora, max_intentos, "SIN_LATIDO")
        if estado is not None:
            movidas.append((corrida_id, estado))
    await db.commit()
    return movidas


async def _soltar(
    db, corrida_id: UUID, intentos: Optional[int], ahora: datetime,
    max_intentos: int,
) -> str:
    """Devuelve una corrida cuyo recorrido falló, como el barrido pero sin
    esperar el timeout. Si ni eso se puede escribir, la deja CALCULANDO para
    que el barrido la recupere cuando venza su latido."""
    if intentos is None:
        return estados.CALCULANDO
    try:
        await db.rollback()
        estado = await _transicionar(
            db, corrida_id, intentos, ahora, max_intentos, "ERROR")
        await db.commit()
    except Exception:  # noqa: BLE001 -- el barrido es el respaldo
        logger.exception("corrida %s: no se pudo devolver", corrida_id)
        return estados.CALCULANDO
    return estado or estados.CALCULANDO


async def _devolver_por_cierre(db, corrida_id: UUID) -> None:
    """Cierre del proceso: PENDIENTE de inmediato y sin gastar el intento
    (no fue culpa de la corrida). Mejor esfuerzo: nunca debe propagar."""
    try:
        await db.rollback()
        await db.execute(
            update(Corrida)
            .where(Corrida.id == corrida_id,
                   Corrida.estado == estados.CALCULANDO)
            .values(
                estado=estados.PENDIENTE,
                intentos=func.greatest(Corrida.intentos - 1, 0),
                reintentar_despues_de=None,
                latido_en=None)
            .execution_options(synchronize_session=False))
        await db.commit()
    except Exception:  # noqa: BLE001 -- el barrido es el respaldo
        logger.exception(
            "corrida %s: no se pudo devolver al cerrar", corrida_id)


# --- Recorrido ---------------------------------------------------------------


async def _con_reintentos(
    db, corrida: sv.CorridaRef, sucursal_id: UUID, ctx, motor,
    ejecutor: Optional[Executor], dormir: Callable,
) -> bool:
    """Procesa una sucursal reintentando las fallas transitorias de base:
    3 intentos con 1 s y 2 s de espera. Agotados, la sucursal queda FALLIDA
    con E-CORRIDA-099. `False` = la corrida se anuló (detener)."""
    for intento in range(1, INTENTOS_DBAPI + 1):
        try:
            return await sv.procesar_sucursal(
                db, corrida, sucursal_id, ctx, motor, ejecutor)
        except DBAPIError:
            logger.warning(
                "corrida %s: falla transitoria en la sucursal %s "
                "(intento %s de %s)", corrida.codigo, sucursal_id, intento,
                INTENTOS_DBAPI, exc_info=True)
            await db.rollback()
            if intento < INTENTOS_DBAPI:
                await dormir(ESPERAS_DBAPI[intento - 1])
    return await sv.marcar_fallida(
        db, corrida.id, sucursal_id, codigos.E_CORRIDA_INTERNO,
        codigos.mensaje(codigos.E_CORRIDA_INTERNO))


async def _recorrer(
    db, corrida, ejecutor: Optional[Executor], dormir: Callable,
) -> str:
    referencia = sv.CorridaRef(corrida.id, corrida.codigo)
    motor, ctx = await sv.preparar(db, corrida)
    for sucursal_id in await sv.pendientes(db, referencia.id):
        seguir = await _con_reintentos(
            db, referencia, sucursal_id, ctx, motor, ejecutor, dormir)
        await db.commit()
        if not seguir:
            return estados.ANULADA
    estado = await sv.finalizar_corrida(db, referencia.id)
    await db.commit()
    return estado


async def ejecutar_corrida(
    corrida_id: UUID, *, session_factory=None,
    ejecutor: Optional[Executor] = None, dormir: Callable = asyncio.sleep,
    reloj: Callable[[], datetime] = ahora_utc,
    max_intentos: Optional[int] = None,
) -> str:
    """Recorre una corrida YA reclamada (CALCULANDO) y devuelve su estado.

    Nunca propaga un error del recorrido: lo registra y devuelve la corrida
    (ver el docstring del módulo). Sí propaga `CancelledError`, después de
    devolverla a PENDIENTE.
    """
    fabrica = session_factory or motored_session_maker()
    limite = (
        settings.MOTORED_CORRIDA_MAX_INTENTOS
        if max_intentos is None else max_intentos)
    async with fabrica() as db:
        intentos = None
        try:
            corrida = await db.get(Corrida, corrida_id)
            intentos = corrida.intentos
            return await _recorrer(db, corrida, ejecutor, dormir)
        except asyncio.CancelledError:
            await _devolver_por_cierre(db, corrida_id)
            raise
        except Exception:  # noqa: BLE001 -- un recorrido roto no cae al loop
            logger.exception("corrida %s: el recorrido falló", corrida_id)
            return await _soltar(db, corrida_id, intentos, reloj(), limite)


async def reclamar_y_ejecutar(
    corrida_id: UUID, *, session_factory=None,
    ejecutor: Optional[Executor] = None, dormir: Callable = asyncio.sleep,
    reloj: Callable[[], datetime] = ahora_utc,
    max_intentos: Optional[int] = None,
) -> str:
    """Reclama la corrida indicada y la ejecuta hasta el final, en línea.
    Para el runner en línea (tests y scripts); E-CORRIDA-040 si no estaba
    PENDIENTE."""
    fabrica = session_factory or motored_session_maker()
    async with fabrica() as db:
        await sv.reclamar_corrida(db, corrida_id)
        await db.commit()
    return await ejecutar_corrida(
        corrida_id, session_factory=fabrica, ejecutor=ejecutor,
        dormir=dormir, reloj=reloj, max_intentos=max_intentos)
