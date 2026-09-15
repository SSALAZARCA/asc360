import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ParametroMetodologiaCreate(BaseModel):
    clave: str
    valor: Any
    vigente_desde: date


class ParametroMetodologiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    valor: Any
    vigente_desde: date
    created_at: Optional[datetime] = None
