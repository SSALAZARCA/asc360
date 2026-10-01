"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5b,
ADR-6, decisiones F4-7 y F4-12, spec TP-08..TP-14b y TP-24..TP-33): ver y
aplicar el recorte al tope de presupuesto de UNA tienda.

- `resumen_topes`: por tienda con pedido, su tope, lo que vale el pedido, el
  exceso y cuántas líneas con cantidad no tienen precio.
- `previsualizar`: la propuesta de `recorte.proponer_recorte` para una tienda
  en BORRADOR, con su `token` (sha256 del JSON canónico de la propuesta).
  Sólo lee: no toma ningún bloqueo ni escribe. Si la propuesta no aplica
  (modo apagado, sin tope, pedido cerrado, escenario...) devuelve
  `activo: False` y el `motivo_inactivo`, nunca una propuesta.
- `aplicar`: bloquea la corrida `FOR SHARE`, la tienda `FOR UPDATE` y sus
  líneas `FOR UPDATE ORDER BY id` (el orden global de `bloqueos.py`),
  RECALCULA la propuesta y sólo la aplica si su token es el que el usuario
  vio; si no (o si ya no hay nada que recortar) es E-CORRIDA-060 y no
  cambia nada. Escribe cada línea recortada y su fila de
  `corrida_linea_historial` (motivo RECORTE_PRESUPUESTO, con el tope, la
  versión del parámetro y el token) en la misma transacción, igual que una
  edición manual. Nunca recorta sola: sólo con esta llamada.
- `topes_congelados`: el tope en vigor de cada tienda que se cierra, para
  el `detalle` de su evento CERRADO (`pedido_tienda.py`).

Orden de los chequeos (R3 de las tareas): corrida y tienda (404), escenario
(042), cálculo (040), invalidada (041), tienda sin pedido (065), pedido no
BORRADOR (061), modo apagado (058), tienda sin tope (059) y token (060).

Ningún commit acá: la transacción es del llamador.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Dict, List, NamedTuple, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, bindparam, func, insert, or_, select, update

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services import parametros_topes
from app.motored.services.corridas import (
    bloqueos,
    codigos,
    estados,
    lecturas_pedido,
    recorte,
    valores,
)
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.motor.aritmetica import a_fraccion, cuantizar
from app.motored.services.reloj import hoy_bogota

ACCION = "recortar"
MOTIVO_RECORTE = "RECORTE_PRESUPUESTO"

# Por qué una propuesta no aplica, según el código del rechazo.
_MOTIVOS_INACTIVO = {
    codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA: "ESCENARIO",
    codigos.E_CORRIDA_ESTADO_NO_ADMITE: "CORRIDA_NO_CALCULADA",
    codigos.E_CORRIDA_INVALIDADA: "CORRIDA_INVALIDADA",
    codigos.E_CORRIDA_SIN_PEDIDO: "SIN_PEDIDO",
    codigos.E_CORRIDA_RECORTE_NO_BORRADOR: "NO_BORRADOR",
    codigos.E_CORRIDA_RECORTE_MODO_OFF: "MODO_OFF",
    codigos.E_CORRIDA_RECORTE_SIN_TOPE: "SIN_TOPE",
}

_COLUMNAS = (
    CorridaLinea.id,
    CorridaLinea.codigo_referencia,
    CorridaLinea.nombre_parte,
    CorridaLinea.clase_abc,
    CorridaLinea.pedido_final,
    CorridaLinea.unidad_empaque,
    CorridaLinea.precio,
    CorridaLinea.inventario_final,
    CorridaLinea.demanda_ponderada,
)


class _Contexto(NamedTuple):
    """Lo que `previsualizar` y `aplicar` comparten tras sus chequeos."""

    limite: Decimal
    parametro_id: Optional[UUID]


# --- Puro: token, líneas y vistas -------------------------------------------


