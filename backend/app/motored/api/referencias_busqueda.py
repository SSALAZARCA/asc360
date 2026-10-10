"""
Motored Pedidos — lectura paginada de referencias
(`odd/tasks/motored-referencias-paginacion.md`, T1).

Endpoints dedicados en vez de cambiar la forma de `GET /maestros/referencias`
(`maestros.py::list_maestro`), que sigue devolviendo la lista completa sin
paginar para no romper a ningún caller existente:

- `GET /maestros/referencias/buscar`: `{items, total, page, page_size}`.
- `GET /maestros/referencias/lineas-comerciales`: valores distintos.
- `GET /maestros/referencias/sustitutas`: type-ahead del selector de
  sustituta (mismo proveedor, excluyendo la propia referencia).
- `GET /maestros/referencias/exportar.xlsx`: the whole master (or what
  matches the SAME filters as `/buscar`) in the upload template layout
  (`odd/tasks/motored-referencias-descarga-excel.md`).

Mismo gate de lectura que `list_maestro` (los 4 roles autenticados; las
referencias son catálogo compartido, sin scoping por sucursal).

ORDEN DE INCLUSIÓN: `router.py` monta este router ANTES que `maestros`.
Si no, `GET /maestros/referencias/buscar` matchea primero
`/maestros/{entidad}/{entity_id}` y responde 422 (uuid inválido).
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import (
    MotoredUser,
    get_current_motored_user,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.schemas.referencia import ReferenciaRead
from app.motored.services import referencias_busqueda as busqueda
from app.motored.services import referencias_excel
from app.motored.services.corridas.exportacion_hmcl import (
    content_disposition,
)
from app.motored.services.reloj import hoy_bogota

router = APIRouter(
    prefix="/maestros/referencias",
    tags=["motored-maestros"],
    dependencies=[Depends(require_motored_ready)],
)

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


def _item(referencia, sustituta_codigo: Optional[str]) -> dict:
    item = ReferenciaRead.model_validate(referencia).model_dump(mode="json")
    item["sustituta_codigo"] = sustituta_codigo
    return item


@router.get("/buscar")
async def buscar_referencias(
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    q: Optional[str] = None,
    linea_comercial: Optional[str] = None,
    activa: Optional[bool] = None,
    proveedor_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> dict:
    filtros = busqueda.FiltrosReferencia(
        q, linea_comercial, activa, proveedor_id)
    total = await busqueda.contar_referencias(db, filtros)
    filas = await busqueda.pagina_referencias(db, filtros, page, page_size)
    return {
        "items": [_item(referencia, codigo) for referencia, codigo in filas],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/lineas-comerciales")
async def listar_lineas_comerciales(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> List[str]:
    return await busqueda.lineas_comerciales(db)


@router.get("/sustitutas")
async def buscar_sustitutas(
    proveedor_id: uuid.UUID,
    q: Optional[str] = None,
    exclude_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> List[dict]:
    candidatas = await busqueda.buscar_sustitutas(
        db, proveedor_id, q, exclude_id)
    return [
        {"id": str(r.id), "codigo": r.codigo, "nombre": r.nombre}
        for r in candidatas
    ]


@router.get("/exportar.xlsx", response_class=Response)
async def exportar_referencias(
    q: Optional[str] = None,
    linea_comercial: Optional[str] = None,
    activa: Optional[bool] = None,
    proveedor_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> Response:
    """Same filters and read gate as `/buscar`, without paging."""
    filtros = busqueda.FiltrosReferencia(
        q, linea_comercial, activa, proveedor_id)
    filas = await busqueda.filas_exportacion(db, filtros)
    nombre = referencias_excel.nombre_archivo(hoy_bogota())
    return Response(
        referencias_excel.libro(filas),
        media_type=referencias_excel.XLSX,
        headers={
            "Content-Disposition": content_disposition(nombre),
            "Cache-Control": "no-store",
        },
    )
