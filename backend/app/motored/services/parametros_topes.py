"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5a,
ADR-6, decisión F4-7): lectura y escritura del tope de presupuesto.

El interruptor `modo_tope_presupuesto` (global) y el tope por tienda
`presupuesto_maximo_pedido` viven en `parametro_metodologia`, en el grupo
PEDIDO: nunca entran al snapshot de la corrida. Un tope se guarda como texto
decimal exacto (o JSON `null` = "sin tope"); cada cambio es una fila nueva.

Los servicios no hacen commit: lo hace el router.
"""
import uuid
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select

from app.motored.models.sucursal import Sucursal
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.corridas import codigos

MAXIMO_TOPES = 200


def _invalido(detalle: str) -> pc.ErrorParametro:
    codigo = codigos.E_PARAM_VALOR_INVALIDO
    return pc.ErrorParametro(codigo, codigos.mensaje(
        codigo, clave=pc.CLAVE_TOPE_PEDIDO, detalle=detalle))


def _fraccion(valor: Any) -> Optional[Fraction]:
    """El tope tipado de un valor guardado; nulo si no hay tope o si la
    fila guardada ya no cumple la regla (una lectura jamás falla)."""
    try:
        return pc.parsear(pc.CLAVE_TOPE_PEDIDO, valor)
    except pc.ErrorParametro:
        return None


def _decimal(valor: Any) -> Optional[Decimal]:
    """El tope como `Decimal` exacto (sin pasar por fracciones, que sólo
    sirven para comparar); nulo si no hay tope o la fila no es válida."""
    if _fraccion(valor) is None:
        return None
    return Decimal(str(valor).strip())


def tope_vigente(
    vigentes: "parametros.VigentesMotor", sucursal_id: uuid.UUID,
) -> parametros.ResolucionParametro:
    """El tope de UNA tienda. Sólo cuenta una fila de esa tienda: nunca una
    global ni la de otra (sin fila el valor es `None`, "sin tope")."""
    resolucion = vigentes.resolver(pc.CLAVE_TOPE_PEDIDO, sucursal_id)
    if resolucion.fuente != parametros.FUENTE_SUCURSAL:
        return parametros.ResolucionParametro(
            None, parametros.FUENTE_DEFAULT, None, None)
    return resolucion


def _item(vigentes, sucursal_id, nombre) -> dict:
    resolucion = tope_vigente(vigentes, sucursal_id)
    return {
        "sucursal_id": sucursal_id,
        "nombre": nombre,
        "valor": _decimal(resolucion.valor),
        "vigente_desde": resolucion.vigente_desde,
    }


async def _vigentes(db, claves: Iterable[str], en_fecha: date):
    return await parametros.obtener_vigentes_motor(db, claves, en_fecha)


async def leer_topes(db, en_fecha: date) -> dict:
    """El interruptor y el tope de cada tienda activa, por nombre."""
    vigentes = await _vigentes(
        db, [pc.CLAVE_MODO_TOPE, pc.CLAVE_TOPE_PEDIDO], en_fecha)
    modo = vigentes.resolver(pc.CLAVE_MODO_TOPE)
    resultado = await db.execute(
        select(Sucursal.id, Sucursal.nombre)
        .where(Sucursal.activa.is_(True))
        .order_by(Sucursal.nombre)
    )
    return {
        "modo_activo": modo.valor is True,
        "modo_vigente_desde": modo.vigente_desde,
        "topes": [_item(vigentes, sid, nombre)
                  for sid, nombre in resultado.all()],
    }


def _validar_entradas(entradas: Sequence[Any]) -> None:
    """Largo 1..200, sin tienda repetida y cada valor válido; E-PARAM-002.
    Se valida TODO antes de tocar la base: o entra todo o nada."""
    if not 1 <= len(entradas) <= MAXIMO_TOPES:
        raise _invalido(f"se esperaban entre 1 y {MAXIMO_TOPES} topes")
    vistas = set()
    for entrada in entradas:
        if entrada.sucursal_id in vistas:
            raise _invalido(f"la sucursal {entrada.sucursal_id} se repite")
        vistas.add(entrada.sucursal_id)
        try:
            pc.validar_escritura(
                pc.CLAVE_TOPE_PEDIDO, entrada.valor, entrada.sucursal_id)
        except pc.ErrorParametro as error:
            raise pc.ErrorParametro(
                error.codigo,
                f"{error.mensaje} (sucursal {entrada.sucursal_id})",
            ) from error


async def _exigir_sucursales(db, ids: List[uuid.UUID]) -> None:
    resultado = await db.execute(
        select(Sucursal.id).where(Sucursal.id.in_(ids)))
    faltan = set(ids) - set(resultado.scalars().all())
    if faltan:
        nombres = ", ".join(sorted(str(x) for x in faltan))
        raise _invalido(f"la sucursal no existe ({nombres})")


def _texto(valor: Any) -> Optional[str]:
    """Texto decimal exacto que se guarda (`None` = sin tope)."""
    decimal = _decimal(valor)
    return None if decimal is None else format(decimal, "f")


async def guardar_topes(
    db, entradas: Sequence[Any], usuario_id: uuid.UUID, en_fecha: date,
) -> Dict[str, List[uuid.UUID]]:
    """Una versión nueva por cada tienda cuyo tope CAMBIA, en la misma
    transacción del llamador; las que ya tienen ese valor no se tocan."""
    _validar_entradas(entradas)
    await _exigir_sucursales(db, [e.sucursal_id for e in entradas])
    vigentes = await _vigentes(db, [pc.CLAVE_TOPE_PEDIDO], en_fecha)
    resultado: Dict[str, List[uuid.UUID]] = {
        "actualizados": [], "sin_cambios": []}
    for entrada in entradas:
        nuevo = _fraccion(entrada.valor)
        actual = _fraccion(tope_vigente(vigentes, entrada.sucursal_id).valor)
        if nuevo == actual:
            resultado["sin_cambios"].append(entrada.sucursal_id)
            continue
        await parametros.registrar_cambio(
            db, pc.CLAVE_TOPE_PEDIDO, _texto(entrada.valor), en_fecha,
            usuario_id, sucursal_id=entrada.sucursal_id)
        resultado["actualizados"].append(entrada.sucursal_id)
    return resultado
