"""
Payloads of the Errores tab actions that fix a carga before revalidating
it (odd/tasks/motored-cargas-revalidar.md, R1).

`AccionResolucion` extends the original `ResolverErroresAccion` with the
two optional fields of "Crear referencia": the línea comercial and the
proveedor. Both are optional so an older client that sends neither keeps
working (see `api/cargas.py::_aplicar_creacion_referencia`).
"""
import uuid
from typing import List, Optional

from pydantic import BaseModel

from app.motored.schemas.ingesta import ResolverErroresAccion


class AccionResolucion(ResolverErroresAccion):
    linea_comercial: Optional[str] = None
    proveedor_id: Optional[uuid.UUID] = None


class ResolverAccionesRequest(BaseModel):
    acciones: List[AccionResolucion]


class LineaComercialOpcion(BaseModel):
    """One configured línea comercial: `valor` is the text to send back,
    `etiqueta` what the select shows."""

    valor: str
    etiqueta: str
