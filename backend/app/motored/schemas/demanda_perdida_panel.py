"""
Motored Pedidos — schemas del panel ADMIN de Ventas Perdidas
(sdd/motored-ventas-perdidas-panel, Phase 4, design D2/D4 "Interfaces").

`PersonaRef`/`SucursalRef`/`ReferenciaRef` son las formas mínimas que el
listado necesita para pintar cada dimensión relacionada de una
`DemandaPerdidaBotLinea` sin exponer la entidad completa (`Usuario`/
`Sucursal`/`Referencia`). `PersonaRef.activo`/`SucursalRef.activa` existen
porque el listado del panel deliberadamente NO filtra por actividad (Q1
resuelto en el design): una línea de un asesor o sucursal ya desactivado
sigue apareciendo, y el frontend usa este flag para etiquetarla "(inactivo)"/
"(inactiva)" en vez de ocultarla.

`AnularLineaAdminResponse` (Phase 5, `POST .../anular`) se define acá junto
con el resto porque el design la agrupa en la misma sección "Interfaces" --
no tiene ningún caller todavía en este batch (solo Phase 4's `GET` está en
alcance); queda inerte hasta que Phase 5 la use.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.motored.services.fechas_utc import UtcDatetime


class PersonaRef(BaseModel):
    id: uuid.UUID
    nombre: str
    activo: bool


class SucursalRef(BaseModel):
    id: uuid.UUID
    nombre: str
    activa: bool


class ReferenciaRef(BaseModel):
    id: uuid.UUID
    codigo: str
    nombre: Optional[str] = None


class BotLineaAdminRead(BaseModel):
    linea_id: uuid.UUID
    carga_id: uuid.UUID
    fecha: date
    cantidad: float
    estado: str
    metodo: Optional[str] = None
    created_at: Optional[UtcDatetime] = None

    asesor: PersonaRef
    sucursal: SucursalRef
    referencia: ReferenciaRef

    editado_por: Optional[PersonaRef] = None
    editado_en: Optional[UtcDatetime] = None
    anulado_por: Optional[PersonaRef] = None
    anulado_en: Optional[UtcDatetime] = None


class AnularLineaAdminResponse(BotLineaAdminRead):
    agregado_consistente: bool
