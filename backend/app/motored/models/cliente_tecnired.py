"""
Motored -- modelo `cliente_tecnired`: lista de NIT de clientes Tecnired.

Alimenta el tablero de asesores (indicador "ventas a clientes Tecnired"); el
motor de pedidos NUNCA la lee. A diferencia de los otros maestros, cada carga
REEMPLAZA la lista completa (borra todo e inserta lo nuevo en una sola
transaccion), asi que no hay llave de upsert ni soft-delete.

`nit` guarda el NIT normalizado (ver `schemas/cliente_tecnired.py::
normalizar_nit`), igual que la columna CLIENTE NORMALIZADO del Excel de origen,
para poder cruzarlo con `venta_detalle.cliente_factura` normalizado de la misma
forma.

Dato personal (Ley 1581 de 2012): NIT y razon social de clientes. Solo lo ven
ADMIN y COMPRAS.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.motored.database import MotoredBase


class ClienteTecnired(MotoredBase):
    __tablename__ = "cliente_tecnired"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nit = Column(String(30), unique=True, nullable=False)
    razon_social = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)
