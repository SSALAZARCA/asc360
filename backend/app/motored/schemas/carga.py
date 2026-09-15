from typing import Any, List

from pydantic import BaseModel


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