def token_de(
    sucursal_id: UUID, limite: Fraction, cortes: Sequence[recorte.Recorte],
) -> str:
    """sha256 del JSON canónico de la propuesta: la tienda, el tope y, por
    línea, `[id, cantidad actual, cantidad propuesta]` ordenado por id. Lo
    que el usuario vio; si algo de eso cambia, el token cambia."""
    cuerpo = {
        "sucursal_id": str(sucursal_id),
        "tope": str(limite),
        "recortes": sorted(
            [x.linea_id, str(x.pedido_actual), str(x.pedido_propuesto)]
            for x in cortes),
    }
    canonico = json.dumps(cuerpo, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _fraccion(valor: Any, defecto: int = 0) -> Fraction:
    return a_fraccion(defecto if valor is None else valor)


def lineas_recortables(filas: Sequence[Any]) -> List[recorte.LineaRecortable]:
    """Las filas de la consulta como entradas del recorte puro: `y` es el
    inventario efectivo de la línea (`inventario_final`, V + W + X) y `n` la
    demanda ponderada; sin demanda o sin precio quedan en `None`."""
    return [
        recorte.LineaRecortable(
            linea_id=f.id,
            codigo=f.codigo_referencia,
            clase_abc=f.clase_abc,
            pedido=_fraccion(f.pedido_final),
            unidad_empaque=f.unidad_empaque,
            precio=None if f.precio is None else a_fraccion(f.precio),
            y=_fraccion(f.inventario_final),
            n=None if f.demanda_ponderada is None
            else a_fraccion(f.demanda_ponderada),
        )
        for f in filas
    ]


def _jsonable(valor: Any) -> Any:
    """La vista con `Decimal` y `UUID` como texto (la serializa `json`)."""
    if isinstance(valor, dict):
        return {k: _jsonable(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_jsonable(v) for v in valor]
    if isinstance(valor, (Decimal, UUID)):
        return str(valor)
    return valor


def _empaques(corte: recorte.Recorte, unidad: int) -> Optional[Decimal]:
    if unidad <= 0:
        return None
    quitado = corte.pedido_actual - corte.pedido_propuesto
    return cuantizar(quitado / unidad, 2)


def _linea_vista(corte: recorte.Recorte, fila: Any) -> Dict[str, Any]:
    return {
        "linea_id": corte.linea_id,
        "codigo": corte.codigo,
        "nombre": fila.nombre_parte,
        "clase_abc": corte.clase_abc,
        "unidad_empaque": fila.unidad_empaque,
        "pedido_actual": cuantizar(corte.pedido_actual, 2),
        "pedido_propuesto": cuantizar(corte.pedido_propuesto, 2),
        "empaques_recortados": _empaques(corte, fila.unidad_empaque),
        "valor_recortado": cuantizar(corte.valor_recortado, 2),
    }


def _aviso(codigo: str, cantidad: int) -> Dict[str, str]:
    return {"codigo": codigo,
            "mensaje": codigos.mensaje(codigo, cantidad=cantidad)}


def _advertencias(
    propuesta: recorte.PropuestaRecorte, por_id: Dict[int, Any],
) -> List[Dict[str, str]]:
    """A-CORRIDA-120 si el recorte baja líneas que no estaban en múltiplos
    del empaque; A-CORRIDA-121 si hay líneas con cantidad y sin precio."""
    fuera = sum(
        1 for x in propuesta.recortes
        if valores.fuera_de_empaque(
            x.pedido_actual, por_id[x.linea_id].unidad_empaque))
    avisos = []
    if fuera:
        avisos.append(_aviso(codigos.A_CORRIDA_FUERA_DE_EMPAQUE, fuera))
    if propuesta.lineas_sin_precio:
        avisos.append(_aviso(
            codigos.A_CORRIDA_TOPE_SIN_PRECIO, propuesta.lineas_sin_precio))
    return avisos


def _vista_activa(
    corrida_id: UUID, sucursal_id: UUID, limite: Decimal,
    propuesta: recorte.PropuestaRecorte, por_id: Dict[int, Any],
) -> Dict[str, Any]:
    token = token_de(sucursal_id, a_fraccion(limite), propuesta.recortes)
    return {
        "activo": True,
        "motivo_inactivo": None,
        "modo_activo": True,
        "corrida_id": corrida_id,
        "sucursal_id": sucursal_id,
        "tope": limite,
        "valor_actual": cuantizar(propuesta.valor_actual, 2),
        "exceso": cuantizar(propuesta.exceso, 2),
        "recortes": [
            _linea_vista(x, por_id[x.linea_id]) for x in propuesta.recortes],
        "valor_final": cuantizar(propuesta.valor_final, 2),
        "exceso_residual": cuantizar(propuesta.exceso_residual, 2),
        "lineas_sin_precio": propuesta.lineas_sin_precio,
        "advertencias": _advertencias(propuesta, por_id),
        "token": token,
    }


def _vista_inactiva(
    corrida_id: UUID, sucursal_id: UUID, error: ErrorCorrida,
) -> Dict[str, Any]:
    """La propuesta que no aplica: dice por qué y no trae nada que aplicar."""
    detalle = error.detalle or {}
    return {
        "activo": False,
        "motivo_inactivo": _MOTIVOS_INACTIVO[error.codigo],
        "modo_activo": detalle.get("modo_activo"),
        "corrida_id": corrida_id,
        "sucursal_id": sucursal_id,
        "tope": None,
        "valor_actual": None,
        "exceso": None,
        "recortes": [],
        "valor_final": None,
        "exceso_residual": None,
        "lineas_sin_precio": 0,
        "advertencias": [],
        "token": None,
    }


# --- Lecturas y chequeos ----------------------------------------------------


async def _leer_uno(db, consulta, ausente: str):
    """Una fila ORM sin bloquear (siempre fresca); `LookupError` si falta."""
    resultado = await db.execute(
        consulta.execution_options(populate_existing=True))
    fila = resultado.scalars().first()
    if fila is None:
        raise LookupError(ausente)
    return fila


def _exigir_borrador(tienda: Any) -> None:
    """065 si la tienda no tiene pedido; 061 si no está en BORRADOR."""
    if tienda.estado_pedido is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_SIN_PEDIDO,
            codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO))
    if tienda.estado_pedido != estados.PEDIDO_BORRADOR:
        raise ErrorCorrida(
            codigos.E_CORRIDA_RECORTE_NO_BORRADOR,
            codigos.mensaje(
                codigos.E_CORRIDA_RECORTE_NO_BORRADOR,
                estado=tienda.estado_pedido))


