"""
Motored satisfaction survey (slice T3) -- customer-base Excel upload under
`/api/motored/encuesta/cargas`. ADMIN and SERVICIO_CLIENTE only (the latter is
confined to `/encuesta*` and `/detractores*` by `deps`).

`/validar` is a pure dry run; `POST /` re-validates the whole file server-side
and, only when it is fully valid, writes one `encuesta_carga` plus its
`encuesta_registro` rows in a single transaction (all-or-nothing, like the
masters upload). Invalid files answer HTTP 200 with `ok: false`.
"""
import io
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api.carga import _check_content_length_guard, _read_upload_bounded
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.models.encuesta_respuesta import EncuestaRespuesta
from app.motored.models.usuario import Usuario
from app.motored.schemas.carga import CargaResultado
from app.motored.services import encuesta_carga as servicio
from app.motored.services import encuesta_excel, encuesta_resultados
from app.motored.services.carga_excel import CargaExcelError, LimiteFilasExcedidoError
from app.motored.services.fechas_utc import UtcDatetime
from app.motored.services.encuesta_resultados import MAX_RANGO_DIAS, Filtro, Por

router = APIRouter(
    prefix="/encuesta/cargas",
    tags=["motored-encuesta"],
    dependencies=[Depends(require_motored_ready)],
)

_require_access = require_roles("ADMIN", "SERVICIO_CLIENTE")
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class EncuestaCargaResultado(CargaResultado):
    carga_id: Optional[uuid.UUID] = None


class EncuestaDetalleFila(BaseModel):
    cliente: str
    cedula: str
    telefono: Optional[str] = None
    tienda: Optional[str] = None
    estado: Literal["RESPONDIDA", "SIN_RESPONDER"]
    nota: Optional[int] = None
    categoria: Optional[Literal["DETRACTOR", "SATISFECHO"]] = None
    comentario: Optional[str] = None
    fecha_respuesta: Optional[UtcDatetime] = None


class EncuestaCargaRead(BaseModel):
    id: uuid.UUID
    nombre_archivo: str
    total_registros: int
    created_at: Optional[UtcDatetime] = None
    usuario: Optional[str] = None
    respondidos: int


async def _parse_upload(request: Request, file: UploadFile) -> List[Dict[str, Any]]:
    _check_content_length_guard(request)
    file_bytes = await _read_upload_bounded(file)
    try:
        return servicio.parse_encuesta_excel(file.filename, file_bytes)
    except LimiteFilasExcedidoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except CargaExcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/plantilla")
async def descargar_plantilla(user: MotoredUser = Depends(_require_access)):
    workbook = Workbook()
    workbook.active.append(servicio.column_labels())
    buffer = io.BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="plantilla_encuesta.xlsx"'},
    )


@router.post("/validar", response_model=EncuestaCargaResultado)
async def validar_carga(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
):
    filas = await _parse_upload(request, file)
    registros, errores = servicio.validar_filas(filas)
    return EncuestaCargaResultado(
        ok=not errores,
        total_filas=len(filas),
        errores=errores,
        advertencias=servicio.advertencias_de(registros),
    )


@router.post("", response_model=EncuestaCargaResultado)
async def cargar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
):
    filas = await _parse_upload(request, file)
    registros, errores = servicio.validar_filas(filas)
    if errores:
        return EncuestaCargaResultado(ok=False, total_filas=len(filas), errores=errores)

    carga = EncuestaCarga(
        id=uuid.uuid4(),
        nombre_archivo=(file.filename or "carga.xlsx")[:255],
        total_registros=len(registros),
        usuario_id=uuid.UUID(user.user_id),
    )
    db.add(carga)
    # No relationship() between these models, so flush the parent first:
    # insert order across tables is not guaranteed to follow the foreign key.
    await db.flush()
    for registro in registros:
        db.add(EncuestaRegistro(carga_id=carga.id, **registro))
    await db.commit()
    return EncuestaCargaResultado(
        ok=True,
        total_filas=len(filas),
        insertados=len(registros),
        advertencias=servicio.advertencias_de(registros),
        carga_id=carga.id,
    )


@router.get("", response_model=List[EncuestaCargaRead])
async def listar_cargas(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
):
    respondidos = (
        select(func.count(EncuestaRespuesta.id))
        .join(EncuestaRegistro, EncuestaRegistro.id == EncuestaRespuesta.registro_id)
        .where(EncuestaRegistro.carga_id == EncuestaCarga.id)
        .correlate(EncuestaCarga)
        .scalar_subquery()
    )
    stmt = (
        select(
            EncuestaCarga.id,
            EncuestaCarga.nombre_archivo,
            EncuestaCarga.total_registros,
            EncuestaCarga.created_at,
            Usuario.nombre.label("usuario_nombre"),
            respondidos.label("respondidos"),
        )
        .outerjoin(Usuario, Usuario.id == EncuestaCarga.usuario_id)
        .order_by(EncuestaCarga.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        EncuestaCargaRead(
            id=row.id,
            nombre_archivo=row.nombre_archivo,
            total_registros=row.total_registros,
            created_at=row.created_at,
            usuario=row.usuario_nombre,
            respondidos=row.respondidos or 0,
        )
        for row in result.all()
    ]


def _xlsx(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=encuesta_excel.XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/resultados/excel")
async def excel_por_rango(
    desde: date,
    hasta: date,
    por: Por = "envio",
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
):
    if desde > hasta:
        raise HTTPException(status_code=422, detail="La fecha desde no puede ser posterior a la fecha hasta")
    if (hasta - desde).days + 1 > MAX_RANGO_DIAS:
        raise HTTPException(status_code=422, detail=f"El rango no puede superar {MAX_RANGO_DIAS} días")
    rows = await encuesta_resultados.filas_de_rango(db, desde, hasta, por)
    content = encuesta_excel.construir_por_rango(rows, desde, hasta, por, datetime.now(timezone.utc))
    return _xlsx(content, encuesta_excel.nombre_por_rango(desde, hasta, por))


@router.get("/{carga_id}/detalle", response_model=List[EncuestaDetalleFila])
async def detalle_carga(
    carga_id: uuid.UUID,
    filtro: Filtro = "todas",
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
):
    rows = await encuesta_resultados.filas_de_carga(db, carga_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Carga no encontrada")
    return encuesta_resultados.filtrar([encuesta_resultados.fila_de(r) for r in rows], filtro)


@router.get("/{carga_id}/excel")
async def excel_de_carga(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_access),
):
    rows = await encuesta_resultados.filas_de_carga(db, carga_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Carga no encontrada")
    return _xlsx(encuesta_excel.construir_por_carga(rows), encuesta_excel.nombre_por_carga(rows))
