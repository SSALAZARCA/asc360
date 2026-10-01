"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B3b,
ADR-1, ADR-11, decisiones F4-11, F4-13 y F4-15): marcar como enviado el
pedido de cada tienda y corregir después su número de orden.

- `enviar_lote` / `enviar_tienda`: CERRADO -> ENVIADO con el número de orden
  del proveedor y la fecha de envío de CADA tienda (F4-11). Todo o nada: la
  primera tienda que no se pueda enviar rechaza el lote nombrándola. Toma la
  corrida `FOR SHARE` y las tiendas `FOR UPDATE` en orden de `sucursal_id`
  (el orden global de `bloqueos.py`). Escribe la fila `corrida_envio` (en un
  savepoint) y un evento ENVIADO por tienda: `ENVIADO <=> existe la fila`.
- F4-13, un solo envío por semana: si la tienda ya tiene un envío para la
  misma `fecha_corte` y proveedor en otra corrida, E-CORRIDA-050 nombra esa
  corrida y su número. La UNIQUE `uq_corrida_envio_corte_sucursal` es la
  barrera real; la consulta previa sólo da el mensaje, y si otra corrida
  gana la carrera la `IntegrityError` se traduce al mismo 050.
- `corregir_numero` (F4-15): cambia el número de orden de una tienda ya
  ENVIADA, en la misma fila, y deja un evento ENVIO_CORREGIDO con
  `{antes, despues}`. El mismo número es un no-op. La fecha de envío no se
  corrige y una tienda enviada nunca se des-envía ni se reabre.

Orden de los chequeos (R3 de las tareas): corrida y tienda (404), escenario
(042, con la acción), cálculo (040), invalidada (041, no al corregir), tienda
sin pedido (065), estado del pedido (049 o 047 al enviar; 067 al corregir),
datos (048), envío duplicado (050) y nada que pedir (056, A1).

