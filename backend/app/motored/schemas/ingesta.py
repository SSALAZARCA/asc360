"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.4
(sdd/motored-pedidos-ingesta; design §API, §Schema, ADR-9). Narrowed by
Fase 3 "Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-declarado; design
D1): `tipo` es DECLARADO por el caller en `POST /cargas`, nunca inferido ni
completado después -- `CargaArchivoSubidaResponse` ya no necesita informar
`tipo_detectado`/`requiere_tipo`/`requiere_periodo` (el caller ya sabe su
propio `tipo`, y por lo tanto si declara período, antes de subir el
archivo), y `CargaArchivoPatch` ya no acepta `tipo`.

Formas de request/response para `/api/motored/cargas` -- separado de
`schemas/carga.py` (Fase 1, `CargaRequest`/`CargaResultado`, filas
JSON/Excel de maestros) porque este es un surface DISTINTO (subida de
archivo binario + período declarado + estado de un job en background),
nunca la misma forma que el camino todo-o-nada de Fase 1.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class CargaArchivoSubidaResponse(BaseModel):
    """`202` de `POST /cargas` (`sdd/motored-cargas-tipo-declarado/design`,
    D3: "response narrows to `{carga_id, duplicado_de}`")."""

    carga_id: uuid.UUID
    duplicado_de: Optional[uuid.UUID] = None


class CargaArchivoPatch(BaseModel):
    """`PATCH /cargas/{id}` -- completa el período mientras `estado` sigue
    `PENDIENTE` (ADR-9, E10: 409 fuera de ese estado). `tipo` fue removido
    (design D1): se declara upfront en `POST /cargas`, nunca queda
    pendiente de completar."""

    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None


class CargaArchivoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: Optional[str]
    origen: str = "EXCEL"
    nombre_archivo: Optional[str]
    estado: str
    filas_leidas: int
    filas_validas: int
    filas_rechazadas: int
    periodo_desde: Optional[date]
    periodo_hasta: Optional[date]
    lotes_staged: int
    ultimo_lote_aplicado: int
    latido_en: Optional[datetime]
    aplicado_en: Optional[datetime]
    created_at: datetime


class CargaErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fila: int
    columna: Optional[str]
    valor: Optional[str]
    codigo_error: str
    mensaje: str


class CargaInformeResponse(BaseModel):
    """Informe previo (dry-run) -- design §API `GET /cargas/{id}/informe`:
    conteos, período declarado vs. detectado, variación vs. la carga
    anterior del MISMO tipo, y cualquier default de `parametro_
    metodologia` usado (registrado en `log` por `parametros.resolver`)."""

    id: uuid.UUID
    tipo: Optional[str]
    estado: str
    filas_leidas: int
    filas_validas: int
    filas_rechazadas: int
    periodo_desde: Optional[date]
    periodo_hasta: Optional[date]
    log: Dict[str, Any] = {}
    variacion_pct_vs_carga_anterior: Optional[float] = None


class ResolverErroresAccion(BaseModel):
    """Una acción por error (spec 'Error-resolution actions'): mapear a una
    sucursal existente, crear la referencia bajo `OTROS`, o ignorar."""

    codigo_error: str
    valor: Optional[str] = None
    accion: str  # "mapear_sucursal" | "crear_referencia" | "ignorar"
    sucursal_id: Optional[uuid.UUID] = None


class ResolverErroresRequest(BaseModel):
    acciones: List[ResolverErroresAccion]


class ResolverErroresResultado(BaseModel):
    acciones_aplicadas: int
    acciones_ignoradas: int = 0
