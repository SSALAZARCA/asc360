"""
Motored Pedidos — router de carga masiva (sdd/motored-pedidos-cimientos,
Fase 4, ADR-6, owner decision #1).

Recibe FILAS YA ESTRUCTURADAS (`CargaRequest.filas: list[dict]`) para UNA
`entidad` a la vez -- este es el camino usado por `.csv` (parseado en el
browser por el frontend). El parseo de un `.xlsx` crudo tiene su propio par
de endpoints, agregados después (ver "Batch posterior" más abajo). Lo que SÍ
es responsabilidad de este router es la lógica que `services/carga.py`
documenta explícitamente como fuera de su propio alcance: para `referencia`,
resolver por código dos relaciones ANTES de llamar a `procesar_carga`, cada
una con UN solo query (no uno por fila) -- ver `_resolve_referencia_
relaciones`.

Ad-hoc bugfix (no trackeado bajo ningún sdd/*): `_resolve_referencia_
relaciones` (renombrada desde `_resolve_proveedor_codigos`) ahora también
resuelve `sustituida_por_codigo` -> `sustituida_por`. A diferencia de
`proveedor_codigo` (FK requerida -- un código sin match simplemente deja
`proveedor_id` ausente, y `validate_rows` ya reporta "campo requerido" más
adelante), `sustituida_por` es OPCIONAL en `ReferenciaCreate`: dejar la fila
sin setear cuando el código no matchea sería un fallo SILENCIOSO (la fila
"pasa" igual, solo que sin ese campo) -- exactamente lo que "todo o nada"
(owner decision #1) prohíbe. Por eso esta función devuelve un segundo valor,
`errores_resolucion`, que el caller mezcla con los errores de
`validate_rows` ANTES de decidir todo-o-nada, en los 4 endpoints de abajo.

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
adelante reutilizan exactamente el mismo pipeline (`_resolve_referencia_
relaciones` -> `validate_rows`/`procesar_carga`) que los endpoints de arriba
-- cero lógica de validación/upsert duplicada.
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
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


def entidad_or_404(entidad: str) -> str:
    if entidad not in _SCHEMA_BY_ENTIDAD:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Maestro desconocido: '{entidad}'")
    return entidad


def _check_size_guards(request: Request, payload: CargaRequest) -> None:
    """Rechaza ANTES de tocar validación/BD -- ni una fila se procesa si el
    archivo excede los límites configurados (spec 'Oversized or wrong-type
    file is rejected before parsing'). El chequeo de `Content-Length` en sí
    vive en `_check_content_length_guard` -- compartido con el camino Excel
    (gga: evita que las dos copias diverjan si se ajusta el límite)."""
    _check_content_length_guard(request)
    if len(payload.filas) > settings.MOTORED_MAX_UPLOAD_ROWS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El archivo supera el límite de {settings.MOTORED_MAX_UPLOAD_ROWS} filas",
        )


def _pick_sustituta(
    codigo: str, proveedor_id: Optional[uuid.UUID], candidatas: List[Referencia]
) -> Tuple[Optional[uuid.UUID], Optional[str]]:
    """Elige la referencia sustituta para `codigo` entre `candidatas` (todas
    las referencias existentes con ese código -- la UNIQUE es
    `(codigo, proveedor_id)`, así que puede haber varias). Regla de negocio
    (decisión del usuario, 2026-09-28): la sustituta DEBE ser del MISMO
    proveedor que la fila; un equivalente de otro proveedor/marca va en
    "Homologados otras marcas", nunca como sustituta. Retorna `(id, None)` o
    `(None, motivo_de_error)` -- nunca se descarta en silencio."""
    for candidata in candidatas:
        if proveedor_id is not None and candidata.proveedor_id == proveedor_id:
            return candidata.id, None
    if candidatas:
        return None, (
            f"'Código de referencia sustituta' '{codigo}' existe, pero de otro proveedor. La sustituta "
            "debe ser del mismo proveedor; los equivalentes de otras marcas van en 'Homologados otras marcas'."
        )
    return None, (
        f"'Código de referencia sustituta' '{codigo}' no corresponde a ninguna referencia existente "
        "de este proveedor"
    )


async def _resolve_referencia_relaciones(
    db: AsyncSession, entidad: str, filas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Para `referencia` ÚNICAMENTE: resuelve dos relaciones por código antes
    de validar/escribir, cada una con UN query (`IN (...)`, no uno por fila)
    -- alcance documentado en `services/carga.py`'s docstring ('la
    resolución... es responsabilidad del llamador'). Retorna
    `(filas_resueltas, errores_resolucion)`.

    - `proveedor_codigo` -> `proveedor_id` (FK REQUERIDA en
      `ReferenciaCreate`): un código sin match simplemente deja `proveedor_id`
      ausente de la fila -- `validate_rows` ya reporta un "campo requerido"
      claro más adelante, así que esta función no necesita generar un error
      propio para este caso.
    - `sustituida_por_codigo` -> `sustituida_por` (FK OPCIONAL), elegida por
      `_pick_sustituta` (SOLO del mismo proveedor). A diferencia
      de arriba, dejar la fila silenciosamente sin `sustituida_por` cuando el
      código no matchea violaría "todo o nada" (owner decision #1) -- un
      typo de negocio pasaría desapercibido. Por eso un código sin match acá
      SÍ genera una entrada en `errores_resolucion` (mismo shape `{fila,
      motivo}` 1-indexado que `validate_rows.RowError`), que el caller
      mezcla con los errores de validación antes de decidir todo-o-nada."""
    if entidad != "referencia":
        return filas, []

    proveedor_codigos = {fila.get("proveedor_codigo") for fila in filas if fila.get("proveedor_codigo")}
    sustituida_por_codigos = {
        fila.get("sustituida_por_codigo") for fila in filas if fila.get("sustituida_por_codigo")
    }

    proveedor_id_by_codigo: Dict[str, uuid.UUID] = {}
    if proveedor_codigos:
        result = await db.execute(select(Proveedor).where(Proveedor.codigo.in_(proveedor_codigos)))
        proveedor_id_by_codigo = {p.codigo: p.id for p in result.scalars().all()}

    referencias_by_codigo: Dict[str, List[Referencia]] = {}
    if sustituida_por_codigos:
        result = await db.execute(select(Referencia).where(Referencia.codigo.in_(sustituida_por_codigos)))
        for referencia in result.scalars().all():
            referencias_by_codigo.setdefault(referencia.codigo, []).append(referencia)

    resolved: List[Dict[str, Any]] = []
    errores_resolucion: List[Dict[str, Any]] = []
    for index, fila in enumerate(filas, start=1):
        fila = dict(fila)

        proveedor_codigo = fila.get("proveedor_codigo")
        if proveedor_codigo in proveedor_id_by_codigo:
            fila["proveedor_id"] = proveedor_id_by_codigo[proveedor_codigo]

        sustituida_por_codigo = fila.get("sustituida_por_codigo")
        if sustituida_por_codigo:
            sustituta_id, motivo = _pick_sustituta(
                sustituida_por_codigo, fila.get("proveedor_id"), referencias_by_codigo.get(sustituida_por_codigo, [])
            )
            if sustituta_id is not None:
                fila["sustituida_por"] = sustituta_id
            else:
                errores_resolucion.append({"fila": index, "motivo": motivo})

        resolved.append(fila)
    return resolved, errores_resolucion


async def _validar_y_construir_resultado(
    db: AsyncSession, entidad: str, filas: List[Dict[str, Any]]
) -> CargaResultado:
    """Lógica compartida entre `validar_carga` y `validar_carga_excel` (ad-hoc
    dedupe, no trackeado bajo ningún sdd/*, 2026-09-28): resolver relaciones
    de `referencia` -> `validate_rows` -> mezclar errores -> armar
    `CargaResultado`. Los dos endpoints solo difieren en CÓMO llegan las
    `filas` (JSON ya estructurado vs. parseo de `.xlsx`) -- de ahí en
    adelante es el mismo dry-run puro (nunca `procesar_carga`, que además
    haría upsert+commit)."""
    filas, errores_resolucion = await _resolve_referencia_relaciones(db, entidad, filas)
    _valid_rows, errors = validate_rows(entidad, filas)
    errores_totales = errores_resolucion + errors

    if errores_totales:
        return CargaResultado(
            ok=False,
            total_filas=len(filas),
            errores=[{"fila": e["fila"], "motivo": e["motivo"]} for e in errores_totales],
        )
    return CargaResultado(ok=True, total_filas=len(filas))


async def _resolver_y_procesar_carga(
    db: AsyncSession, entidad: str, filas: List[Dict[str, Any]], usuario_id: uuid.UUID
) -> CargaResultado:
    """Lógica compartida entre `carga` y `carga_excel` (ad-hoc dedupe, no
    trackeado bajo ningún sdd/*, 2026-09-28): resolver relaciones de
    `referencia` y delegar en `procesar_carga` (upsert atómico, único
    `db.commit()`). `errores_resolucion` viaja como `errores_previos` -- por
    sí solo ya alcanza para bloquear TODO el archivo (todo-o-nada), exacto
    igual que un error de `validate_rows`."""
    filas, errores_resolucion = await _resolve_referencia_relaciones(db, entidad, filas)
    return await procesar_carga(db, entidad, filas, usuario_id, errores_previos=errores_resolucion)


@router.post("/validar", response_model=CargaResultado)
async def validar_carga(
    entidad: str,
    payload: CargaRequest,
    request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Dry-run: SOLO valida, nunca escribe -- ver `_validar_y_construir_
    resultado` para la lógica compartida con `validar_carga_excel`."""
    entidad = entidad_or_404(entidad)
    _check_size_guards(request, payload)
    return await _validar_y_construir_resultado(db, entidad, payload.filas)


@router.post("", response_model=CargaResultado)
async def carga(
    entidad: str,
    payload: CargaRequest,
    request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Re-valida ENTERO el archivo server-side (ADR-6: nunca confía en el
    payload de `validar` del cliente) y, si es válido, hace upsert atómico --
    ver `_resolver_y_procesar_carga` para la lógica compartida con
    `carga_excel`."""
    entidad = entidad_or_404(entidad)
    _check_size_guards(request, payload)
    usuario_id = uuid.UUID(user.user_id)
    return await _resolver_y_procesar_carga(db, entidad, payload.filas, usuario_id)


def _check_content_length_guard(request: Request) -> None:
    """Chequeo de `Content-Length` compartido por AMBOS caminos:
    `_check_size_guards` (JSON) lo llama y le suma el chequeo de cantidad de
    filas; el camino Excel lo llama solo, ya que para `.xlsx` el límite de
    filas se enforza DURANTE el parseo (`parse_excel_rows`, streaming), no
    después de tener `payload.filas` ya materializado en memoria como en el
    camino JSON."""
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


_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024  # 1MB -- tamaño de lectura arbitrario, no crítico


async def _read_upload_bounded(file: UploadFile) -> bytes:
    """Lee `file` en bloques de `_UPLOAD_READ_CHUNK_BYTES`, cortando apenas
    el acumulado supera `settings.MOTORED_MAX_UPLOAD_MB` -- nunca mantiene en
    memoria más que el límite configurado (más un bloque) a la vez.

    Ad-hoc bugfix (no trackeado bajo ningún sdd/*, 2026-09-28):
    `_check_content_length_guard` de arriba SOLO rechaza cuando el header
    `Content-Length` está presente y lo supera -- un cliente con
    chunked transfer-encoding (sin ese header) lo esquivaba por completo, y
    el viejo `await file.read()` sin límite leía TODO el archivo a memoria
    sin ningún tope propio. Este helper es el backstop real: el chequeo de
    header sigue siendo el fast-path barato para el caso común, este es la
    segunda defensa para cuando el header miente o no está."""
    max_bytes = settings.MOTORED_MAX_UPLOAD_MB * 1024 * 1024
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"El archivo supera el límite de {settings.MOTORED_MAX_UPLOAD_MB}MB",
            )
    return b"".join(chunks)


async def _parse_excel_upload(entidad: str, request: Request, file: UploadFile) -> List[Dict[str, Any]]:
    """Guard de tamaño + parseo, traduciendo cada subclase de
    `CargaExcelError` al status HTTP correcto: `LimiteFilasExcedidoError`
    -> 422 (mismo código que el guard de filas del camino JSON); cualquier
    otra `CargaExcelError` (columna faltante, archivo corrupto, `.xls`,
    extensión no soportada) -> 400, nunca un 500 sin manejar.

    `_check_content_length_guard` es un fast-path barato para el caso común
    (header presente); `_read_upload_bounded` es el backstop real que
    enforza el límite leyendo en bloques, sin importar si el header está,
    falta, o miente (chunked transfer-encoding)."""
    _check_content_length_guard(request)
    file_bytes = await _read_upload_bounded(file)
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
    """Variante `.xlsx` de `validar_carga`: mismo dry-run puro -- ver
    `_validar_y_construir_resultado`, solo cambia cómo llegan las filas."""
    entidad = entidad_or_404(entidad)
    filas = await _parse_excel_upload(entidad, request, file)
    return await _validar_y_construir_resultado(db, entidad, filas)


@router.post("/excel", response_model=CargaResultado)
async def carga_excel(
    entidad: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Variante `.xlsx` de `carga`: re-valida TODO el archivo server-side y,
    si es válido, hace upsert atómico -- ver `_resolver_y_procesar_carga`,
    la MISMA lógica que usa el camino JSON, una sola fuente de verdad para
    todo-o-nada."""
    entidad = entidad_or_404(entidad)
    filas = await _parse_excel_upload(entidad, request, file)
    usuario_id = uuid.UUID(user.user_id)
    return await _resolver_y_procesar_carga(db, entidad, filas, usuario_id)
