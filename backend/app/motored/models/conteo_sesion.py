"""
Motored inventory counts -- device sessions and their people
(odd/motored-conteos-inventario, WU3; design §4.4, §5.3, ADR-3, §8.3).

`conteo_sesion` is one counting device: a PAIR (no user account, stage 1)
or an ASESOR (Lore Mini App, stage 3; `ck_conteo_sesion_asesor_usuario`).
Only the sha256 of the device token is stored.

`conteo_integrante` holds the 1-3 people of a session with their cédula,
normalized with `limpiar_cedula`. The cédula is used ONLY server-side (the
"different pair" rule, ADR-4): it is never returned by any endpoint,
never logged and never exported (Ley 1581).
"""
import uuid

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index,
    SmallInteger, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase
from app.motored.models.conteo import lista_sql

TIPOS = ("PAREJA", "ASESOR")
ESTADOS = ("CONECTADA", "DESCONECTADA", "CERRADA")
DISPOSITIVOS = ("ESCRITORIO", "MOVIL", "MINIAPP")


class ConteoSesion(MotoredBase):
    __tablename__ = "conteo_sesion"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_conteo_sesion_token_hash"),
        CheckConstraint(
            f"tipo IN {lista_sql(TIPOS)}", name="ck_conteo_sesion_tipo"),
        CheckConstraint(
            f"estado IN {lista_sql(ESTADOS)}",
            name="ck_conteo_sesion_estado"),
        CheckConstraint(
            f"dispositivo IN {lista_sql(DISPOSITIVOS)}",
            name="ck_conteo_sesion_dispositivo"),
        CheckConstraint(
            "tipo = 'PAREJA' OR usuario_id IS NOT NULL",
            name="ck_conteo_sesion_asesor_usuario"),
        Index("ix_conteo_sesion_conteo_estado", "conteo_id", "estado"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conteo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conteo.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo = Column(String(8), nullable=False, default="PAREJA")
    token_hash = Column(String(64), nullable=False)
    estado = Column(String(14), nullable=False, default="CONECTADA")
    dispositivo = Column(String(10), nullable=False)
    ubicacion_actual_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ubicacion_inventario.id", ondelete="SET NULL"),
        nullable=True,
    )
    usuario_id = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    telegram_id = Column(BigInteger, nullable=True)
    conectada_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    ultima_actividad_en = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    desconectada_en = Column(DateTime(timezone=True), nullable=True)
    desconectada_por = Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)


class ConteoIntegrante(MotoredBase):
    __tablename__ = "conteo_integrante"
    __table_args__ = (
        UniqueConstraint(
            "sesion_id", "orden", name="uq_conteo_integrante_orden"),
        CheckConstraint(
            "orden BETWEEN 1 AND 3", name="ck_conteo_integrante_orden"),
        Index("ix_conteo_integrante_sesion", "sesion_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sesion_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conteo_sesion.id", ondelete="CASCADE"),
        nullable=False,
    )
    orden = Column(SmallInteger, nullable=False)
    nombre = Column(String(120), nullable=False)
    cedula = Column(String(20), nullable=False)
