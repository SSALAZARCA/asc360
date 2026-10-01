"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B1 y B3a,
ADR-1, decisión F4-14): el pedido de cada tienda de una corrida.

La corrida es sólo el lote de cálculo; cada `(corrida, sucursal)` con pedido
tiene su propio estado en `corrida_sucursal.estado_pedido`. Este módulo
reúne las reglas del ciclo de vida por tienda:

- `iniciar_pedidos` (B1) deja BORRADOR el pedido de las tiendas OK de una
  corrida real recién calculada.
- `cerrar_todas` / `cerrar_tienda` (B3a): BORRADOR -> CERRADO, de una tienda
  o de varias a la vez (todo o nada). Toma las cargas vinculadas `FOR SHARE`,
  la corrida `FOR SHARE` y las tiendas `FOR UPDATE` en orden de
  `sucursal_id` (cargas -> corrida -> tienda, el orden global de
  `bloqueos.py`); un cierre espera a las ediciones en vuelo de esa tienda y
  las ve cerradas después. Escribe un evento CERRADO por tienda.
- `reabrir_tienda` (B3a): CERRADO -> BORRADOR con un motivo obligatorio y un
  evento REABIERTO; nunca toca a otra tienda. Enviar es de `envio.py` (B3b).
- `resumen_pedidos`: cuántas tiendas OK están en cada estado, para la lista.

Orden de los chequeos (R3 de las tareas): corrida y tienda (404), escenario
(042, con la acción), cálculo (040), invalidada o carga anulada (041, no al
reabrir), tienda sin pedido (065) y estado del pedido (064 al cerrar; 045,
044 y después el motivo 046 al reabrir).

