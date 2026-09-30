"""
Motored login event log (T10): one row per login attempt (success, failure or
blocked), written by `POST /auth/login` and read by the ADMIN "Registro de
ingresos" screen.

Never stores the password. `motivo` is internal (why a failure failed) and is
never returned to the login caller. Retention: none yet; if the table grows,
prune rows older than N months with a scheduled job (the (created_at desc)
index keeps that cheap).
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase

RESULTADOS = ("EXITO", "FALLO", "BLOQUEADO")


class LoginEvento(MotoredBase):
    __tablename__ = "login_evento"
    __table_args__ = (
        CheckConstraint("resultado IN ('EXITO', 'FALLO', 'BLOQUEADO')", name="ck_login_evento_resultado"),
        Index("ix_login_evento_created_at", text("created_at DESC")),
        Index("ix_login_evento_usuario_created", "usuario_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)  # naive UTC
    email_intentado = Column(String(255), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
    resultado = Column(String(16), nullable=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    motivo = Column(String(32), nullable=True)
