"""
Motored Pedidos — modelo `referencia` (sdd/motored-pedidos-cimientos, Fase 3).

Reglas bloqueantes (proposal §4.1/§5.8, spec):
- UNIQUE(`codigo`, `proveedor_id`).
- `unidad_empaque` default 1, JAMÁS 0: el 0/None de entrada se corrige a 1
  en `services/maestros.py`/`services/carga.py`. `unidad_empaque_advertencia`
  persiste la marca de "esta fila fue corregida" para que el tablero de
  salud pueda listar exactamente esos casos como ADVERTENCIA (nunca hay
  forma de distinguir "corregido" de "cargado como 1" solo mirando el valor
  final, que siempre es >=1 por diseño).
- `precio_normal` es EL campo que valoriza pedidos -- distinto de
  `precio_venta`/`precio_publico` (informativos, nullable).
- `sustituida_por` seteado -> `activa = false` (services/maestros.py).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class Referencia(MotoredBase):
    __tablename__ = "referencia"
    __table_args__ = (UniqueConstraint("codigo", "proveedor_id", name="uq_referencia_codigo_proveedor"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(100), nullable=False)
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("proveedor.id"), nullable=False)
    descripcion = Column(String(255), nullable=True)

    unidad_empaque = Column(Integer, nullable=False, default=1)
    unidad_empaque_advertencia = Column(Boolean, nullable=False, default=False)

    precio_normal = Column(Numeric(14, 2), nullable=True)
    precio_venta = Column(Numeric(14, 2), nullable=True)
    precio_publico = Column(Numeric(14, 2), nullable=True)

    sustituida_por = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=True)
    activa = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