async def _vigentes(db, hoy: date):
    return await parametros.obtener_vigentes_motor(
        db, [pc.CLAVE_MODO_TOPE, pc.CLAVE_TOPE_PEDIDO], hoy)


def _modo_activo(vigentes) -> bool:
    return vigentes.resolver(pc.CLAVE_MODO_TOPE).valor is True


async def _exigir_tope(db, sucursal_id: UUID, hoy: date) -> _Contexto:
    """058 con el modo apagado; 059 si la tienda no tiene tope PROPIO."""
    vigentes = await _vigentes(db, hoy)
    if not _modo_activo(vigentes):
        raise ErrorCorrida(
            codigos.E_CORRIDA_RECORTE_MODO_OFF,
            codigos.mensaje(codigos.E_CORRIDA_RECORTE_MODO_OFF),
            {"modo_activo": False})
    limite, parametro_id = parametros_topes.tope_de(vigentes, sucursal_id)
    if limite is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_RECORTE_SIN_TOPE,
            codigos.mensaje(codigos.E_CORRIDA_RECORTE_SIN_TOPE),
            {"modo_activo": True})
    return _Contexto(limite, parametro_id)


async def _preparar(
    db, corrida_id: UUID, sucursal_id: UUID, hoy: date, *, bloquear: bool,
) -> _Contexto:
    """Los chequeos comunes de ver y aplicar, en el orden de R3. Con
    `bloquear`, la corrida `FOR SHARE` y la tienda `FOR UPDATE`; sin él,
    lecturas simples."""
    if bloquear:
        corrida = await bloqueos.bloquear_corrida(
            db, corrida_id, exclusivo=False)
        tienda = await bloqueos.bloquear_tienda(
            db, corrida_id, sucursal_id, exclusivo=True)
    else:
        corrida = await _leer_uno(
            db, select(Corrida).where(Corrida.id == corrida_id),
            "Corrida no encontrada.")
        tienda = await _leer_uno(
            db, select(CorridaSucursal).where(
                CorridaSucursal.corrida_id == corrida_id,
                CorridaSucursal.sucursal_id == sucursal_id),
            "La tienda no está en la corrida.")
    bloqueos.exigir_operable(corrida, ACCION)
    _exigir_borrador(tienda)
    return await _exigir_tope(db, sucursal_id, hoy)


async def _leer_lineas(
    db, corrida_id: UUID, sucursal_id: UUID, *, bloquear: bool,
) -> list:
    """Las líneas con cantidad de la tienda, sin las excluidas, por id. Con
    `bloquear`, `FOR UPDATE` (en orden de id: nadie se cruza)."""
    consulta = (
        select(*_COLUMNAS)
        .where(CorridaLinea.corrida_id == corrida_id,
               CorridaLinea.sucursal_id == sucursal_id,
               CorridaLinea.motivo_exclusion.is_(None),
               CorridaLinea.pedido_final > 0)
        .order_by(CorridaLinea.id))
    if bloquear:
        consulta = consulta.with_for_update()
    return list((await db.execute(consulta)).all())


