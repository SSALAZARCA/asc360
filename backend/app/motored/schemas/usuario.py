import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class UsuarioCreate(BaseModel):
    nombre: str
    email: str
    password: str
    role: str
    sucursal_ids: List[uuid.UUID] = []


class UsuarioRead(BaseModel):
    """sdd/motored-ventas-perdidas-bot, Phase 4, task 4.5: `email` becomes
    `Optional` -- an `ASESOR_MOSTRADOR` row (Phase 1's nullable web
    credentials) has none, and the new `GET /usuarios?status=pending` list
    can return exactly such rows; without this, serializing one would 500,
    the same class of bug Phase 3 already fixed for `CargaArchivoRead.
    nombre_archivo`. `status`/`phone` mirror the `Usuario` columns
    directly. `telegram_vinculado` is a bool derived from `telegram_id
    is not None` -- the raw `telegram_id` itself is NEVER exposed here
    (design D5: "The raw telegram_id is never exposed"); it has no
    corresponding attribute on `Usuario`, so `_to_read` in
    `api/usuarios.py` sets it explicitly after `model_validate`, not via
    `from_attributes`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    email: Optional[str] = None
    role: str
    activo: bool
    status: str = "approved"
    phone: Optional[str] = None
    telegram_vinculado: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
