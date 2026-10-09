"""
Motored inventory counts -- a bin location inside a store
(odd/motored-conteos-inventario, WU2; design §4.3).

Locations persist across counts so printed labels are reused; the label's
barcode value is `UBI-` + `codigo`. Owner override: the count is per
STORE, so a location belongs to a `sucursal` and has NO bodega column.

`codigo` is stored normalized (trimmed, upper case, not empty;
`ck_ubicacion_inventario_codigo_normalizado`). `origen` is 'LIDER'
(created ahead) or 'PAREJA' (typed ad hoc during a count).
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, String,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase
from app.motored.models.conteo import lista_sql

ORIGENES = ("LIDER", "PAREJA")


class UbicacionInventario(MotoredBase):
    __tablename__ = "ubicacion_inventario"
    __table_args__ = (
        UniqueConstraint(
            "sucursal_id", "codigo", name="uq_ubicacion_inventario_codigo"),
        CheckConstraint(
            "codigo = upper(btrim(codigo)) AND codigo <> ''",
            name="ck_ubicacion_inventario_codigo_normalizado"),
        CheckConstraint(
            f"origen IN {lista_sql(ORIGENES)}",
            name="ck_ubicacion_inventario_origen"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sucursal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sucursal.id", ondelete="RESTRICT"),
        nullable=False,
    )
    codigo = Column(String(30), nullable=False)
    nombre = Column(String(60), nullable=False)
    activa = Column(
        Boolean, nullable=False, default=True,
        server_default=text("true"))
    origen = Column(String(8), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
