"""
Motored -- modelo `venta_detalle`: una fila por cada linea del archivo VENTAS
(alimenta los indicadores del tablero de asesores; el motor de pedidos NUNCA la lee -- sigue leyendo
solo `venta_mensual`).

Se escribe en `Aplicar` de una carga VENTAS, en la misma transaccion que el
upsert de `venta_mensual` y desde las mismas filas de staging. Re-subir los
mismos (sucursal, anio, mes) REEMPLAZA el detalle (delete-on-replace). Anular
una carga NO borra estas filas: todo lector debe filtrar
`carga_archivo.estado != 'ANULADO'` via `carga_id`.

Dato personal (Ley 1581 de 2012): `cliente_factura` y `vendedor` son nombres
de personas. Se guardan como texto, solo los ven los roles que ya ven ventas
y una politica de retencion se definira mas adelante.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class VentaDetalle(MotoredBase):
    __tablename__ = "venta_detalle"
    __table_args__ = (
        Index("ix_venta_detalle_sucursal_id_fecha", "sucursal_id", "fecha"),
        Index("ix_venta_detalle_vendedor_norm_fecha", "vendedor_norm", "fecha"),
        Index("ix_venta_detalle_carga_id", "carga_id"),
        Index("ix_venta_detalle_sucursal_id_nro_documento", "sucursal_id", "nro_documento"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    anio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    origen = Column(String(12), nullable=False)
    cantidad = Column(Numeric(14, 2), nullable=False)
    vendedor = Column(String(255), nullable=False)
    # Mayusculas, sin tildes, espacios colapsados: los nombres de Excel derivan.
    vendedor_norm = Column(String(255), nullable=False)
    valor_bruto = Column(Numeric(16, 2), nullable=False)
    valor_descuentos = Column(Numeric(16, 2), nullable=False)
    cliente_factura = Column(String(255), nullable=False)
    # Numero de factura: el detalle se agrega por factura (ticket, items por
    # factura, facturas multilinea).
    nro_documento = Column(String(50), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
