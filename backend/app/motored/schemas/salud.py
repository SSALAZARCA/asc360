import uuid
from typing import List, Optional

from pydantic import BaseModel


class Hallazgo(BaseModel):
    tipo: str
    entidad: str
    entidad_id: Optional[uuid.UUID] = None
    mensaje: str
    bloqueante: bool


class SaludMaestros(BaseModel):
    estado: str  # "verde" | "advertencia" | "bloqueado"
    hallazgos: List[Hallazgo] = []
