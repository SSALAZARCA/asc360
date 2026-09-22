"""
Motored Pedidos — modelo `ingreso_factura` (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra", corregido en
Phase 8 "FACTURAS/INGRESOS + Tránsito"; design §Schema, ADR-9, spec
"Tránsito cruce by RH document identity").

Lado "ingreso" del cruce contra `factura_proveedor_linea` -- misma forma de
prefijo/número (`(prefijo_rh, numero_rh)`, `numero_rh bigint`, H3), sin las
tres columnas booleanas de tránsito (esas viven del lado factura, que es
el que el cruce actualiza).

`sucursal_id`/`referencia_id` son NULLABLE (migración `3956c0ebd69c`,
Phase 8): el archivo real ("ingreso facturas ultimo 45 dias") es a nivel de
DOCUMENTO -- una fila por `Nrodocumento` -- y no trae ninguna columna de
sucursal ni de parte/referencia (a diferencia de `facturas pedidos`, que sí
es a nivel de línea). El cruce mismo (spec §5.6, pseudocódigo del design)
nunca las necesitó: matchea únicamente por `(prefijo_rh, numero_rh)`. Por
eso la clave natural de esta tabla es `UNIQUE(prefijo_rh, numero_rh)`, no
la clave de 4 columnas que sí tiene sentido en `factura_proveedor_linea`
(que sí es a nivel de línea).

`valor_neto` (antes `cantidad`, misma migración): el archivo no trae
ninguna columna de cantidad de unidades -- es un registro financiero por
documento (`Valornetolocal`), no un registro de partes. Es el campo que
`transito.py` compara contra la suma de `valor_total` de
`factura_proveedor_linea` para `ingreso_parcial_sospechoso` (spec §5.6)."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class IngresoFactura(MotoredBase):
    __tablename__ = "ingreso_factura"
    __table_args__ = (
        UniqueConstraint(
            "prefijo_rh", "numero_rh", name="uq_ingreso_factura_prefijo_rh_numero_rh",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prefijo_rh = Column(String(2), nullable=False)
    numero_rh = Column(BigInteger, nullable=False)
    fecha_ingreso = Column(Date, nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=True)
    referencia_id = Column(UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=True)
    valor_neto = Column(Numeric(14, 2), nullable=False)

    carga_id = Column(UUID(as_uuid=True), ForeignKey("carga_archivo.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
