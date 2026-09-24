"""
Motored Pedidos — modelo `usuario` (sdd/motored-pedidos-cimientos, Fase 3;
sdd/motored-ventas-perdidas-bot, Phase 1 "Schema", design D2/D5).

Tabla de usuarios COMPLETAMENTE independiente de `app.models.user.User` --
sin FK, sin secuencia compartida, sin join posible (motored-isolation,
"Independent user store"). Vive sobre `MotoredBase`, nunca sobre
`app.database.Base`.

`ASESOR_MOSTRADOR` (bot "Lore") is a role with NO web credentials at all --
`email`/`hashed_password` are nullable and `ck_usuario_credenciales_web`
enforces, at the DB level, that every OTHER role still requires both. Bot
self-registration is a `pending -> approved|rejected` status flow
(`status` + `ck_usuario_status`), resolved by `resuelto_por`/`resuelto_en`
(shared by both the web Usuarios screen and the bot's admin approval path,
design D5's `resolver_solicitud`). `telegram_id` links an advisor's (or an
ADMIN's, for push notifications) Telegram account; `codigo_vinculacion_hash`/
`codigo_vinculacion_expira` back the one-time linking code -- only the sha256
is ever stored, never the raw code.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.motored.database import MotoredBase


class MotoredRole(enum.Enum):
    ADMIN = "ADMIN"
    COMPRAS = "COMPRAS"
    SUCURSAL = "SUCURSAL"
    CONSULTA = "CONSULTA"
    ASESOR_MOSTRADOR = "ASESOR_MOSTRADOR"


class Usuario(MotoredBase):
    __tablename__ = "usuario"
    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_usuario_telegram_id"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="ck_usuario_status",
        ),
        CheckConstraint(
            "role = 'ASESOR_MOSTRADOR' OR "
            "(email IS NOT NULL AND hashed_password IS NOT NULL)",
            name="ck_usuario_credenciales_web",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    role = Column(Enum(MotoredRole, name="motored_role"), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)

    telegram_id = Column(BigInteger, nullable=True)
    phone = Column(String(20), nullable=True)
    status = Column(String(16), nullable=False, default="approved")
    resuelto_por = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    resuelto_en = Column(DateTime(timezone=True), nullable=True)
    codigo_vinculacion_hash = Column(String(64), nullable=True)
    codigo_vinculacion_expira = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sucursales = relationship(
        "UsuarioSucursal", back_populates="usuario", cascade="all, delete-orphan"
    )
