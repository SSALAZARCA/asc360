"""
Inventory counts -- "Pendientes por sanear" before a count starts
(odd/motored-conteos-inventario, WU15).

An invoice still waiting for its ingreso, or a transfer still waiting for
its reception, makes the count show differences that are not real. The
pre-start screen lists them for the conteo's store and Iniciar WARNS
(`PendientesPorSanear`, a 409 with the counts) until the leader confirms;
it never blocks.

The lists come from the services that own those rules, read per store
exactly like the asesor card does (`ingresos_pendientes.pendientes`,
`traslados_pendientes.pendientes`: the verifiable window, the principal
rollup and the shared confirmation state). Nothing here changes them.

"Verificado en el ERP" (owner decision 2026-10-10): before Iniciar the
leader may mark an item as checked in the ERP. The mark lives ONLY on
this conteo (`snapshot_advertencias["verificados_erp"]`), never in the
Gestión repuestos confirmations; the next file load stays the official
source. A marked item stops counting for the Iniciar warning. Item keys
are the services' identities: the invoice name ("RH 482915") and
"documento|bodega_salida|bodega_entrada" for a transfer.

Nothing here commits: the API owns the transaction.
"""
import uuid
from datetime import date, datetime
from typing import (
    Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple,
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.conteo import Conteo
from app.motored.models.usuario import Usuario
from app.motored.services import ingresos_pendientes as ingresos
from app.motored.services import traslados_pendientes as traslados
from app.motored.services.conteos import acceso, errores
from app.motored.services.reloj import hoy_bogota

FACTURA = "FACTURA"
TRASLADO = "TRASLADO"
TIPOS = (FACTURA, TRASLADO)
CLAVE_VERIFICADOS = "verificados_erp"
# Response key -> carga tipo whose latest applied load dates the lists.
CARGAS = {
    "facturas_pedidos": "FACTURAS_PEDIDOS",
    "ingresos_facturas": "INGRESOS_FACTURAS",
    "traslados": "TRASLADOS",
}
MSG_SOLO_PROGRAMADO = (
    "Solo se pueden marcar pendientes antes de iniciar el conteo.")

Marcas = Sequence[Mapping[str, Any]]


# --- pure rules -------------------------------------------------------------


def clave_traslado(item: Mapping[str, Any]) -> str:
    return "|".join((
        item["documento"], item["bodega_salida"], item["bodega_entrada"]))


def verificados_de(advertencias: Optional[Mapping[str, Any]]) -> List[dict]:
    """The ERP marks stored on a conteo (none when nothing is stored)."""
    return list((advertencias or {}).get(CLAVE_VERIFICADOS) or [])


def _indice(marcas: Marcas) -> Dict[Tuple[str, str], Mapping[str, Any]]:
    return {(m["tipo"], m["clave"]): m for m in marcas}


def _verificado(marca: Optional[Mapping[str, Any]]) -> Optional[dict]:
    if marca is None:
        return None
    return {"por": marca.get("nombre") or "", "en": marca.get("en")}


def _cantidad(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def revisar(
        facturas: int, traslados_: int, confirmado: bool,
        usuario_id: uuid.UUID) -> Optional[dict]:
    """None with nothing pending. Otherwise PendientesPorSanear with the
    counts unless `confirmado`; then the record kept on the conteo."""
    if not facturas and not traslados_:
        return None
    if confirmado:
        return {"facturas": facturas, "traslados": traslados_,
                "confirmada_por": str(usuario_id)}
    raise errores.PendientesPorSanear(
        "Esta tienda tiene "
        f"{_cantidad(facturas, 'factura', 'facturas')} por ingresar y "
        f"{_cantidad(traslados_, 'traslado', 'traslados')} por recibir en "
        "el ERP. Si inicia así, el conteo mostrará diferencias que no son "
        "reales.",
        facturas=facturas, traslados=traslados_)


def combinar(
        antiguedad: Optional[dict], aviso: Optional[dict],
        marcas: Marcas) -> Optional[dict]:
    """What Iniciar stores in `snapshot_advertencias`: the stale-inventory
    record (flat, as before), plus `pendientes` and the ERP marks when
    there are any; None when there is nothing."""
    registro = dict(antiguedad or {})
    if aviso is not None:
        registro["pendientes"] = aviso
    if marcas:
        registro[CLAVE_VERIFICADOS] = list(marcas)
    return registro or None


def marcar_en(
        advertencias: Optional[Mapping[str, Any]], tipo: str, clave: str,
        usuario_id: uuid.UUID, nombre: str, ahora: datetime) -> dict:
    """A NEW advertencias dict with the item marked (re-marking replaces
    the earlier mark)."""
    quedan = desmarcar_en(advertencias, tipo, clave) or {}
    marca = {"tipo": tipo, "clave": clave, "usuario_id": str(usuario_id),
             "nombre": nombre, "en": ahora.isoformat()}
    return {**quedan,
            CLAVE_VERIFICADOS: verificados_de(quedan) + [marca]}


def desmarcar_en(
        advertencias: Optional[Mapping[str, Any]], tipo: str,
        clave: str) -> Optional[dict]:
    """A NEW advertencias dict without the item's mark; None when nothing
    is left."""
    resto = {k: v for k, v in (advertencias or {}).items()
             if k != CLAVE_VERIFICADOS}
    marcas = [m for m in verificados_de(advertencias)
              if (m["tipo"], m["clave"]) != (tipo, clave)]
    if marcas:
        resto[CLAVE_VERIFICADOS] = marcas
    return resto or None


def _factura(item: Mapping[str, Any], marcas) -> dict:
    clave = item["factura"]
    return {
        "factura": item["factura"], "fecha": item["fecha"],
        "dias": item["dias"], "unidades": item["unidades"],
        "valor": item["valor"], "num_referencias": item["num_referencias"],
        "estado_confirmacion": item["estado"],
        "confirmado_por": item["confirmado_por"], "clave": clave,
        "verificado": _verificado(marcas.get((FACTURA, clave)))}


def _traslado(item: Mapping[str, Any], marcas) -> dict:
    clave = clave_traslado(item)
    return {
        "documento": item["documento"], "fecha": item["fecha"],
        "dias": item["dias"], "bodega_salida": item["bodega_salida"],
        "bodega_entrada": item["bodega_entrada"], "sale": item["sale"],
        "llega": item["llega"], "refs": item["refs"],
        "unidades": item["unidades"], "num_lineas": item["num_lineas"],
        "estado_confirmacion": item["estado"],
        "confirmado_por": item["confirmado_por"], "clave": clave,
        "verificado": _verificado(marcas.get((TRASLADO, clave)))}


def _sin_verificar(filas: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for f in filas if f["verificado"] is None)


# --- database ---------------------------------------------------------------


async def ultima_carga(db: AsyncSession, tipo: str) -> Optional[dict]:
    """`{fecha_carga, periodo_hasta}` of the latest APLICADO carga of
    `tipo` (same order as the transfers' current snapshot)."""
    fila = (await db.execute(
        select(CargaArchivo.aplicado_en, CargaArchivo.periodo_hasta)
        .where(CargaArchivo.tipo == tipo,
               CargaArchivo.estado == "APLICADO")
        .order_by(CargaArchivo.aplicado_en.desc().nulls_last(),
                  CargaArchivo.created_at.desc())
        .limit(1))).first()
    if fila is None:
        return None
    return {"fecha_carga": fila[0], "periodo_hasta": fila[1]}


async def _filas(
        db: AsyncSession, sucursal_id: uuid.UUID, hoy: date,
        marcas: Marcas) -> Tuple[List[dict], List[dict]]:
    indice = _indice(marcas)
    facturas = await ingresos.pendientes(db, [sucursal_id], hoy=hoy)
    lista = await traslados.pendientes(db, [sucursal_id], hoy=hoy)
    return ([_factura(i, indice) for i in facturas],
            [_traslado(i, indice) for i in lista])


async def leer(
        db: AsyncSession, sucursal_id: uuid.UUID,
        hoy: Optional[date] = None, marcas: Marcas = ()) -> dict:
    """The `/pendientes` payload of a store."""
    facturas, lista = await _filas(
        db, sucursal_id, hoy or hoy_bogota(), marcas)
    cargas = {clave: await ultima_carga(db, tipo)
              for clave, tipo in CARGAS.items()}
    return {
        "facturas": facturas, "traslados": lista,
        "por_sanear": {"facturas": _sin_verificar(facturas),
                       "traslados": _sin_verificar(lista)},
        "cargas": cargas,
        "verificable_desde": await ingresos.verificable_desde(db)}


async def contar(
        db: AsyncSession, sucursal_id: uuid.UUID, hoy: date,
        marcas: Marcas = ()) -> Tuple[int, int]:
    """(facturas, traslados) still pending and not verified in the ERP."""
    facturas, lista = await _filas(db, sucursal_id, hoy, marcas)
    return _sin_verificar(facturas), _sin_verificar(lista)


async def _programado(db: AsyncSession, conteo_id: uuid.UUID) -> Conteo:
    conteo = await acceso.bloquear_conteo(db, conteo_id)
    if conteo.estado != "PROGRAMADO":
        raise errores.EstadoInvalido(
            MSG_SOLO_PROGRAMADO, estado=conteo.estado)
    return conteo


async def marcar(
        db: AsyncSession, conteo_id: uuid.UUID, tipo: str, clave: str,
        usuario_id: uuid.UUID, ahora: datetime) -> Conteo:
    """Marks a pending item of the store "Verificado en el ERP" (conteo
    row locked, PROGRAMADO only). 404 when it is no longer pending."""
    if tipo not in TIPOS:
        raise errores.PendienteInvalido()
    conteo = await _programado(db, conteo_id)
    facturas, lista = await _filas(
        db, conteo.sucursal_id, hoy_bogota(ahora), ())
    filas = facturas if tipo == FACTURA else lista
    if not any(f["clave"] == clave for f in filas):
        raise errores.PendienteNoEncontrado()
    usuario = await db.get(Usuario, usuario_id)
    conteo.snapshot_advertencias = marcar_en(
        conteo.snapshot_advertencias, tipo, clave, usuario_id,
        getattr(usuario, "nombre", "") or "", ahora)
    await db.flush()
    return conteo


async def desmarcar(
        db: AsyncSession, conteo_id: uuid.UUID, tipo: str,
        clave: str) -> Conteo:
    """Undoes a mark (PROGRAMADO only); a missing mark is a no-op."""
    if tipo not in TIPOS:
        raise errores.PendienteInvalido()
    conteo = await _programado(db, conteo_id)
    conteo.snapshot_advertencias = desmarcar_en(
        conteo.snapshot_advertencias, tipo, clave)
    await db.flush()
    return conteo
