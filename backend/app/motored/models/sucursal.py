"""
Motored Pedidos — modelo `sucursal` (sdd/motored-pedidos-cimientos, Fase 3).

`nombre` UNIQUE y canónico; el `trim()` obligatorio se aplica en la capa de
servicio (`services/maestros.py`) antes de persistir o comparar (spec:
"Trailing-whitespace sucursal name is normalized"). `sic` faltante es el
ÚNICO defecto BLOQUEANTE del tablero de salud (spec "Sucursal without SIC
is blocking").

Post-archive correction (spec §4.1): `dias_empaque`/`dias_transito` son el
valor PROPIO de esta sucursal, distinto de `proveedor.dias_empaque_default`/
`dias_transito_default` (que son solo el fallback usado cuando este campo
queda en null) -- Fase 1 únicamente persiste y edita el campo; la lógica de
resolución del fallback es del motor de cálculo, de una fase posterior.
`fecha_apertura` se usa recién en §6.4.4 (excluir meses sin operación) pero
el campo debe existir desde ya porque §7.12 lo lista como campo Fase-1 de la
pestaña Sucursales.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class Sucursal(MotoredBase):
    __tablename__ = "sucursal"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), unique=True, nullable=False)
    sic = Column(String(50), nullable=True)
    dias_seguridad = Column(Numeric(5, 2), nullable=False, default=2.5)
    dias_empaque = Column(Integer, nullable=True)
    dias_transito = Column(Integer, nullable=True)
    bodega_principal = Column(String(50), nullable=True)
    departamento = Column(String(120), nullable=True)
    ciudad = Column(String(120), nullable=True)
    fecha_apertura = Column(Date, nullable=True)
    activa = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
