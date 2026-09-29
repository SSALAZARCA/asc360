"""
Motored satisfaction survey (slice T5) -- detractor case management under
`/api/motored/detractores`. ADMIN and SERVICIO_CLIENTE only; the latter is
confined to `/encuesta*` and `/detractores*` by `deps`. Thin router: rules live
in `services/caso_detractor.py`. `GET /` also returns `conteo_por_estado`
(unfiltered, for tab badges) in the same response: one round trip, one small
GROUP BY, and no second endpoint for the UI to keep in sync.
"""
import uuid
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, StringConstraints, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.services import caso_detractor as servicio

router = APIRouter(
    prefix="/detractores",
    tags=["motored-detractores"],
    dependencies=[Depends(require_motored_ready)],
)

_require_access = require_roles("ADMIN", "SERVICIO_CLIENTE")
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


class AccionCreate(BaseModel):
    # APERTURA and CAMBIO_ESTADO are system-only: not accepted here.
    tipo: Literal["LLAMADA", "WHATSAPP", "NOTA", "COMPENSACION", "CORRECCION"]
    descripcion: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]


class EstadoChange(BaseModel):
    estado: Literal["EN_GESTION", "CERRADO"]
    resultado: Optional[Literal["RECUPERADO", "NO_RECUPERADO", "NO_CONTACTABLE"]] = None
    comentario: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=4000)]

    @model_validator(mode="after")
    def _resultado_only_when_closing(self):
        if self.estado == "CERRADO" and self.resultado is None:
            raise ValueError("Al cerrar el caso se debe indicar el resultado")
        if self.estado != "CERRADO" and self.resultado is not None:
            raise ValueError("El resultado solo aplica al cerrar el caso")
        return self


async def _run(coro):
    try:
        return await coro
    except servicio.CasoError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("")
async def listar_casos(
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    estado: Optional[Literal["ABIERTO", "EN_GESTION", "CERRADO"]] = None,
    centro_servicio: Optional[str] = None,
    autoriza_datos: Optional[bool] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
) -> dict:
    return await servicio.listar(
        db, page=page, page_size=page_size, estado=estado, centro_servicio=centro_servicio,
        autoriza_datos=autoriza_datos, desde=desde, hasta=hasta, q=q,
    )


@router.get("/{caso_id}")
async def detalle_caso(
    caso_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
) -> dict:
    return await _run(servicio.detalle(db, caso_id))


@router.post("/{caso_id}/acciones", status_code=status.HTTP_201_CREATED)
async def agregar_accion(
    caso_id: uuid.UUID,
    body: AccionCreate,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
) -> dict:
    return await _run(servicio.agregar_accion(
        db, caso_id, usuario_id=user.user_id, tipo=body.tipo, descripcion=body.descripcion,
    ))


@router.post("/{caso_id}/estado")
async def cambiar_estado(
    caso_id: uuid.UUID,
    body: EstadoChange,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
) -> dict:
    return await _run(servicio.cambiar_estado(
        db, caso_id, usuario_id=user.user_id, estado=body.estado,
        resultado=body.resultado, comentario=body.comentario,
    ))
