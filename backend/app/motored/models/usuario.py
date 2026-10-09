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
    Index,
    Integer,
    String,
    text,
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
    # Customer-service agent: web role confined to the survey/detractor
    # routes (see `deps.SERVICIO_CLIENTE_ALLOWED_PREFIXES`).
    SERVICIO_CLIENTE = "SERVICIO_CLIENTE"
    # Management: web role confined to budgets and the advisor dashboard (see
    # `deps.GERENCIA_ALLOWED_PREFIXES`).
    GERENCIA = "GERENCIA"
    # Parts coordinator: web role confined to the KPI's and the "Gestión
    # repuestos" section (see `deps.COORDINADOR_REPUESTOS_ALLOWED_PREFIXES`).
    COORDINADOR_REPUESTOS = "COORDINADOR_REPUESTOS"


class Usuario(MotoredBase):
    __tablename__ = "usuario"
    __table_args__ = (
        # Several advisors may share one Telegram (migration a3f7c91d2e58).
        Index("ix_usuario_telegram_id", "telegram_id"),
        Index(
            "uq_usuario_telegram_phone_activo", "telegram_id", "phone",
            unique=True, postgresql_where=text("status <> 'rejected'"),
        ),
        Index(
            "uq_usuario_telegram_admin", "telegram_id",
            unique=True, postgresql_where=text("role = 'ADMIN'"),
        ),
        # One APPROVED usuario per cédula; pending duplicates are allowed
        # (migration c6d2f8a41b97).
        Index(
            "uq_usuario_cedula_aprobada", "cedula",
            unique=True, postgresql_where=text("cedula_aprobada"),
        ),
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

    # Link to the vendedor master (services/cedula_usuario.py). A cédula typed
    # in Lore stays pending until an ADMIN approves it; only an approved one
    # is used to send the daily asesor report.
    cedula = Column(String(20), nullable=True)
    cedula_aprobada = Column(
        Boolean, nullable=False, default=False,
        server_default=text("false"),
    )

    # Naive UTC. Sessions (JWTs) issued before this instant are rejected.
    password_changed_at = Column(DateTime, nullable=True)
    # True after an admin create/reset: only POST /auth/password works until cleared.
    must_change_password = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    # Account lockout (naive UTC). Failed-login counter inside a window that
    # starts at its first failure; `bloqueado_hasta` set on the 5th failure.
    login_fallidos = Column(Integer, nullable=False, default=0, server_default=text("0"))
    login_ventana_inicio = Column(DateTime, nullable=True)
    bloqueado_hasta = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sucursales = relationship(
        "UsuarioSucursal", back_populates="usuario", cascade="all, delete-orphan"
    )
