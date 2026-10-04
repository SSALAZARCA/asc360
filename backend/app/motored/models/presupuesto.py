"""
Motored -- sales budgets per asesor per month (odd/motored-presupuestos-
gerencia, T2).

`presupuesto_version` is the header of one version of one month: every upload
or manual edit inserts a NEW header (next `version` for that `mes`) with ALL of
that month's lines; old versions are never touched, so the header doubles as
the audit trail (who, when, origin, file, note). The latest version of a month
(max `version`) is the one indicators read.

`presupuesto_linea` is one asesor's budget in that version. `cedula` is the
key (not `vendedor.id`): one person can have several vendedor rows (one per ERP
name), all sharing the cedula. `sucursal_id` is the store the asesor is
assigned to FOR THAT MONTH; a store's budget is the sum of its lines.

Dato personal (Ley 1581 de 2012): cedula. Solo ADMIN y GERENCIA.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase

ORIGEN_EXCEL = "EXCEL"
ORIGEN_MANUAL = "MANUAL"


class PresupuestoVersion(MotoredBase):
    __tablename__ = "presupuesto_version"
    __table_args__ = (
        UniqueConstraint("mes", "version", name="uq_presupuesto_version_mes_version"),
        CheckConstraint("EXTRACT(DAY FROM mes) = 1", name="ck_presupuesto_version_mes_dia_1"),
        CheckConstraint("version >= 1", name="ck_presupuesto_version_positiva"),
        CheckConstraint("origen IN ('EXCEL', 'MANUAL')", name="ck_presupuesto_version_origen"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mes = Column(Date, nullable=False)
    version = Column(Integer, nullable=False)
    origen = Column(String(10), nullable=False)
    archivo_nombre = Column(String(255), nullable=True)
    nota = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)


class PresupuestoLinea(MotoredBase):
    __tablename__ = "presupuesto_linea"
    __table_args__ = (
        UniqueConstraint("version_id", "cedula", name="uq_presupuesto_linea_version_cedula"),
        CheckConstraint("monto > 0", name="ck_presupuesto_linea_monto_positivo"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(
        UUID(as_uuid=True), ForeignKey("presupuesto_version.id", ondelete="CASCADE"), nullable=False)
    cedula = Column(String(20), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False)
    monto = Column(BigInteger, nullable=False)
