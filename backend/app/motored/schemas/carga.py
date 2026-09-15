from typing import Any, Dict, List

from pydantic import BaseModel


class CargaRequest(BaseModel):
    """Payload de la Fase 4: filas YA ESTRUCTURADAS (list[dict]) para una
    `entidad` a la vez. El parseo de un archivo .xlsx crudo a filas queda
    fuera de este slice (ver `app/motored/api/carga.py`)."""

    filas: List[Dict[str, Any]]


class CargaErrorRow(BaseModel):
    fila: int
    motivo: str


class CargaResultado(BaseModel):
    ok: bool
    total_filas: int
    errores: List[CargaErrorRow] = []
    insertados: int = 0
    actualizados: int = 0
    advertencias: List[Any] = []
