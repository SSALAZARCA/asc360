"""
Motored satisfaction survey (slice T4) -- PUBLIC, unauthenticated API under
`/api/motored/encuesta/publico`. Customers reach it from a WhatsApp link, so
there is no `get_current_motored_user`; abuse is bounded by a per-IP rate
limit (cedulas are guessable) and by returning minimal data only.
`/identificar` answers HTTP 200 with a discriminated `estado` so the page can
render each screen; `/respuestas` uses 404/409 for the failure cases.
"""
import uuid
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.services import encuesta_publica as servicio

router = APIRouter(
    prefix="/encuesta/publico",
    tags=["motored-encuesta-publica"],
    dependencies=[Depends(require_motored_ready)],
)

# Identification is the enumeration vector: 10/min/IP keeps a real customer
# (a few retries) comfortable but caps guessing at ~14k cedulas/day per IP.
IDENTIFICAR_LIMIT = "10/minute"
# Submitting needs a valid registro_id (uuid) obtained from identification, so
# it is not a guessing vector; looser to tolerate shared workshop Wi-Fi/NAT.
RESPUESTAS_LIMIT = "20/minute"

Score = Field(ge=1, le=5)


class IdentificarRequest(BaseModel):
    cedula: str = Field(min_length=1, max_length=64)


class RegistroPendiente(BaseModel):
    registro_id: uuid.UUID
    placa: str
    linea: Optional[str] = None


class IdentificarResponse(BaseModel):
    estado: Literal["NO_ENCONTRADA", "YA_RESPONDIDA", "PENDIENTE"]
    mensaje: Optional[str] = None
    respondida_at: Optional[datetime] = None
    primer_nombre: Optional[str] = None
    registros: Optional[List[RegistroPendiente]] = None


class RespuestaRequest(BaseModel):
    cedula: str = Field(min_length=1, max_length=64)
    registro_id: uuid.UUID
    satisfaccion_general: int = Score
    p_explicacion_tecnica: Optional[int] = Field(ge=1, le=5)
    p_confianza_reparacion: Optional[int] = Field(ge=1, le=5)
    p_servicio_taller: Optional[int] = Field(ge=1, le=5)
    p_calidad_mecanicos: Optional[int] = Field(ge=1, le=5)
    p_claridad_cobros: Optional[int] = Field(ge=1, le=5)
    p_originalidad_repuestos: Optional[int] = Field(ge=1, le=5)
    observaciones: Optional[str] = Field(default=None)
    autoriza_datos: bool

    @field_validator("observaciones")
    @classmethod
    def _clean_observaciones(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if len(value) > 2000:
            raise ValueError("observaciones supera los 2000 caracteres")
        return value or None


class RespuestaResponse(BaseModel):
    clasificacion: Literal["DETRACTOR", "SATISFECHO"]
    caso_numero: Optional[int] = None
    primer_nombre: str


@router.post("/identificar", response_model=IdentificarResponse, response_model_exclude_none=True)
@limiter.limit(IDENTIFICAR_LIMIT)
async def identificar(
    request: Request,
    payload: IdentificarRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    resultado = await servicio.identificar(db, payload.cedula)
    return IdentificarResponse(
        estado=resultado.estado,
        mensaje=servicio.NOT_FOUND_MESSAGE if resultado.estado == "NO_ENCONTRADA" else None,
        respondida_at=resultado.respondida_at,
        primer_nombre=resultado.primer_nombre,
        registros=resultado.registros,
    )


@router.post("/respuestas", response_model=RespuestaResponse)
@limiter.limit(RESPUESTAS_LIMIT)
async def responder(
    request: Request,
    payload: RespuestaRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    datos = payload.model_dump(exclude={"cedula", "registro_id"})
    try:
        resultado = await servicio.registrar_respuesta(
            db, cedula_raw=payload.cedula, registro_id=payload.registro_id, datos=datos
        )
    except servicio.RegistroNoEncontrado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="REGISTRO_NO_ENCONTRADO")
    except servicio.RespuestaYaRegistrada:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="YA_RESPONDIDA")
    return RespuestaResponse(
        clasificacion=resultado.clasificacion,
        caso_numero=resultado.caso_numero,
        primer_nombre=resultado.primer_nombre,
    )
