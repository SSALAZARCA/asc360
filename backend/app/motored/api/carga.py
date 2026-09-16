"""
Motored Pedidos — router de carga masiva (sdd/motored-pedidos-cimientos,
Fase 4, ADR-6, owner decision #1).

Recibe FILAS YA ESTRUCTURADAS (`CargaRequest.filas: list[dict]`) para UNA
`entidad` a la vez -- este es el camino usado por `.csv` (parseado en el
browser por el frontend). El parseo de un `.xlsx` crudo tiene su propio par
de endpoints, agregados después (ver "Batch posterior" más abajo). Lo que SÍ
es responsabilidad de este router es la única pieza de lógica que
`services/carga.py` documenta explícitamente como fuera de su propio
alcance: para `referencia`, resolver `proveedor_codigo` -> `proveedor_id`
ANTES de llamar a `procesar_carga`, con UN solo query (no uno por fila).

`validar` es un dry-run puro (`validate_rows` directamente, nunca
`procesar_carga`, que además haría upsert). `carga` re-valida TODO el
archivo server-side (ADR-6: nunca confía en el resultado de `validar` del
cliente) y, si es válido, hace upsert atómico vía `procesar_carga` (que ya
hace el único `db.commit()`).

RBAC: ADMIN|COMPRAS únicamente en ambos endpoints -- esta es una operación
destructiva (all-or-nothing, escribe sobre maestros reales).

--------------------------------------------------------------------------
Batch posterior (owner brief "Excel upload capability"): `/carga/excel` y
`/carga/excel/validar` aceptan el archivo `.xlsx` CRUDO (multipart) en vez de
`filas` ya estructuradas -- `services/carga_excel.py::parse_excel_rows` lo
parsea a la MISMA forma canónica que el camino JSON ya espera, y de ahí en
adelante reutilizan exactamente el mismo pipeline (`_resolve_proveedor_
codigos` -> `validate_rows`/`procesar_carga`) que los endpoints de arriba --
cero lógica de validación/upsert duplicada.
"""
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.proveedor import Proveedor
from app.motored.schemas.carga import CargaRequest, CargaResultado
from app.motored.services.carga import procesar_carga
from app.motored.services.carga_excel import CargaExcelError, LimiteFilasExcedidoError, parse_excel_rows
from app.motored.services.validators import _SCHEMA_BY_ENTIDAD, validate_rows

router = APIRouter(
    prefix="/maestros/{entidad}/carga",
    tags=["motored-carga"],
    dependencies=[Depends(require_motored_ready)],
)

_require_write = require_roles("ADMIN", "COMPRAS")


def _entidad_or_404(entidad: str) -> str:
    if entidad not in _SCHEMA_BY_ENTIDAD:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Maestro desconocido: '{entidad}'")
    return entidad


def _check_size_guards(request: Request, payload: CargaRequest) -> None:
    """Rechaza ANTES de tocar validación/BD -- ni una fila se procesa si el
    archivo excede los límites configurados (spec 'Oversized or wrong-type
    file is rejected before parsing')."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            content_length_bytes = int(content_length)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Header 'Content-Length' inválido",
            )
        max_bytes = settings.MOTORED_MAX_UPLOAD_MB * 1024 * 1024
        if content_length_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"El archivo supera el límite de {settings.MOTORED_MAX_UPLOAD_MB}MB",
            )
    if len(payload.filas) > settings.MOTORED_MAX_UPLOAD_ROWS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El archivo supera el límite de {settings.MOTORED_MAX_UPLOAD_ROWS} filas",
        )


async def _resolve_proveedor_codigos(
    db: AsyncSession, entidad: str, filas: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Para `referencia` ÚNICAMENTE: resuelve `proveedor_codigo` ->
    `proveedor_id` con UN query (`IN (...)`, no uno por fila) antes de
    validar/escribir -- alcance documentado en `services/carga.py`'s
    docstring ('la resolución... es responsabilidad del llamador')."""
    if entidad != "referencia":
        return filas

    codigos = {fila.get("proveedor_codigo") for fila in filas if fila.get("proveedor_codigo")}
    if not codigos:
        return filas

    result = await db.execute(select(Proveedor).where(Proveedor.codigo.in_(codigos)))
    id_by_codigo = {p.codigo: p.id for p in result.scalars().all()}

    resolved = []
    for fila in filas:
        fila = dict(fila)
        codigo = fila.get("proveedor_codigo")
        if codigo in id_by_codigo:
            fila["proveedor_id"] = id_by_codigo[codigo]
        resolved.append(fila)
    return resolved


