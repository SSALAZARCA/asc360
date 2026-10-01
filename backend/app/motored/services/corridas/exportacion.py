"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B4, ADR-7,
decisión F4-1, A5): qué tiendas se exportan a HMCL y cómo se arma el
archivo.

Sólo LEE: nunca escribe ni deja un evento, y se puede repetir (también tras
enviar la tienda, A5). Las reglas de `preparar_tienda` y `preparar_corrida`
son las de una exportación, en este orden de chequeos: la corrida y la tienda
existen (404), no es un escenario (042), la corrida terminó de calcularse
(040) y no está invalidada (041), la tienda tiene pedido (065), está CERRADO
o ENVIADO (055), tiene alguna cantidad mayor que 0 (056) y tiene SIC (057).

Para que el estado del pedido y sus líneas se lean juntos, toma la corrida
`FOR SHARE` y las tiendas `FOR SHARE` en orden de `sucursal_id` (el orden
global de `bloqueos.py`): un reabrir o un envío en curso espera a que la
lectura termine y nunca se exporta un pedido a medio cambiar. El llamador
confirma (suelta los bloqueos) ANTES de construir los archivos.

`construir_xlsx` y `construir_zip` son síncronas y sin base de datos: la API
las corre en un hilo (`run_in_threadpool`) y devuelven un archivo temporal
(`SpooledTemporaryFile`, en memoria hasta 8 MB y en disco después) listo para
transmitir, con su tamaño.
"""
import io
from collections import defaultdict
from tempfile import SpooledTemporaryFile
from typing import (
    Any,
    Callable,
    Dict,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Tuple,
)
from uuid import UUID

from sqlalchemy import select

from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import bloqueos, codigos, estados
from app.motored.services.corridas import exportacion_hmcl as hmcl
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.corridas.exportacion_hmcl import DatosTienda

ACCION_EXPORTAR = "exportar"
MAX_EN_MEMORIA = 8 * 1024 * 1024
EXPORTABLES = frozenset({estados.PEDIDO_CERRADO, estados.PEDIDO_ENVIADO})
MOTIVO_BORRADOR = "BORRADOR"
MOTIVO_SIN_PEDIDO = "SIN_PEDIDO"
MOTIVO_SIN_CANTIDAD = "SIN_CANTIDAD"
TEXTO_OMISION = {
    MOTIVO_BORRADOR: "El pedido sigue en BORRADOR",
    MOTIVO_SIN_PEDIDO: "No tiene pedido (su cálculo no terminó bien)",
    MOTIVO_SIN_CANTIDAD: "Todas sus cantidades son 0",
}


class SeleccionZip(NamedTuple):
    """La corrida, los datos de cada tienda que va en el zip y las que se
    omitieron con su motivo."""

    corrida: Any
    tiendas: List[DatosTienda]
    omitidas: List[Dict[str, str]]


# --- Rechazos ---------------------------------------------------------------


def _sin_pedido(nombre: str, sucursal_id: UUID) -> ErrorCorrida:
    texto = codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO)
    return ErrorCorrida(
        codigos.E_CORRIDA_SIN_PEDIDO, f"{nombre}: {texto}",
        {"sucursal_id": str(sucursal_id), "tienda": nombre})


def _no_cerrado(
    nombre: str, sucursal_id: UUID, estado: Optional[str],
) -> ErrorCorrida:
    detalle = (f"el pedido de {nombre} está {estado}: ciérrelo antes de "
               "exportarlo")
    codigo = codigos.E_CORRIDA_EXPORTAR_NO_CERRADO
    return ErrorCorrida(
        codigo, codigos.mensaje(codigo, detalle=detalle),
        {"sucursal_id": str(sucursal_id), "tienda": nombre,
         "estado_pedido": estado})


def _ninguna_cerrada() -> ErrorCorrida:
    detalle = ("ninguna tienda tiene el pedido cerrado o enviado; ciérrelo "
               "antes de exportarlo")
    codigo = codigos.E_CORRIDA_EXPORTAR_NO_CERRADO
    return ErrorCorrida(codigo, codigos.mensaje(codigo, detalle=detalle))


def _nada_que_exportar(
    nombre: Optional[str] = None, sucursal_id: Optional[UUID] = None,
) -> ErrorCorrida:
    detalle = None if sucursal_id is None else {
        "sucursal_id": str(sucursal_id), "tienda": nombre}
    return ErrorCorrida(
        codigos.E_CORRIDA_NADA_QUE_ENVIAR,
        codigos.mensaje_nada_que_exportar(nombre), detalle)


def _sin_sic(nombre: str, sucursal_id: UUID) -> ErrorCorrida:
    return ErrorCorrida(
        codigos.E_CORRIDA_EXPORTAR_SIN_SIC,
        codigos.mensaje(codigos.E_CORRIDA_EXPORTAR_SIN_SIC, tienda=nombre),
        {"sucursal_id": str(sucursal_id), "tienda": nombre})


# --- Lecturas ---------------------------------------------------------------


async def _tiendas(
    db, corrida_id: UUID, sucursal_ids: Optional[Sequence[UUID]],
) -> list:
    """`[(tienda, nombre, sic)]` con las filas `corrida_sucursal` bloqueadas
    `FOR SHARE` en orden de `sucursal_id`: todas las de la corrida o sólo las
    pedidas."""
    cs = CorridaSucursal
    consulta = (
        select(cs, Sucursal.nombre, Sucursal.sic)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(cs.corrida_id == corrida_id))
    if sucursal_ids is not None:
        consulta = consulta.where(cs.sucursal_id.in_(list(sucursal_ids)))
    resultado = await db.execute(
        consulta.order_by(cs.sucursal_id)
        .with_for_update(read=True, of=cs)
        .execution_options(populate_existing=True))
    return resultado.all()


async def _lineas(
    db, corrida_id: UUID, sucursal_ids: Sequence[UUID],
) -> Dict[UUID, List[Tuple[str, Any]]]:
    """`{sucursal_id: [(código, cantidad)]}` de las líneas con cantidad a
    pedir mayor que 0 y no excluidas, en UNA consulta."""
    cl = CorridaLinea
    resultado = await db.execute(
        select(cl.sucursal_id, cl.codigo_referencia, cl.pedido_final)
        .where(cl.corrida_id == corrida_id,
               cl.sucursal_id.in_(list(sucursal_ids)),
               cl.motivo_exclusion.is_(None), cl.pedido_final > 0))
    agrupadas: Dict[UUID, List[Tuple[str, Any]]] = defaultdict(list)
    for sucursal_id, codigo, cantidad in resultado.all():
        agrupadas[sucursal_id].append((codigo, cantidad))
    return agrupadas


# --- Reglas -----------------------------------------------------------------


def _exigir_exportable(fila: Any) -> None:
    """065 si la tienda no tiene pedido y 055 si todavía no está cerrado."""
    tienda, nombre, _ = fila
    nombre = nombre.strip()
    if tienda.estado_pedido is None:
        raise _sin_pedido(nombre, tienda.sucursal_id)
    if tienda.estado_pedido not in EXPORTABLES:
        raise _no_cerrado(nombre, tienda.sucursal_id, tienda.estado_pedido)


def _datos(corrida: Any, fila: Any, lineas: Sequence[Any]) -> DatosTienda:
    """Los datos del archivo de una tienda; 057 si no tiene SIC."""
    tienda, nombre, sic = fila
    nombre = nombre.strip()
    if not (sic or "").strip():
        raise _sin_sic(nombre, tienda.sucursal_id)
    return DatosTienda(
        nombre, sic.strip(), corrida.fecha_corte, list(lineas))


async def preparar_tienda(
    db, corrida_id: UUID, sucursal_id: UUID,
) -> DatosTienda:
    """Los datos del archivo de UNA tienda. `LookupError` si la corrida o la
    tienda no existen; el resto, `ErrorCorrida` con el código de la regla."""
    corrida = await bloqueos.bloquear_corrida(db, corrida_id, exclusivo=False)
    filas = await _tiendas(db, corrida_id, [sucursal_id])
    if not filas:
        raise LookupError("La tienda no está en la corrida.")
    bloqueos.exigir_operable(corrida, ACCION_EXPORTAR)
    _exigir_exportable(filas[0])
    lineas = (await _lineas(db, corrida_id, [sucursal_id])).get(sucursal_id)
    if not lineas:
        raise _nada_que_exportar(filas[0][1].strip(), sucursal_id)
    return _datos(corrida, filas[0], lineas)


def _motivo_omision(tienda: Any, lineas: Dict[UUID, list]) -> Optional[str]:
    if tienda.estado_pedido is None:
        return MOTIVO_SIN_PEDIDO
    if tienda.estado_pedido not in EXPORTABLES:
        return MOTIVO_BORRADOR
    return None if lineas.get(tienda.sucursal_id) else MOTIVO_SIN_CANTIDAD


def _omitida(tienda: Any, nombre: str, motivo: str) -> Dict[str, str]:
    return {"sucursal_id": str(tienda.sucursal_id), "nombre": nombre.strip(),
            "codigo": motivo, "motivo": TEXTO_OMISION[motivo]}


def _repartir(corrida: Any, filas: list, lineas: Dict[UUID, list]):
    """Parte las tiendas entre las que van en el zip y las omitidas (con su
    motivo); 057 si una que va no tiene SIC."""
    tiendas: List[DatosTienda] = []
    omitidas: List[Dict[str, str]] = []
    for fila in filas:
        tienda, nombre, _ = fila
        motivo = _motivo_omision(tienda, lineas)
        if motivo is not None:
            omitidas.append(_omitida(tienda, nombre, motivo))
        else:
            tiendas.append(_datos(corrida, fila, lineas[tienda.sucursal_id]))
    return tiendas, omitidas


async def preparar_corrida(
    db, corrida_id: UUID, sucursal_ids: Optional[Sequence[UUID]] = None,
) -> SeleccionZip:
    """Los datos de cada tienda del zip. Sin lista, todas las tiendas
    CERRADO o ENVIADO con algo para pedir (las demás se omiten y se dice por
    qué); con lista, esas: una sin pedido (065) o en BORRADOR (055) rechaza
    la petición y una sin cantidades se omite. `LookupError` si la corrida
    o alguna tienda pedida no existen."""
    corrida = await bloqueos.bloquear_corrida(db, corrida_id, exclusivo=False)
    pedidas = None if sucursal_ids is None else list(dict.fromkeys(
        sucursal_ids))
    filas = await _tiendas(db, corrida_id, pedidas)
    if pedidas is not None:
        if len(filas) != len(pedidas):
            raise LookupError("La tienda no está en la corrida.")
        for fila in filas:
            _exigir_exportable(fila)
    bloqueos.exigir_operable(corrida, ACCION_EXPORTAR)
    exportables = [f[0].sucursal_id for f in filas
                   if f[0].estado_pedido in EXPORTABLES]
    if not exportables:
        raise _ninguna_cerrada()
    lineas = await _lineas(db, corrida_id, exportables)
    tiendas, omitidas = _repartir(corrida, filas, lineas)
    if not tiendas:
        raise _nada_que_exportar()
    return SeleccionZip(corrida, tiendas, omitidas)


# --- Construir los archivos (síncrono, sin base de datos) -------------------


def _archivo_temporal(
    escribir: Callable[[Any], None],
) -> Tuple[Any, int]:
    """Corre `escribir(archivo)` sobre un archivo temporal, lo deja
    rebobinado y devuelve `(archivo, tamaño)`; si falla, lo cierra."""
    archivo = SpooledTemporaryFile(max_size=MAX_EN_MEMORIA)
    try:
        escribir(archivo)
        tamano = archivo.tell()
        archivo.seek(0)
    except BaseException:
        archivo.close()
        raise
    return archivo, tamano


def construir_xlsx(datos: DatosTienda) -> Tuple[Any, int]:
    """El `.xlsx` de una tienda: `(archivo temporal rebobinado, tamaño)`."""
    return _archivo_temporal(lambda destino: hmcl.escribir_libro(
        datos, destino))


def _archivos_del_zip(
    tiendas: Sequence[DatosTienda],
) -> List[Tuple[str, bytes]]:
    archivos = []
    for datos in tiendas:
        buffer = io.BytesIO()
        hmcl.escribir_libro(datos, buffer)
        nombre = hmcl.nombre_archivo(
            datos.sic, datos.nombre, datos.fecha_corte)
        archivos.append((nombre, buffer.getvalue()))
    return archivos


def construir_zip(tiendas: Sequence[DatosTienda]) -> Tuple[Any, int]:
    """El zip con un `.xlsx` por tienda: `(archivo temporal rebobinado,
    tamaño)`."""
    return _archivo_temporal(lambda destino: hmcl.empaquetar(
        _archivos_del_zip(tiendas), destino))