async def _proponer(
    db, corrida_id: UUID, sucursal_id: UUID, limite: Decimal, *,
    bloquear: bool,
):
    """`(propuesta, vista, por_id)` de la tienda con sus líneas ACTUALES."""
    filas = await _leer_lineas(
        db, corrida_id, sucursal_id, bloquear=bloquear)
    propuesta = recorte.proponer_recorte(
        lineas_recortables(filas), a_fraccion(limite))
    por_id = {f.id: f for f in filas}
    vista = _vista_activa(corrida_id, sucursal_id, limite, propuesta, por_id)
    return propuesta, vista, por_id


# --- Ver --------------------------------------------------------------------


async def previsualizar(
    db, corrida_id: UUID, sucursal_id: UUID, hoy: Optional[date] = None,
) -> Dict[str, Any]:
    """La propuesta de recorte de la tienda, con su token, o `activo: False`
    y el motivo. No toma bloqueos ni escribe; repetirla da lo mismo.
    `LookupError` si la corrida o la tienda no existen."""
    hoy = hoy or hoy_bogota()
    try:
        contexto = await _preparar(
            db, corrida_id, sucursal_id, hoy, bloquear=False)
    except ErrorCorrida as error:
        return _vista_inactiva(corrida_id, sucursal_id, error)
    _, vista, _ = await _proponer(
        db, corrida_id, sucursal_id, contexto.limite, bloquear=False)
    return vista


# --- Aplicar ----------------------------------------------------------------


def _cambios(propuesta, por_id) -> List[Dict[str, Any]]:
    """Los parámetros del UPDATE por lote: cada línea con su nueva cantidad
    y el valor que el motor le habría calculado."""
    return [
        {"b_id": x.linea_id,
         "b_final": cuantizar(x.pedido_propuesto, 2),
         "b_valor": valores.valor(
             x.pedido_propuesto, por_id[x.linea_id].precio)}
        for x in sorted(propuesta.recortes, key=lambda x: x.linea_id)
    ]


def _filas_historial(
    propuesta, corrida_id: UUID, sucursal_id: UUID, detalle: dict,
    usuario_id: UUID,
) -> List[Dict[str, Any]]:
    return [
        {"corrida_id": corrida_id, "linea_id": x.linea_id,
         "sucursal_id": sucursal_id, "campo": "pedido_final",
         "valor_anterior": cuantizar(x.pedido_actual, 2),
         "valor_nuevo": cuantizar(x.pedido_propuesto, 2),
         "motivo": MOTIVO_RECORTE, "detalle": detalle,
         "usuario_id": usuario_id}
        for x in sorted(propuesta.recortes, key=lambda x: x.linea_id)
    ]


async def _escribir(
    db, propuesta, por_id, filas_historial: List[Dict[str, Any]],
) -> None:
    """UPDATE por lote de las líneas y, después (el padre antes que el
    hijo), las filas del historial; ambos en la transacción del llamador."""
    tabla = CorridaLinea.__table__
    await db.execute(
        update(tabla).where(tabla.c.id == bindparam("b_id")).values(
            pedido_final=bindparam("b_final"),
            valor_pedido=bindparam("b_valor")),
        _cambios(propuesta, por_id))
    await db.execute(insert(CorridaLineaHistorial), filas_historial)


def _desactualizada(vista: Dict[str, Any]) -> ErrorCorrida:
    """060 con la propuesta fresca, para que la pantalla la muestre."""
    return ErrorCorrida(
        codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA,
        codigos.mensaje(codigos.E_CORRIDA_PROPUESTA_DESACTUALIZADA),
        {"propuesta": _jsonable(vista)})


