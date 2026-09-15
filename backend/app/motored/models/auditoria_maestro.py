"""
Motored Pedidos — modelo `auditoria_maestro` (sdd/motored-pedidos-
cimientos, Fase 3, §7.15). Rastro de auditoría de EDICIÓN DE MAESTROS
únicamente -- alcance cerrado en la proposal, no es un sistema de auditoría
general. Una fila por campo cambiado, escrita por
`services/auditoria.py::diff_and_audit`.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class AuditoriaMaestro(MotoredBase):
    __tablename__ = "auditoria_maestro"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entidad = Column(String(50), nullable=False)  # 'sucursal' | 'bodega' | 'proveedor' | 'referencia'
    entidad_id = Column(UUID(as_uuid=True), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    accion = Column(String(20), nullable=False)  # 'create' | 'update' | 'deactivate'
    campo = Column(String(100), nullable=True)
    valor_anterior = Column(String(500), nullable=True)
    valor_nuevo = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
