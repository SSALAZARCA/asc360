"""
Motored -- modelo `inventario_detalle`: una fila por cada linea del archivo
INVENTARIO (por bodega fisica, con su costo promedio unitario). Alimenta el
costo por referencia del tablero de asesores; el motor de pedidos NUNCA la
lee -- sigue leyendo solo `inventario_snapshot`.

Se escribe en `Aplicar` de una carga INVENTARIO, en la misma transaccion que
el upsert de `inventario_snapshot` y desde las mismas filas de staging.
Re-subir el mismo (fecha_corte, sucursal) REEMPLAZA el detalle
(delete-on-replace). Anular una carga NO borra estas filas: todo lector debe
filtrar `carga_archivo.estado != 'ANULADO'` via `carga_id`. La purga de
retencion (`services/retencion.py`) la borra en el mismo job y con la misma
`fecha_limite` que el snapshot.

`costo_unitario` es NULL cuando la celda venia en blanco o no se pudo
interpretar, y puede ser <= 0 (el ERP exporta costos negativos): todo lector
de costos debe excluir los valores NULL o <= 0.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class InventarioDetalle(MotoredBase):
    __tablename__ = "inventario_detalle"
    __table_args__ = (
        Index("ix_inventario_detalle_fecha_corte_sucursal_id", "fecha_corte", "sucursal_id"),
        Index("ix_inventario_detalle_referencia_id_fecha_corte", "referencia_id", "fecha_corte"),
        Index("ix_inventario_detalle_carga_id", "carga_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)
    fecha_corte = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    # Codigo crudo de la bodega fisica (sin consolidar), recortado.
    bodega = Column(String(20), nullable=False)
    existencia = Column(Numeric(14, 2), nullable=False)
    costo_unitario = Column(Numeric(16, 2), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