Ningún commit acá: la transacción es del llamador.
"""
import datetime
from datetime import timezone
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_envio import CorridaEnvio
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.services.corridas import bloqueos, codigos, estados
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.reloj import hoy_bogota

ACCION_ENVIAR = "enviar"
ACCION_CORREGIR = "corregir el envío"
EVENTO_ENVIADO = "ENVIADO"
EVENTO_CORREGIDO = "ENVIO_CORREGIDO"
MAX_NUMERO = 50
UNIQUE_ENVIO = "uq_corrida_envio_corte_sucursal"


class PedidoEnviar(NamedTuple):
    """Lo que se pide enviar de una tienda; los valores llegan sin validar
    (la regla 048 la aplica el servicio, después de los chequeos de estado)."""

    sucursal_id: UUID
    numero: Any
    fecha_envio: Any


class ResultadoEnvios(NamedTuple):
    """La corrida y las filas `corrida_envio` que dejó el lote."""

    corrida: Any
    envios: List[Any]


class ResultadoCorreccion(NamedTuple):
    """La tienda, su fila `corrida_envio` y si el número cambió."""

    tienda: Any
    envio: Any
    cambio: bool


async def numero_enviado(db, corrida_id: UUID, sucursal_id: UUID) -> str:
    """El número de orden con que se envió la tienda ("sin número" si no
    hay fila, que no debería pasar)."""
    resultado = await db.execute(
        select(CorridaEnvio.numero_pedido_proveedor).where(
            CorridaEnvio.corrida_id == corrida_id,
            CorridaEnvio.sucursal_id == sucursal_id))
    return resultado.scalars().first() or "sin número"


def _invalido(texto: str, nombre: Optional[str] = None) -> ErrorCorrida:
    """048: el dato de envío no es válido (nombra la tienda en un lote)."""
    detalle = texto if nombre is None else f"{nombre}: {texto}"
    return ErrorCorrida(
        codigos.E_CORRIDA_ENVIO_INVALIDO,
        codigos.mensaje(codigos.E_CORRIDA_ENVIO_INVALIDO, detalle=detalle))


def _numero_valido(numero: Any, nombre: Optional[str] = None) -> str:
    """El número recortado, de 1 a 50 caracteres; si no, 048."""
    limpio = numero.strip() if isinstance(numero, str) else ""
    if not 1 <= len(limpio) <= MAX_NUMERO:
        raise _invalido(
            f"el número de orden debe tener entre 1 y {MAX_NUMERO} "
            "caracteres", nombre)
    return limpio


def _como_fecha(valor: Any) -> Optional[datetime.date]:
    """Una fecha de calendario (`date` o `YYYY-MM-DD`); `None` si no lo es.
    Un `datetime` o un número no son una fecha de envío."""
    if isinstance(valor, datetime.datetime):
        return None
    if isinstance(valor, datetime.date):
        return valor
    if isinstance(valor, str):
        try:
            return datetime.date.fromisoformat(valor.strip())
        except ValueError:
            return None
    return None


def _fecha_valida(
    valor: Any, fecha_corte: datetime.date, nombre: Optional[str] = None,
) -> datetime.date:
    """Entre la fecha de corte y hoy (Bogotá), inclusive; si no, 048."""
    fecha = _como_fecha(valor)
    if fecha is None or not fecha_corte <= fecha <= hoy_bogota():
        raise _invalido(
            "la fecha de envío debe estar entre la fecha de corte "
            f"({fecha_corte.isoformat()}) y hoy", nombre)
    return fecha


# --- Enviar -----------------------------------------------------------------


def _exigir_con_pedido(filas: list) -> None:
    """065 antes que 049/047: una tienda sin pedido se nombra aunque otra del
    lote tenga otro problema."""
    for tienda, nombre in filas:
        if tienda.estado_pedido is None:
            raise ErrorCorrida(
                codigos.E_CORRIDA_SIN_PEDIDO,
                f"{nombre}: {codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO)}",
                {"sucursal_id": str(tienda.sucursal_id), "tienda": nombre})


async def _exigir_cerradas(db, corrida_id: UUID, filas: list) -> None:
    """Cada tienda debe estar CERRADO: ENVIADO es 049 (con su número) y
    BORRADOR 047; la primera, en orden de `sucursal_id`, rechaza el lote."""
    _exigir_con_pedido(filas)
    for tienda, nombre in filas:
        estado = tienda.estado_pedido
        if estado == estados.PEDIDO_ENVIADO:
            numero = await numero_enviado(db, corrida_id, tienda.sucursal_id)
            raise ErrorCorrida(
                codigos.E_CORRIDA_ENVIAR_YA_ENVIADO,
                codigos.mensaje(
                    codigos.E_CORRIDA_ENVIAR_YA_ENVIADO,
                    tienda=nombre, numero=numero),
                {"tienda": nombre, "numero_pedido_proveedor": numero})
        if estado != estados.PEDIDO_CERRADO:
            raise ErrorCorrida(
                codigos.E_CORRIDA_ENVIAR_NO_CERRADO,
                codigos.mensaje(
                    codigos.E_CORRIDA_ENVIAR_NO_CERRADO,
                    tienda=nombre, estado=estado),
                {"tienda": nombre, "estado_pedido": estado})


def _duplicado(
    nombre: str, sucursal_id: UUID, rival: Any,
) -> ErrorCorrida:
    """050: el envío de la misma semana en otra corrida, con su número."""
    _, codigo, numero = rival
    return ErrorCorrida(
        codigos.E_CORRIDA_ENVIO_DUPLICADO,
        codigos.mensaje(
            codigos.E_CORRIDA_ENVIO_DUPLICADO, tienda=nombre,
            corrida=codigo, numero=numero),
        {"sucursal_id": str(sucursal_id), "tienda": nombre,
         "corrida": codigo, "numero_pedido_proveedor": numero})


async def _rivales(
    db, corrida: Any, sucursal_ids: Sequence[UUID],
) -> Dict[UUID, Any]:
    """`{sucursal_id: (sucursal_id, codigo, numero)}` de los envíos de las
    tiendas para el mismo proveedor y corte en OTRA corrida."""
    ce = CorridaEnvio
    filas = await db.execute(
        select(ce.sucursal_id, Corrida.codigo, ce.numero_pedido_proveedor)
        .join(Corrida, Corrida.id == ce.corrida_id)
        .where(ce.proveedor_id == corrida.proveedor_id,
               ce.fecha_corte == corrida.fecha_corte,
               ce.sucursal_id.in_(list(sucursal_ids)),
               ce.corrida_id != corrida.id))
    return {fila[0]: tuple(fila) for fila in filas.all()}


async def _exigir_sin_rival(db, corrida: Any, filas: list) -> None:
    rivales = await _rivales(db, corrida, [t.sucursal_id for t, _ in filas])
    for tienda, nombre in filas:
        if tienda.sucursal_id in rivales:
            raise _duplicado(
                nombre, tienda.sucursal_id, rivales[tienda.sucursal_id])


async def _exigir_con_cantidad(db, corrida_id: UUID, filas: list) -> None:
    """056 (A1): una tienda con SUM(pedido_final) = 0 se cierra pero no se
    envía. Una sola consulta agrupada para todo el lote."""
    cl = CorridaLinea
    sumas = await db.execute(
        select(cl.sucursal_id, func.coalesce(func.sum(cl.pedido_final), 0))
        .where(cl.corrida_id == corrida_id,
               cl.sucursal_id.in_([t.sucursal_id for t, _ in filas]),
               cl.motivo_exclusion.is_(None))
        .group_by(cl.sucursal_id))
    total = {fila[0]: Decimal(fila[1]) for fila in sumas.all()}
    for tienda, nombre in filas:
        if total.get(tienda.sucursal_id, Decimal(0)) <= 0:
            raise ErrorCorrida(
                codigos.E_CORRIDA_NADA_QUE_ENVIAR,
                codigos.mensaje(
                    codigos.E_CORRIDA_NADA_QUE_ENVIAR, tienda=nombre),
                {"sucursal_id": str(tienda.sucursal_id), "tienda": nombre})


async def _insertar_envio(
    db, corrida: Any, tienda: Any, nombre: str, fila: Any,
) -> None:
    """La fila `corrida_envio` en un savepoint: si la UNIQUE salta porque
    otra corrida envió a la vez, se relee al rival y se responde 050."""
    try:
        async with db.begin_nested():
            db.add(fila)
            await db.flush()
    except IntegrityError as error:
        if UNIQUE_ENVIO not in str(error):
            raise
        rivales = await _rivales(db, corrida, [tienda.sucursal_id])
        if tienda.sucursal_id not in rivales:
            raise
        raise _duplicado(
            nombre, tienda.sucursal_id, rivales[tienda.sucursal_id]
        ) from error


async def _escribir_eventos(db, corrida_id: UUID, eventos: list) -> None:
    """Una fila de `pedido_evento` por entrada `(sucursal_id, evento,
    detalle, usuario_id)`; el padre ya se actualizó."""
    await db.execute(insert(PedidoEvento).values([
        {"corrida_id": corrida_id, "sucursal_id": sucursal_id,
         "evento": evento, "detalle": detalle, "usuario_id": usuario_id}
        for sucursal_id, evento, detalle, usuario_id in eventos]))


def _validar(
    pedidos: Sequence[PedidoEnviar], filas: list, corrida: Any,
) -> list:
    """`[(tienda, nombre, numero, fecha)]` con los datos de cada tienda
    validados (048), en el orden de `filas`."""
    por_id = {p.sucursal_id: p for p in pedidos}
    validados = []
    for tienda, nombre in filas:
        pedido = por_id[tienda.sucursal_id]
        nombre_048 = nombre if len(filas) > 1 else None
        numero = _numero_valido(pedido.numero, nombre_048)
        fecha = _fecha_valida(
            pedido.fecha_envio, corrida.fecha_corte, nombre_048)
        validados.append((tienda, nombre, numero, fecha))
    return validados


async def _escribir(
    db, corrida: Any, validados: list, usuario_id: UUID,
) -> List[Any]:
    """CERRADO -> ENVIADO en cada tienda (el padre primero), la fila
    `corrida_envio` de cada una y sus eventos."""
    ahora = datetime.datetime.now(timezone.utc)
    for tienda, _, _, _ in validados:
        tienda.estado_pedido = estados.PEDIDO_ENVIADO
    await db.flush()
    envios = []
    for tienda, nombre, numero, fecha in validados:
        fila = CorridaEnvio(
            corrida_id=corrida.id, sucursal_id=tienda.sucursal_id,
            proveedor_id=corrida.proveedor_id,
            fecha_corte=corrida.fecha_corte, numero_pedido_proveedor=numero,
            fecha_envio=fecha, enviada_por=usuario_id, enviada_en=ahora)
        await _insertar_envio(db, corrida, tienda, nombre, fila)
        envios.append(fila)
    await _escribir_eventos(db, corrida.id, [
        (tienda.sucursal_id, EVENTO_ENVIADO,
         {"numero": numero, "fecha_envio": fecha.isoformat()}, usuario_id)
        for tienda, _, numero, fecha in validados])
    return envios


async def enviar_lote(
    db, corrida_id: UUID, pedidos: Sequence[PedidoEnviar], usuario_id: UUID,
) -> ResultadoEnvios:
    """CERRADO -> ENVIADO en varias tiendas, todo o nada.

    Cada tienda lleva su número de orden y su fecha de envío; la primera que
    no se pueda enviar rechaza el lote nombrándola (065, 049, 047, 048, 050
    o 056). `LookupError` si la corrida o una tienda no existe."""
    ids = [pedido.sucursal_id for pedido in pedidos]
    if len(set(ids)) != len(ids):
        raise _invalido("una tienda aparece más de una vez")
    corrida = await bloqueos.bloquear_corrida(
        db, corrida_id, exclusivo=False)
    filas = await bloqueos.bloquear_tiendas(db, corrida_id, ids)
    bloqueos.exigir_operable(corrida, ACCION_ENVIAR)
    await _exigir_cerradas(db, corrida_id, filas)
    validados = _validar(pedidos, filas, corrida)
    await _exigir_sin_rival(db, corrida, filas)
    await _exigir_con_cantidad(db, corrida_id, filas)
    envios = await _escribir(db, corrida, validados, usuario_id)
    return ResultadoEnvios(corrida, envios)


async def enviar_tienda(
    db, corrida_id: UUID, sucursal_id: UUID, numero: Any, fecha_envio: Any,
    usuario_id: UUID,
) -> ResultadoEnvios:
    """CERRADO -> ENVIADO en UNA tienda (un lote de una)."""
    return await enviar_lote(
        db, corrida_id, [PedidoEnviar(sucursal_id, numero, fecha_envio)],
        usuario_id)


# --- Corregir el número (F4-15) ----------------------------------------------


async def _bloquear_envio(db, corrida_id: UUID, sucursal_id: UUID) -> Any:
    resultado = await db.execute(
        select(CorridaEnvio)
        .where(CorridaEnvio.corrida_id == corrida_id,
               CorridaEnvio.sucursal_id == sucursal_id)
        .with_for_update()
        .execution_options(populate_existing=True))
    fila = resultado.scalars().first()
    if fila is None:
        raise RuntimeError(
            f"la tienda {sucursal_id} está ENVIADO sin fila corrida_envio")
    return fila


def _exigir_enviada(tienda: Any) -> None:
    """065 sin pedido; 067 si el pedido no está ENVIADO."""
    if tienda.estado_pedido is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_SIN_PEDIDO,
            codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO))
    if tienda.estado_pedido != estados.PEDIDO_ENVIADO:
        raise ErrorCorrida(
            codigos.E_CORRIDA_CORREGIR_NO_ENVIADO,
            codigos.mensaje(
                codigos.E_CORRIDA_CORREGIR_NO_ENVIADO,
                estado=tienda.estado_pedido))


async def corregir_numero(
    db, corrida_id: UUID, sucursal_id: UUID, numero: Any, usuario_id: UUID,
) -> ResultadoCorreccion:
    """Cambia el número de orden de una tienda ENVIADO (F4-15).

    Bloquea la corrida `FOR SHARE`, la tienda y su fila de envío `FOR
    UPDATE`. Una corrida invalidada se puede corregir (es sólo auditoría).
    El mismo número no escribe nada y devuelve `cambio = False`.
    `LookupError` si la corrida o la tienda no existen."""
    corrida = await bloqueos.bloquear_corrida(
        db, corrida_id, exclusivo=False)
    tienda = await bloqueos.bloquear_tienda(
        db, corrida_id, sucursal_id, exclusivo=True)
    bloqueos.exigir_operable(corrida, ACCION_CORREGIR, permite_invalidada=True)
    _exigir_enviada(tienda)
    nuevo = _numero_valido(numero)
    fila = await _bloquear_envio(db, corrida_id, sucursal_id)
    antes = fila.numero_pedido_proveedor
    if nuevo == antes:
        return ResultadoCorreccion(tienda, fila, False)
    fila.numero_pedido_proveedor = nuevo
    await db.flush()
    await _escribir_eventos(db, corrida_id, [
        (sucursal_id, EVENTO_CORREGIDO,
         {"antes": antes, "despues": nuevo}, usuario_id)])
    return ResultadoCorreccion(tienda, fila, True)
