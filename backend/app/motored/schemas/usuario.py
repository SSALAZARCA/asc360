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
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    email: str
    role: str
    activo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
