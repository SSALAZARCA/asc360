"""
Motored: aviso anticipado antes de que un dato del pedido se venza.

El preflight de la corrida (`corridas/vigencia.py`) bloquea cuando un dato
(inventario, backorder, facturas de pedidos, ingresos de facturas) es más
viejo que su límite. Acá se avisa ANTES. El día de vencimiento es el último
día en que el dato todavía sirve: `fecha usada + límite`; el preflight
bloquea desde el día siguiente.

Las reglas de qué carga cuenta y con qué fecha son LAS DEL PREFLIGHT (se
reusa su elección de carga y su tabla de tipos, públicas en
`vigencia`) y los límites salen de los
mismos parámetros congelados por una corrida (`cargar_parametros_corrida`).
El inventario es de toda la red, no por sucursal: el preflight elige UNA
carga de inventario global, así que el aviso es por dato, no por sucursal.

Dos avisos por (dato, fecha de vencimiento), hora de Bogotá:
- VISPERA: el día anterior, desde las 16:30;
- DIA: el día de vencimiento, desde las 08:30.
Si el proceso estaba caído a esa hora, el aviso sale al volver (el mismo
día); nunca después de vencido ni dos veces: cada envío se reserva en
`aviso_antiguedad_enviado` (clave única) ANTES de mandarlo.

Este módulo no toca el motor ni el ciclo de vida de las corridas.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Awaitable, Callable, Dict, List, Mapping, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.motored.models.aviso_antiguedad_enviado import (
    AvisoAntiguedadEnviado,
)
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.corridas import parametros_corrida, vigencia
from app.motored.services.reloj import BOGOTA_OFFSET

logger = logging.getLogger("motored.avisos_antiguedad")

UMBRAL_VISPERA = "VISPERA"
UMBRAL_DIA = "DIA"
HORA_VISPERA = time(16, 30)
HORA_DIA = time(8, 30)
# Roles que reciben el aviso por Telegram (decisión del dueño: sólo COMPRAS).
ROLES_DESTINO = (MotoredRole.COMPRAS,)

Enviar = Callable[[int, str], Awaitable[bool]]


@dataclass(frozen=True)
class Vencimiento:
    tipo: str
    nombre: str
    fecha_carga: date
    fecha_vencimiento: date
    limite_dias: int


def calcular_vencimientos(
    hechos: vigencia.HechosVigencia,
    limites: Mapping[str, int],
    hoy: date,
) -> List[Vencimiento]:
    """Un `Vencimiento` por tipo con dato vigente hoy (con el límite de ese
    tipo). Un dato ausente o ya vencido no genera aviso: de eso se encarga
    el preflight."""
    vivas = [
        c for c in hechos.cargas if c.estado == vigencia.ESTADO_APLICADO]
    resultado = []
    for tipo, espec in vigencia.TIPOS_ANTIGUEDAD.items():
        _, fecha = vigencia.elegir_carga_vigente(vivas, tipo, hoy)
        if fecha is None:
            continue
        vence = fecha + timedelta(days=limites[tipo])
        if vence >= hoy:
            resultado.append(Vencimiento(
                tipo, espec[1], fecha, vence, limites[tipo]))
    return resultado


def avisos_del_dia(
    vencimientos: Sequence[Vencimiento], hoy: date,
) -> List[Tuple[Vencimiento, str]]:
    """Los que vencen hoy o mañana, con su etiqueta `hoy` / `manana`."""
    etiquetas = {hoy: "hoy", hoy + timedelta(days=1): "manana"}
    return [
        (v, etiquetas[v.fecha_vencimiento]) for v in vencimientos
        if v.fecha_vencimiento in etiquetas
    ]


def umbrales_a_enviar(
    vencimientos: Sequence[Vencimiento], ahora: datetime,
) -> List[Tuple[str, Vencimiento]]:
    """Qué avisos tocan ya, con `ahora` en hora de Bogotá."""
    hoy, hora = ahora.date(), ahora.timetz().replace(tzinfo=None)
    tocan = []
    for venc, etiqueta in avisos_del_dia(vencimientos, hoy):
        if etiqueta == "hoy" and hora >= HORA_DIA:
            tocan.append((UMBRAL_DIA, venc))
        elif etiqueta == "manana" and hora >= HORA_VISPERA:
            tocan.append((UMBRAL_VISPERA, venc))
    return tocan


def _dd_mm(fecha: date) -> str:
    return fecha.strftime("%d/%m")


def armar_mensaje(umbral: str, vencimientos: Sequence[Vencimiento]) -> str:
    """Texto en español para Telegram, un renglón por dato."""
    if umbral == UMBRAL_VISPERA:
        cabecera = "Motored: estos datos del pedido vencen mañana."
        cierre = "Súbalos antes de lanzar el pedido."
    else:
        cabecera = "Motored: estos datos del pedido vencen hoy."
        cierre = ("Si no los actualiza hoy, el pedido quedará bloqueado. "
                  "Súbalos antes de lanzarlo.")
    lineas = [
        f"- {v.nombre}: cargado el {_dd_mm(v.fecha_carga)}, "
        f"vence el {_dd_mm(v.fecha_vencimiento)}"
        for v in vencimientos
    ]
    return "\n".join([cabecera, *lineas, cierre])


# --- Lectura y reserva ----------------------------------------------------


async def leer_vencimientos(db, hoy: date) -> List[Vencimiento]:
    """Vencimientos de hoy con los mismos hechos y límites del preflight."""
    params = await parametros_corrida.cargar_parametros_corrida(db, hoy, ())
    hechos = await vigencia.cargar_hechos(db, hoy)
    return calcular_vencimientos(hechos, params.limites_antiguedad, hoy)


async def destinatarios(db) -> List[int]:
    """Chats de Telegram de los usuarios activos y aprobados del rol
    destino, sin repetir (varios usuarios pueden compartir un chat)."""
    filas = await db.execute(
        select(Usuario.telegram_id).where(
            Usuario.role.in_(ROLES_DESTINO),
            Usuario.activo.is_(True),
            Usuario.status == "approved",
            Usuario.telegram_id.is_not(None),
        ).distinct())
    return sorted(f for f in filas.scalars().all() if f)


async def reservar(
    db, tipo: str, umbral: str, vence: date, ahora: datetime,
) -> bool:
    """Reserva el envío con un INSERT atómico: `True` sólo para quien lo
    gana; reinicios y réplicas concurrentes reciben `False`."""
    resultado = await db.execute(
        insert(AvisoAntiguedadEnviado.__table__).values(
            id=uuid.uuid4(), dataset=tipo, umbral=umbral,
            fecha_vencimiento=vence, enviado_en=ahora,
        ).on_conflict_do_nothing(
            constraint="uq_aviso_antiguedad_dataset_umbral_vence",
        ).returning(AvisoAntiguedadEnviado.id))
    return resultado.first() is not None


async def liberar(db, tipo: str, umbral: str, vence: date) -> None:
    """Devuelve la reserva (el envío falló del todo) para reintentar."""
    await db.execute(delete(AvisoAntiguedadEnviado).where(
        AvisoAntiguedadEnviado.dataset == tipo,
        AvisoAntiguedadEnviado.umbral == umbral,
        AvisoAntiguedadEnviado.fecha_vencimiento == vence))


# --- Envío -----------------------------------------------------------------


async def _enviar_grupo(
    db, umbral: str, items: Sequence[Vencimiento], chats: Sequence[int],
    ahora: datetime, enviar: Enviar,
) -> int:
    """Reserva cada dato del grupo y manda UN mensaje con los reservados.
    Devuelve cuántos chats lo recibieron."""
    ganados = []
    for venc in items:
        if await reservar(
                db, venc.tipo, umbral, venc.fecha_vencimiento, ahora):
            ganados.append(venc)
    await db.commit()
    if not ganados:
        return 0
    texto = armar_mensaje(umbral, ganados)
    recibidos = 0
    for chat in chats:
        recibidos += 1 if await enviar(chat, texto) else 0
    if recibidos == 0:
        for venc in ganados:
            await liberar(db, venc.tipo, umbral, venc.fecha_vencimiento)
        await db.commit()
        logger.warning(
            "aviso de antigüedad %s: ningún envío llegó; se reintenta",
            umbral)
    return recibidos


async def procesar_avisos(db, ahora: datetime, enviar: Enviar) -> int:
    """Un tick: manda los avisos que tocan y aún no salieron. Devuelve el
    total de mensajes entregados. `ahora` debe traer zona horaria."""
    local = ahora.astimezone(BOGOTA_OFFSET)
    if local.timetz().replace(tzinfo=None) < HORA_DIA:
        return 0
    vencimientos = await leer_vencimientos(db, local.date())
    tocan = umbrales_a_enviar(vencimientos, local)
    if not tocan:
        return 0
    chats = await destinatarios(db)
    if not chats:
        return 0
    grupos: Dict[str, List[Vencimiento]] = {}
    for umbral, venc in tocan:
        grupos.setdefault(umbral, []).append(venc)
    entregados = 0
    for umbral, items in grupos.items():
        entregados += await _enviar_grupo(
            db, umbral, items, chats, ahora, enviar)
    return entregados
