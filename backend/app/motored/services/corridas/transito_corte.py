"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S5a, ADR-6): tránsito
(W) recalculado AL CORTE de la corrida.

W no se lee de las banderas `ingresada` / `transito_vencido` de F2, que se
calcularon contra la fecha de la ingesta y cambian con cada carga. Se
recomputa aquí con el veredicto puro de F2 (`transito.calcular_veredicto`)
evaluado en `fecha_corte`: facturas con `fecha_factura <= corte`, ingresos
con `fecha_ingreso <= corte`. Así el mismo corte da el mismo W sin importar
el día en que se ejecute la corrida.

- Un documento `(prefijo_rh, numero_rh)` ingresado sale del tránsito completo
  (nivel documento, nunca de línea).
- Sin exclusión (por defecto, igual que el Excel) una factura vieja sigue en
  W. Con `excluir_vencido` el documento vencido sale de W y se lista.
- Las notas crédito llegan con cantidad negativa y restan.
- Las cargas ANULADO se ignoran (F2 no borra sus filas al anular).

`calcular_transito_corte` es puro; `cargar_transito_corte` hace las dos
lecturas. Nadie lo llama todavía: lo conecta la corrida (S5b/S6a).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Mapping, Sequence, Tuple
from uuid import UUID

from sqlalchemy import select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.services.ingesta import transito

ESTADO_ANULADO = "ANULADO"
ClaveW = Tuple[UUID, UUID]


@dataclass(frozen=True)
class LineaFactura:
    prefijo_rh: str
    numero_rh: int
    fecha_factura: date
    sucursal_id: UUID
    referencia_id: UUID
    cantidad: Decimal
    valor_total: Decimal


@dataclass(frozen=True)
class IngresoDocumento:
    prefijo_rh: str
    numero_rh: int
    fecha_ingreso: date
    valor_neto: Decimal


@dataclass(frozen=True)
class LineaVencida:
    """Línea de un documento vencido, excluida de W por el switch."""

    prefijo_rh: str
    numero_rh: int
    fecha_factura: date
    sucursal_id: UUID
    referencia_id: UUID
    cantidad: Decimal


@dataclass(frozen=True)
class TransitoAlCorte:
    w: Mapping[ClaveW, Decimal]
    vencidas: Tuple[LineaVencida, ...]


def _documentos(lineas: Sequence[LineaFactura]) -> Dict:
    """Agrega las líneas por documento como espera el veredicto de F2."""
    valor: Dict = defaultdict(Decimal)
    fecha: Dict = {}
    for linea in lineas:
        clave = (linea.prefijo_rh, linea.numero_rh)
        valor[clave] += linea.valor_total
        fecha[clave] = min(
            fecha.get(clave, linea.fecha_factura), linea.fecha_factura)
    return {
        clave: transito.DocumentoFactura(valor[clave], fecha[clave])
        for clave in valor
    }


def calcular_transito_corte(
    facturas: Sequence[LineaFactura],
    ingresos: Sequence[IngresoDocumento],
    fecha_corte: date,
    *,
    excluir_vencido: bool,
    dias_ventana_ingresos: int,
    tolerancia_ingreso_pct: float,
) -> TransitoAlCorte:
    """W por (sucursal, referencia) y documentos vencidos excluidos."""
    lineas = [f for f in facturas if f.fecha_factura <= fecha_corte]
    valor_ingreso = {
        (i.prefijo_rh, i.numero_rh): i.valor_neto
        for i in ingresos if i.fecha_ingreso <= fecha_corte
    }
    veredictos = transito.calcular_veredictos(
        _documentos(lineas), valor_ingreso, fecha_corte,
        dias_ventana_ingresos, tolerancia_ingreso_pct)
    w: Dict[ClaveW, Decimal] = defaultdict(Decimal)
    vencidas: List[LineaVencida] = []
    for linea in lineas:
        veredicto = veredictos[(linea.prefijo_rh, linea.numero_rh)]
        if veredicto.ingresada:
            continue
        if excluir_vencido and veredicto.transito_vencido:
            vencidas.append(_vencida(linea))
            continue
        w[(linea.sucursal_id, linea.referencia_id)] += linea.cantidad
    return TransitoAlCorte(dict(w), tuple(vencidas))


def _vencida(linea: LineaFactura) -> LineaVencida:
    return LineaVencida(
        linea.prefijo_rh, linea.numero_rh, linea.fecha_factura,
        linea.sucursal_id, linea.referencia_id, linea.cantidad)


def _linea(fila) -> LineaFactura:
    return LineaFactura(
        fila.prefijo_rh, fila.numero_rh, fila.fecha_factura,
        fila.sucursal_id, fila.referencia_id, fila.cantidad,
        fila.valor_total)


def _ingreso(fila) -> IngresoDocumento:
    return IngresoDocumento(
        fila.prefijo_rh, fila.numero_rh, fila.fecha_ingreso,
        fila.valor_neto)


async def cargar_transito_corte(
    db,
    fecha_corte: date,
    *,
    excluir_vencido: bool,
    dias_ventana_ingresos: int,
    tolerancia_ingreso_pct: float,
) -> TransitoAlCorte:
    """Lee facturas e ingresos al corte (sin banderas de F2) y calcula W."""
    facturas = await db.execute(
        select(
            FacturaProveedorLinea.prefijo_rh,
            FacturaProveedorLinea.numero_rh,
            FacturaProveedorLinea.fecha_factura,
            FacturaProveedorLinea.sucursal_id,
            FacturaProveedorLinea.referencia_id,
            FacturaProveedorLinea.cantidad,
            FacturaProveedorLinea.valor_total,
        )
        .join(CargaArchivo, CargaArchivo.id == FacturaProveedorLinea.carga_id)
        .where(
            FacturaProveedorLinea.fecha_factura <= fecha_corte,
            CargaArchivo.estado != ESTADO_ANULADO,
        )
    )
    ingresos = await db.execute(
        select(
            IngresoFactura.prefijo_rh, IngresoFactura.numero_rh,
            IngresoFactura.fecha_ingreso, IngresoFactura.valor_neto,
        )
        .join(CargaArchivo, CargaArchivo.id == IngresoFactura.carga_id)
        .where(
            IngresoFactura.fecha_ingreso <= fecha_corte,
            CargaArchivo.estado != ESTADO_ANULADO,
        )
    )
    return calcular_transito_corte(
        [_linea(fila) for fila in facturas.all()],
        [_ingreso(fila) for fila in ingresos.all()],
        fecha_corte,
        excluir_vencido=excluir_vencido,
        dias_ventana_ingresos=dias_ventana_ingresos,
        tolerancia_ingreso_pct=tolerancia_ingreso_pct,
    )
