import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


PASSWORD_MIN_LENGTH = 8
# bcrypt only accepts 72 BYTES (UTF-8); bcrypt 5 raises above that.
PASSWORD_MAX_BYTES = 72


class UsuarioPasswordReset(BaseModel):
    """Body de `POST /usuarios/{id}/password`. El largo mínimo se valida en
    el endpoint (no con `Field(min_length=...)`) porque el 422 automático de
    pydantic devuelve el valor recibido, y una contraseña nunca debe viajar
    de vuelta en una respuesta."""

    password: str


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
