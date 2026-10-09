"""
Motored inventory counts -- failed joins per count and client
(odd/motored-conteos-inventario, WU3; design §4.7, §8.2).

Backs the brute-force lock on the 6-digit code: 5 failures in 15 minutes
lock that client for 15 minutes. `cliente` is the sha256 of the client
IP; the raw IP is never stored.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class ConteoAccesoIntento(MotoredBase):
    __tablename__ = "conteo_acceso_intento"

    conteo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conteo.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cliente = Column(String(64), primary_key=True)
    fallidos = Column(
        Integer, nullable=False, default=0, server_default=text("0"))
    ventana_inicio = Column(DateTime(timezone=True), nullable=False)
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)
