"""
Motored Pedidos — modelo `factura_proveedor_linea` (sdd/motored-pedidos-
ingesta, Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"; design
§Schema, ADR-9, spec "Tránsito cruce by RH document identity").

Identidad de documento vía `(prefijo_rh, numero_rh)` -- `numero_rh` es
`bigint`, NUNCA texto de ancho fijo (H3): el regex `^([A-Z]{2})(\\d+)$` de
`services/ingesta/transito.py` (Fase 8) extrae ambas partes y las compara
como (prefijo, entero), soportando números de más de 6 dígitos. `ingresada`/
`transito_vencido`/`ingreso_parcial_sospechoso` los completa el cruce contra
`ingreso_factura` (Fase 8) -- acá son columnas booleanas con default
`False`, sin lógica todavía.

`valor_total` (migración `3956c0ebd69c`, Phase 8): agregado junto a
`cantidad` -- el schema original de esta fase (Phase 3) solo tenía
`cantidad` (unidades, de la columna `Cantidad`), sin ningún campo
monetario, pero el cruce de tránsito (spec §5.6) necesita comparar VALOR
neto (`Vlr. Total Neto` en el archivo real), no unidades, para
`ingreso_parcial_sospechoso`. `cantidad` mantiene su significado real
(unidades, para la regla Parte/resta de NC); `valor_total` es la línea de
`Vlr. Total Neto` sin transformar.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class FacturaProveedorLinea(MotoredBase):
    __tablename__ = "factura_proveedor_linea"
    __table_args__ = (
        UniqueConstraint(
            "prefijo_rh", "numero_rh", "sucursal_id", "referencia_id",
            name="uq_factura_proveedor_linea_rh_sucursal_referencia",
        ),
        Index("ix_factura_proveedor_linea_prefijo_rh_numero_rh", "prefijo_rh", "numero_rh"),
        Index(
            "ix_factura_proveedor_linea_ingresada_transito_vencido",
            "ingresada", "transito_vencido",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prefijo_rh = Column(String(2), nullable=False)
    numero_rh = Column(BigInteger, nullable=False)
    fecha_factura = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False)
    cantidad = Column(Numeric(14, 2), nullable=False)
    valor_total = Column(Numeric(14, 2), nullable=False)

    ingresada = Column(Boolean, nullable=False, default=False)
    transito_vencido = Column(Boolean, nullable=False, default=False)
    ingreso_parcial_sospechoso = Column(Boolean, nullable=False, default=False)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