Ningún commit acá: la transacción es del llamador.
"""
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, insert, select, update

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.services.corridas import (
    bloqueos,
    codigos,
    envio,
    estados,
)
from app.motored.services.corridas.codigos import ErrorCorrida

ACCION_CERRAR = "cerrar"
ACCION_REABRIR = "reabrir"
EVENTO_CERRADO = "CERRADO"
EVENTO_REABIERTO = "REABIERTO"
MAX_MOTIVO = 500


class ResultadoLote(NamedTuple):
    """Lo que dejó un cierre: la corrida, las tiendas que pasaron a CERRADO
    y cuántas OK ya estaban cerradas o enviadas (sólo en el lote sin lista)."""

    corrida: Any
    cerradas: List[UUID]
    ya_cerradas: int


async def iniciar_pedidos(db, corrida_id: UUID) -> None:
    """NULL -> BORRADOR en las tiendas OK de la corrida, salvo escenario.

    Una tienda FALLIDA u OMITIDA no tiene pedido (queda NULL) y un
    escenario nunca lo tiene (es sólo de prueba). Se corre en la misma
    transacción que cierra el cálculo (CALCULANDO -> BORRADOR)."""
    es_escenario = select(Corrida.id).where(
        Corrida.id == corrida_id, Corrida.es_escenario.is_(True))
    await db.execute(
        update(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida_id,
               CorridaSucursal.estado == estados.SUC_OK,
               ~es_escenario.exists())
        .values(estado_pedido=estados.PEDIDO_BORRADOR)
        .execution_options(synchronize_session=False))


# --- Cerrar -----------------------------------------------------------------


def _no_cerrable(tienda: Any, nombre: str) -> ErrorCorrida:
    """El rechazo de una tienda NOMBRADA que no se puede cerrar (065 si no
    tiene pedido; 064 si no está en BORRADOR)."""
    detalle = {"sucursal_id": str(tienda.sucursal_id), "tienda": nombre,
               "estado_pedido": tienda.estado_pedido}
    if tienda.estado_pedido is None:
        return ErrorCorrida(
            codigos.E_CORRIDA_SIN_PEDIDO,
            f"{nombre}: {codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO)}",
            detalle)
    texto = f"el pedido de {nombre} está {tienda.estado_pedido}"
    return ErrorCorrida(
        codigos.E_CORRIDA_CERRAR_NO_BORRADOR,
        codigos.mensaje(codigos.E_CORRIDA_CERRAR_NO_BORRADOR, detalle=texto),
        detalle)


def _elegir_a_cerrar(filas: list, con_lista: bool) -> List[Any]:
    """Las tiendas a cerrar. Con lista, todas deben estar en BORRADOR (la
    primera que no, en orden de `sucursal_id`, rechaza el lote). Sin lista,
    las que estén en BORRADOR; si ninguna lo está, 064."""
    if con_lista:
        for tienda, nombre in filas:
            if tienda.estado_pedido != estados.PEDIDO_BORRADOR:
                raise _no_cerrable(tienda, nombre)
        return [tienda for tienda, _ in filas]
    abiertas = [
        t for t, _ in filas if t.estado_pedido == estados.PEDIDO_BORRADOR]
    if not abiertas:
        raise ErrorCorrida(
            codigos.E_CORRIDA_CERRAR_NO_BORRADOR,
            codigos.mensaje(
                codigos.E_CORRIDA_CERRAR_NO_BORRADOR,
                detalle="ninguna tienda tiene un pedido en BORRADOR"))
    return abiertas


async def _cerrar(
    db, corrida_id: UUID, usuario_id: UUID,
    sucursal_ids: Optional[Sequence[UUID]],
):
    anuladas = await bloqueos.cargas_anuladas(db, corrida_id)
    corrida = await bloqueos.bloquear_corrida(
        db, corrida_id, exclusivo=False)
    filas = await bloqueos.bloquear_tiendas(db, corrida_id, sucursal_ids)
    bloqueos.exigir_operable(corrida, ACCION_CERRAR)
    if anuladas:
        raise ErrorCorrida(
            codigos.E_CORRIDA_INVALIDADA,
            codigos.mensaje(codigos.E_CORRIDA_INVALIDADA))
    if sucursal_ids is not None:
        _exigir_con_pedido(filas)
    elegidas = _elegir_a_cerrar(filas, sucursal_ids is not None)
    for tienda in elegidas:
        tienda.estado_pedido = estados.PEDIDO_CERRADO
    await db.flush()
    await _escribir_eventos(
        db, corrida_id, EVENTO_CERRADO, [t.sucursal_id for t in elegidas],
        usuario_id)
    return corrida, elegidas, len(filas) - len(elegidas)


def _exigir_con_pedido(filas: list) -> None:
    """065 antes que 064: una tienda sin pedido se nombra aunque otra del
    lote ya esté cerrada."""
    for tienda, nombre in filas:
        if tienda.estado_pedido is None:
            raise _no_cerrable(tienda, nombre)


async def _escribir_eventos(
    db, corrida_id: UUID, evento: str, sucursal_ids: Iterable[UUID],
    usuario_id: UUID, *, motivo: Optional[str] = None,
) -> None:
    """Una fila de `pedido_evento` por tienda (el padre ya se actualizó)."""
    await db.execute(insert(PedidoEvento).values([
        {"corrida_id": corrida_id, "sucursal_id": sucursal_id,
         "evento": evento, "motivo": motivo, "usuario_id": usuario_id}
        for sucursal_id in sucursal_ids]))


async def cerrar_todas(
    db, corrida_id: UUID, usuario_id: UUID,
    sucursal_ids: Optional[Sequence[UUID]] = None,
) -> ResultadoLote:
    """BORRADOR -> CERRADO en varias tiendas, todo o nada.

    Sin `sucursal_ids`, todas las tiendas OK que sigan en BORRADOR (las ya
    cerradas o enviadas no son error: se cuentan en `ya_cerradas`); si
    ninguna lo está, 064. Con `sucursal_ids`, exactamente esas, y la primera
    que no se pueda cerrar rechaza el lote nombrándola (065 o 064).
    `LookupError` si la corrida o una tienda nombrada no existe."""
    corrida, elegidas, ya = await _cerrar(
        db, corrida_id, usuario_id, sucursal_ids)
    return ResultadoLote(
        corrida, [t.sucursal_id for t in elegidas],
        ya if sucursal_ids is None else 0)


async def cerrar_tienda(
    db, corrida_id: UUID, sucursal_id: UUID, usuario_id: UUID,
):
    """BORRADOR -> CERRADO en UNA tienda; devuelve su `corrida_sucursal`."""
    _, elegidas, _ = await _cerrar(
        db, corrida_id, usuario_id, [sucursal_id])
    return elegidas[0]


# --- Reabrir ----------------------------------------------------------------


async def _exigir_cerrado(db, corrida_id: UUID, tienda: Any) -> None:
    if tienda.estado_pedido is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_SIN_PEDIDO,
            codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO))
    if tienda.estado_pedido == estados.PEDIDO_ENVIADO:
        numero = await envio.numero_enviado(
            db, corrida_id, tienda.sucursal_id)
        raise ErrorCorrida(
            codigos.E_CORRIDA_REABRIR_ENVIADO,
            codigos.mensaje(
                codigos.E_CORRIDA_REABRIR_ENVIADO, numero=numero),
            {"numero_pedido_proveedor": numero})
    if tienda.estado_pedido != estados.PEDIDO_CERRADO:
        raise ErrorCorrida(
            codigos.E_CORRIDA_REABRIR_BORRADOR,
            codigos.mensaje(codigos.E_CORRIDA_REABRIR_BORRADOR))


def _motivo_valido(motivo: Any) -> str:
    """El motivo recortado, de 1 a 500 caracteres; si no, 046."""
    limpio = motivo.strip() if isinstance(motivo, str) else ""
    if not 1 <= len(limpio) <= MAX_MOTIVO:
        raise ErrorCorrida(
            codigos.E_CORRIDA_REABRIR_MOTIVO,
            codigos.mensaje(codigos.E_CORRIDA_REABRIR_MOTIVO))
    return limpio


async def reabrir_tienda(
    db, corrida_id: UUID, sucursal_id: UUID, usuario_id: UUID, motivo: Any,
):
    """CERRADO -> BORRADOR en UNA tienda, con motivo y evento REABIERTO.

    Bloquea la corrida `FOR SHARE` y después la tienda `FOR UPDATE`; no mira
    otras tiendas, así que un pedido enviado en otra tienda sigue intacto.
    Una corrida invalidada se puede reabrir (devolver a BORRADOR no es
    riesgoso). `LookupError` si la corrida o la tienda no existen."""
    corrida = await bloqueos.bloquear_corrida(
        db, corrida_id, exclusivo=False)
    tienda = await bloqueos.bloquear_tienda(
        db, corrida_id, sucursal_id, exclusivo=True)
    bloqueos.exigir_operable(corrida, ACCION_REABRIR, permite_invalidada=True)
    await _exigir_cerrado(db, corrida_id, tienda)
    limpio = _motivo_valido(motivo)
    tienda.estado_pedido = estados.PEDIDO_BORRADOR
    await db.flush()
    await _escribir_eventos(
        db, corrida_id, EVENTO_REABIERTO, [sucursal_id], usuario_id,
        motivo=limpio)
    return tienda


# --- Resumen ----------------------------------------------------------------

_CLAVE_DE_ESTADO = {
    estados.PEDIDO_BORRADOR: "borrador",
    estados.PEDIDO_CERRADO: "cerrados",
    estados.PEDIDO_ENVIADO: "enviados",
}


async def resumen_pedidos(
    db, corrida_ids: Sequence[UUID], alcance: Optional[frozenset] = None,
) -> Dict[UUID, Dict[str, int]]:
    """`{corrida_id: {total, borrador, cerrados, enviados}}` sobre las
    tiendas OK (las visibles, con `alcance`), en UNA consulta agrupada. Una
    corrida sin tiendas OK no aparece."""
    ids = list(corrida_ids)
    if not ids:
        return {}
    cs = CorridaSucursal
    condiciones = [cs.corrida_id.in_(ids), cs.estado == estados.SUC_OK]
    if alcance is not None:
        condiciones.append(cs.sucursal_id.in_(sorted(alcance)))
    filas = await db.execute(
        select(cs.corrida_id, cs.estado_pedido, func.count())
        .where(*condiciones)
        .group_by(cs.corrida_id, cs.estado_pedido))
    resumen: Dict[UUID, Dict[str, int]] = {}
    for corrida_id, estado, cuantas in filas.all():
        fila = resumen.setdefault(corrida_id, {
            "total": 0, "borrador": 0, "cerrados": 0, "enviados": 0})
        fila["total"] += cuantas
        clave = _CLAVE_DE_ESTADO.get(estado)
        if clave is not None:
            fila[clave] += cuantas
    return resumen
