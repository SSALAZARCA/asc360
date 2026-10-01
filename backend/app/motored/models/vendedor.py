"""
Motored -- modelo `vendedor`: maestro de vendedores (feature
motored-tablero-asesores, T3). Toda persona que vende, con o sin usuario en la
app. NO es el rol de acceso de la app (ASESOR_MOSTRADOR, etc.): el `cargo` es
texto libre del negocio.

La llave natural es `nombre_norm`, calculada con la MISMA normalizacion que
`venta_detalle.vendedor_norm` (`services/ingesta/ventas.py::normalizar_
vendedor`), para que el cruce con las ventas sea exacto. `nombre` conserva el
nombre del ERP tal como se escribio. `usuario_id` enlaza (a mano, nunca por
Excel ni por coincidencia de nombres) a un Usuario de la app. Quien vende pero
no esta aqui cuenta como "resto de compania" en el tablero.

Dato personal (Ley 1581 de 2012): nombre y cedula de empleados. Solo ADMIN y
COMPRAS. Nunca se borra: desactivar = `activo = false`.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class Vendedor(MotoredBase):
    __tablename__ = "vendedor"
    __table_args__ = (
        Index("uq_vendedor_nombre_norm", "nombre_norm", unique=True),
        Index("ix_vendedor_cargo", "cargo"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), nullable=False)
    nombre_norm = Column(String(255), nullable=False)
    cargo = Column(String(80), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=True)
    cedula = Column(String(20), nullable=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