async def aplicar(
    db, corrida_id: UUID, sucursal_id: UUID, token: Any, usuario_id: UUID,
    hoy: Optional[date] = None,
) -> Dict[str, Any]:
    """Aplica el recorte de la tienda si `token` es el de la propuesta
    ACTUAL; si no, o si no hay nada que recortar, E-CORRIDA-060 y nada
    cambia. `LookupError` si la corrida o la tienda no existen."""
    hoy = hoy or hoy_bogota()
    contexto = await _preparar(db, corrida_id, sucursal_id, hoy, bloquear=True)
    propuesta, vista, por_id = await _proponer(
        db, corrida_id, sucursal_id, contexto.limite, bloquear=True)
    if not propuesta.recortes or token != vista["token"]:
        raise _desactualizada(vista)
    detalle = {"tope": format(contexto.limite, "f"),
               "parametro_id": str(contexto.parametro_id),
               "token": vista["token"]}
    await _escribir(db, propuesta, por_id, _filas_historial(
        propuesta, corrida_id, sucursal_id, detalle, usuario_id))
    totales = await lecturas_pedido.totales_de_tienda(
        db, corrida_id, sucursal_id)
    return {
        "corrida_id": corrida_id,
        "sucursal_id": sucursal_id,
        "tope": contexto.limite,
        "lineas_recortadas": len(propuesta.recortes),
        "valor_liberado": cuantizar(
            propuesta.valor_actual - propuesta.valor_final, 2),
        "valor_final": vista["valor_final"],
        "exceso_residual": vista["exceso_residual"],
        "advertencias": vista["advertencias"],
        "totales_tienda": totales,
    }


# --- Resumen por corrida ----------------------------------------------------


def _consulta_resumen(corrida_id: UUID):
    cs, cl = CorridaSucursal, CorridaLinea
    sin_precio = func.count(cl.id).filter(
        cl.pedido_final > 0, or_(cl.precio.is_(None), cl.precio <= 0))
    return (
        select(cs.sucursal_id, Sucursal.nombre, cs.estado_pedido,
               func.coalesce(func.sum(cl.valor_pedido), 0), sin_precio)
        .select_from(cs)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .outerjoin(cl, and_(
            cl.corrida_id == cs.corrida_id,
            cl.sucursal_id == cs.sucursal_id,
            cl.motivo_exclusion.is_(None)))
        .where(cs.corrida_id == corrida_id, cs.estado == estados.SUC_OK,
               cs.estado_pedido.is_not(None))
        .group_by(cs.sucursal_id, Sucursal.nombre, cs.estado_pedido)
        .order_by(Sucursal.nombre))


def _fila_resumen(fila: Any, vigentes) -> Dict[str, Any]:
    sucursal_id, nombre, estado, valor, sin_precio = fila
    limite, _ = parametros_topes.tope_de(vigentes, sucursal_id)
    valor = Decimal(valor)
    exceso = None if limite is None else cuantizar(
        max(Fraction(0), a_fraccion(valor) - a_fraccion(limite)), 2)
    return {
        "sucursal_id": sucursal_id, "nombre": nombre,
        "estado_pedido": estado, "tope": limite, "valor_a_pedir": valor,
        "exceso": exceso, "lineas_sin_precio": sin_precio,
    }


async def resumen_topes(
    db, corrida_id: UUID, hoy: Optional[date] = None,
) -> Dict[str, Any]:
    """Por tienda con pedido: su tope (si lo tiene), el valor a pedir, el
    exceso y las líneas con cantidad sin precio. `activo: False` y sin
    tiendas con el modo apagado, en un escenario o con la corrida sin
    calcular. `LookupError` si la corrida no existe."""
    hoy = hoy or hoy_bogota()
    corrida = await _leer_uno(
        db, select(Corrida).where(Corrida.id == corrida_id),
        "Corrida no encontrada.")
    inactivo = {"activo": False, "corrida_id": corrida_id, "tiendas": []}
    if corrida.es_escenario or corrida.estado not in estados.CALCULADAS:
        return inactivo
    vigentes = await _vigentes(db, hoy)
    if not _modo_activo(vigentes):
        return inactivo
    filas = (await db.execute(_consulta_resumen(corrida_id))).all()
    return {"activo": True, "corrida_id": corrida_id,
            "tiendas": [_fila_resumen(f, vigentes) for f in filas]}


# --- El tope congelado al cerrar --------------------------------------------


async def topes_congelados(
    db, sucursal_ids: Sequence[UUID], hoy: Optional[date] = None,
) -> Dict[UUID, Dict[str, str]]:
    """`{sucursal_id: {tope, parametro_id}}` del tope EN VIGOR de cada tienda
    que se cierra, para el `detalle` de su evento CERRADO. Con el modo
    apagado, o sin tope propio, la tienda no aparece."""
    vigentes = await _vigentes(db, hoy or hoy_bogota())
    if not _modo_activo(vigentes):
        return {}
    congelados = {}
    for sucursal_id in sucursal_ids:
        limite, parametro_id = parametros_topes.tope_de(
            vigentes, sucursal_id)
        if limite is not None:
            congelados[sucursal_id] = {
                "tope": format(limite, "f"),
                "parametro_id": str(parametro_id)}
    return congelados