@router.post("/validar", response_model=CargaResultado)
async def validar_carga(
    entidad: str,
    payload: CargaRequest,
    request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Dry-run: SOLO valida, nunca escribe. Corre `validate_rows`
    directamente (no `procesar_carga`, que además haría upsert+commit)."""
    entidad = _entidad_or_404(entidad)
    _check_size_guards(request, payload)

    filas = await _resolve_proveedor_codigos(db, entidad, payload.filas)
    valid_rows, errors = validate_rows(entidad, filas)

    if errors:
        return CargaResultado(
            ok=False,
            total_filas=len(filas),
            errores=[{"fila": e["fila"], "motivo": e["motivo"]} for e in errors],
        )
    return CargaResultado(ok=True, total_filas=len(filas))


@router.post("", response_model=CargaResultado)
async def carga(
    entidad: str,
    payload: CargaRequest,
    request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Re-valida ENTERO el archivo server-side (ADR-6: nunca confía en el
    payload de `validar` del cliente) y, si es válido, hace upsert atómico
    vía `procesar_carga` (que ya hace el único `db.commit()` -- este
    endpoint NO commitea por su cuenta cuando delega ahí)."""
    entidad = _entidad_or_404(entidad)
    _check_size_guards(request, payload)

    filas = await _resolve_proveedor_codigos(db, entidad, payload.filas)
    usuario_id = uuid.UUID(user.user_id)
    return await procesar_carga(db, entidad, filas, usuario_id)


def _check_content_length_guard(request: Request) -> None:
    """Mismo chequeo de tamaño que `_check_size_guards`, pero SIN el chequeo
    de cantidad de filas -- para el camino Excel, el límite de filas se
    enforza DURANTE el parseo (`parse_excel_rows`, streaming), no después de
    tener `payload.filas` ya materializado en memoria como en el camino
    JSON."""
    content_length = request.headers.get("content-length")
    if content_length is None:
        return
    try:
        content_length_bytes = int(content_length)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header 'Content-Length' inválido",
        )
    max_bytes = settings.MOTORED_MAX_UPLOAD_MB * 1024 * 1024
    if content_length_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el límite de {settings.MOTORED_MAX_UPLOAD_MB}MB",
        )


async def _parse_excel_upload(entidad: str, request: Request, file: UploadFile) -> List[Dict[str, Any]]:
    """Guard de tamaño + parseo, traduciendo cada subclase de
    `CargaExcelError` al status HTTP correcto: `LimiteFilasExcedidoError`
    -> 422 (mismo código que el guard de filas del camino JSON); cualquier
    otra `CargaExcelError` (columna faltante, archivo corrupto, `.xls`,
    extensión no soportada) -> 400, nunca un 500 sin manejar."""
    _check_content_length_guard(request)
    file_bytes = await file.read()
    try:
        return parse_excel_rows(entidad, file.filename, file_bytes)
    except LimiteFilasExcedidoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except CargaExcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/excel/validar", response_model=CargaResultado)
async def validar_carga_excel(
    entidad: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Variante `.xlsx` de `validar_carga`: mismo dry-run puro (`validate_
    rows`, nunca `procesar_carga`), solo cambia cómo llegan las filas."""
    entidad = _entidad_or_404(entidad)
    filas = await _parse_excel_upload(entidad, request, file)

    filas = await _resolve_proveedor_codigos(db, entidad, filas)
    valid_rows, errors = validate_rows(entidad, filas)

    if errors:
        return CargaResultado(
            ok=False,
            total_filas=len(filas),
            errores=[{"fila": e["fila"], "motivo": e["motivo"]} for e in errors],
        )
    return CargaResultado(ok=True, total_filas=len(filas))


@router.post("/excel", response_model=CargaResultado)
async def carga_excel(
    entidad: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Variante `.xlsx` de `carga`: re-valida TODO el archivo server-side y,
    si es válido, hace upsert atómico vía el MISMO `procesar_carga` que usa
    el camino JSON -- una sola fuente de verdad para todo-o-nada."""
    entidad = _entidad_or_404(entidad)
    filas = await _parse_excel_upload(entidad, request, file)

    filas = await _resolve_proveedor_codigos(db, entidad, filas)
    usuario_id = uuid.UUID(user.user_id)
    return await procesar_carga(db, entidad, filas, usuario_id)
