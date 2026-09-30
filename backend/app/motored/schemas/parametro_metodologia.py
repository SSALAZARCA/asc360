import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ParametroMetodologiaCreate(BaseModel):
    clave: str
    valor: Any
    vigente_desde: date
    # None = alcance global. Sólo `dias_entre_pedidos` admite sucursal.
    sucursal_id: Optional[uuid.UUID] = None


class ParametroMetodologiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    valor: Any
    vigente_desde: date
    sucursal_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None
