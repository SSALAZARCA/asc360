"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), tasks
9.3/9.4/9.5/9.6 (sdd/motored-pedidos-ingesta; design ADR-5/ADR-9, §API).
Narrowed by Fase 3 "Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-
declarado; design D1): `tipo` es ahora DECLARADO por el caller en `POST
/cargas`, nunca inferido -- ver docstring de `subir_carga` y `_despachar_
si_completa` para el detalle de qué cambió.

`/api/motored/cargas` -- el surface de Fase 2 para los 6 `tipo` de
movimiento de `carga_archivo` (spec "Per-type upload surface with shared
carga_archivo history"). `MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS` NO son
alcanzables acá desde este cambio -- ver `orquestador.TIPOS_MAESTRO`/
`orquestador.ejecutar_maestro`, preservados sin modificar mas inalcanzables
por constraint del owner (proposal, decisión #3). **CREATE, no MODIFY** de
`api/carga.py` (singular, Fase 1's masters endpoint) -- confirmado por
`sdd/motored-pedidos-ingesta/design-addendum` (Correction 1): ese archivo
queda byte-a-byte sin tocar (ADR-5).

RBAC (spec "RBAC on ingest endpoints"): `ADMIN`/`COMPRAS` únicamente para
subir/completar tipo-período/resolver errores/aplicar/anular -- operaciones
que escriben o disparan una escritura. `SUCURSAL`/`CONSULTA` tienen acceso
de solo lectura a cargas/informes/errores/preview, con `SUCURSAL` scopeado
a las filas de su(s) propia(s) sucursal(es) (T19, hot spot histórico --
la verificación de `sdd/motored-pedidos-cimientos` ya encontró un defecto
real de branch-scoping ahí).

Anulación (spec "Anulación guard"): desde Fase 3 S7 (sdd/motored-pedidos-
motor, ADR-11) la anulación de una carga EXCEL pasa por
`services.corridas.guardas.aplicar_guard_anulacion`: si una corrida CERRADA
usó la carga responde 409 E-CARGA-050 (carga intacta); las corridas vivas
que la usaron quedan invalidadas y la anulación sigue. Sin corridas
vinculadas el camino es el de Fase 2, sin cambios. La rama BOT no pasa por
la guarda (sus cabeceras no se vinculan a corridas).

Decisión documentada -- scoping de `GET /cargas` (lista): `carga_archivo`
NO tiene una dimensión de sucursal (un archivo puede tocar muchas/todas las
sucursales a la vez) -- a diferencia de `carga_error`/`carga_fila_staging`,
que sí resuelven una sucursal POR FILA. Por eso el scoping SUCURSAL se
aplica en `errores`/`errores.csv` (vía `_filtrar_errores_por_sucursal`),
nunca en la lista de cargas en sí, que es visible completa para los 4
roles -- igual criterio "el header no es de una sucursal, las filas sí" que
ya separa `carga_archivo` de `carga_fila_staging` en el propio schema.

Decisión documentada -- fail-closed en `_filtrar_errores_por_sucursal`: un
error cuya fila NO tiene `sucursal_id` resuelta en staging (el caso
`SUCURSAL_NO_ENCONTRADA`, por definición) o que es un error de archivo
completo (`fila=0`, p.ej. columna obligatoria faltante o período
rechazado) NUNCA se muestra a un usuario SUCURSAL -- no hay forma de
probar que esa fila es de SU sucursal, así que se prefiere ocultarla a
arriesgar filtrar la de otra (nunca al revés).

El mismo criterio aplica a `GET /{carga_id}/preview` (`_filtrar_staging_
por_sucursal`): a diferencia de `carga_archivo`, `carga_fila_staging` SÍ
resuelve una sucursal POR FILA -- es la misma tabla y el mismo campo que
justifican el filtro de `errores`/`errores.csv`, así que un usuario
SUCURSAL nunca debe poder leer el payload crudo (cantidades, valores) de
una fila de otra sucursal a través de este endpoint.
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.deps import (
    MotoredUser,
    get_current_motored_user,
    get_motored_db_or_503,
    require_motored_ready,
    require_roles,
)
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.schemas.referencia import ReferenciaUpdate
from app.motored.schemas.ingesta import (
    AsignacionLineaItem,
    AsignarLineaRequest,
    CargaArchivoPatch,
    CargaArchivoRead,
    CargaArchivoSubidaResponse,
    CargaErrorRead,
    CargaInformeResponse,
    DeclaracionSinDatosRequest,
    ResolverErroresRequest,
    ReferenciasSinLineaResponse,
    ResolverErroresResultado,
    VaciadoPrevistoRead,
)
from app.motored.services import parametros, parametros_claves, tablero_comisiones
from app.motored.services import demanda_perdida_bot as demanda_perdida_bot_mod
from app.motored.services import kpi_resumen
from app.motored.services import maestros as maestros_mod
from app.motored.services import storage
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.corridas.guardas import aplicar_guard_anulacion
from app.motored.services.ingesta import deteccion as deteccion_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import lector as lector_mod
from app.motored.services.ingesta import orquestador
from app.motored.services.ingesta import periodo as periodo_mod
from app.motored.services.ingesta import plantillas as plantillas_mod
from app.motored.services.ingesta import resolucion as resolucion_mod
from app.motored.services.ingesta import sin_datos as sin_datos_mod
from app.motored.services.ingesta import ventas_lineas as lineas_mod
from app.motored.services.trabajos.runner import JobRunner, SupervisorRunner

router = APIRouter(
    prefix="/cargas",
    tags=["motored-cargas"],
    dependencies=[Depends(require_motored_ready)],
)

_require_write = require_roles("ADMIN", "COMPRAS")


def get_job_runner() -> JobRunner:
    """Seam inyectable (mismo criterio que `get_motored_user_lookup`):
    producción usa `SupervisorRunner` (ADR-1); la suite de tests entera
    override-ea a `InlineRunner` vía `app.dependency_overrides`, así ningún
    test funcional necesita el supervisor real."""
    return SupervisorRunner()


def _check_content_length_guard(request: Request) -> None:
    """Mismo criterio que `api/carga.py::_check_content_length_guard`, con
    el límite propio de movimiento (150MB, más permisivo que el de
    maestros) -- el `tipo` real todavía no se conoce en este punto."""
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
    max_bytes = settings.MOTORED_MAX_MOVIMIENTO_UPLOAD_MB * 1024 * 1024
    if content_length_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el límite de {settings.MOTORED_MAX_MOVIMIENTO_UPLOAD_MB}MB",
        )


def _check_periodo_no_futuro(periodo_desde: Optional[date], periodo_hasta: Optional[date]) -> None:
    """ADR-9, E7: período futuro es `422` ANTES de escribir nada (para
    `POST`, antes de la subida a MinIO; para `PATCH`, antes de commitear)."""
    hoy = date.today()
    if (periodo_desde and periodo_desde > hoy) or (periodo_hasta and periodo_hasta > hoy):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": periodo_mod.CODIGO_PERIODO_FUTURO,
                "message": "El período declarado no puede estar en el futuro.",
            },
        )


async def _carga_or_404(db: AsyncSession, carga_id: uuid.UUID) -> CargaArchivo:
    result = await db.execute(select(CargaArchivo).where(CargaArchivo.id == carga_id))
    carga = result.scalars().first()
    if carga is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carga no encontrada.")
    return carga


def _requiere_periodo(tipo: Optional[str], periodo_desde: Optional[date]) -> bool:
    return tipo in periodo_mod.TIPOS_QUE_DECLARAN_PERIODO and periodo_desde is None


async def _despachar_si_completa(carga: CargaArchivo, job_runner: JobRunner) -> None:
    """Único punto de decisión "¿ya se puede encolar esta carga?" -- usado
    tanto por `POST` (recién subida) como por `PATCH` (período completado
    después). `carga.tipo` es SIEMPRE uno de los 6 tipos de movimiento en
    este flujo (ver el allow-list de `subir_carga` contra `orquestador.
    TIPOS_MOVIMIENTO`) -- se encola vía `JobRunner` SOLO si el gate de
    ADR-9 ya está satisfecho; si no, la fila queda `PENDIENTE`, sin tocar.

    El branch `MAESTRO_*` que antes vivía acá -- despachando síncrono vía
    `orquestador.ejecutar_maestro`, con su propia descarga desde MinIO -- es
    ahora ESTRUCTURALMENTE INALCANZABLE (`sdd/motored-cargas-tipo-
    declarado/proposal`, decisión #3): `MAESTRO_REFERENCIAS`/`MAESTRO_
    BODEGAS` se rechazan en la puerta de `POST /cargas`, antes de que
    exista una fila `carga_archivo`. `orquestador.TIPOS_MAESTRO`/
    `orquestador.ejecutar_maestro` siguen en el repo, sin modificar, por
    constraint del owner -- este es el pointer comment que ese constraint
    pide dejar en el ahora-muerto call site."""
    if not _requiere_periodo(carga.tipo, carga.periodo_desde):
        await job_runner.enqueue(carga.id, carga.tipo)


def _verificar_tipo_o_400(tipo: str, file_bytes: bytes) -> None:
    """Verificación por firma de encabezado contra el tipo DECLARADO (spec
    "Declared type with content verification") -- reemplaza la vieja
    `_detectar_tipo_o_400` (inferencia, spec previa "Unrecognized headers
    force manual selection", ya no aplica: `tipo` nunca es `None` acá). Un
    archivo genuinamente ilegible por `openpyxl` sigue siendo `400`; un
    archivo legible que no verifica contra `tipo` también, con el detalle
    estructurado que la spec exige ("names the declared type and the
    specific missing expected columns")."""
    try:
        filas_muestra = deteccion_mod.extraer_filas_muestra(
            file_bytes, columnas_esperadas=deteccion_mod.columnas_esperadas_de(tipo)
        )
    except lector_mod.LecturaMovimientoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    try:
        deteccion_mod.verificar_tipo(tipo, filas_muestra)
    except deteccion_mod.TipoNoCoincideError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "tipo_declarado": exc.tipo_declarado,
                "sin_coincidencia": exc.sin_coincidencia,
                "columnas_faltantes": exc.columnas_faltantes,
            },
        )


def _subir_a_minio_o_502(carga_id: uuid.UUID, tipo: str, file_bytes: bytes):
    try:
        return storage.subir_archivo(carga_id, tipo, io.BytesIO(file_bytes))
    except storage.SubidaArchivoError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


async def _buscar_duplicado(db: AsyncSession, hash_sha256: str) -> Optional[uuid.UUID]:
    """Spec "Duplicate sha256 → ask, never block" -- solo INFORMA cuál fue
    la carga anterior con el mismo hash, nunca impide la subida."""
    duplicado = await db.execute(
        select(CargaArchivo.id)
        .where(CargaArchivo.hash_sha256 == hash_sha256)
        .order_by(CargaArchivo.created_at.desc())
        .limit(1)
    )
    return duplicado.scalars().first()


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CargaArchivoSubidaResponse)
async def subir_carga(
    request: Request,
    tipo: str = Form(...),
    file: UploadFile = File(...),
    periodo_desde: Optional[date] = Form(None),
    periodo_hasta: Optional[date] = Form(None),
    reemplaza_mes_completo: bool = Form(False),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
    job_runner: JobRunner = Depends(get_job_runner),
):
    """`POST /cargas` (`sdd/motored-cargas-tipo-declarado/design`, D1/D3):
    `tipo` es DECLARADO por el caller (la pestaña que inició la subida),
    restringido a los 6 tipos de movimiento (`orquestador.TIPOS_MOVIMIENTO`)
    -- nunca inferido, nunca `None`. Cualquier valor fuera de esa lista,
    incluidos `MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS`, se rechaza ACÁ, antes
    de leer el archivo, calcular su hash o subirlo a MinIO (spec "Missing
    tipo is rejected before storage" / "A MAESTRO_* value is rejected at
    the door"). Un archivo que no verifica contra el `tipo` declarado
    también es `400`, con el mismo `no-write` guarantee (`_verificar_tipo_
    o_400`)."""
    _check_content_length_guard(request)
    _check_periodo_no_futuro(periodo_desde, periodo_hasta)
    if tipo not in orquestador.TIPOS_MOVIMIENTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{tipo}' no es un tipo de movimiento válido para este endpoint. "
                "Bodegas y Referencias se suben desde su propia pestaña en Maestros."
            ),
        )
    if periodo_hasta is None:
        periodo_hasta = periodo_desde

    file_bytes = await file.read()
    _verificar_tipo_o_400(tipo, file_bytes)

    carga_id = uuid.uuid4()
    resultado_subida = _subir_a_minio_o_502(carga_id, tipo, file_bytes)
    duplicado_de = await _buscar_duplicado(db, resultado_subida.hash_sha256)

    carga = CargaArchivo(
        id=carga_id,
        tipo=tipo,
        nombre_archivo=file.filename or "archivo.xlsx",
        hash_sha256=resultado_subida.hash_sha256,
        ruta_objeto=resultado_subida.ruta_objeto,
        bytes=len(file_bytes),
        estado="PENDIENTE",
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        subido_por=uuid.UUID(user.user_id),
        # Solo VENTAS reemplaza meses; en los demas tipos se ignora.
        log=({orquestador.CLAVE_REEMPLAZA_MES: True}
             if reemplaza_mes_completo and tipo == "VENTAS" else None),
    )
    db.add(carga)
    await db.commit()

    await _despachar_si_completa(carga, job_runner)

    return CargaArchivoSubidaResponse(
        carga_id=carga.id,
        duplicado_de=duplicado_de,
    )


@router.post(
    "/sin-datos",
    status_code=status.HTTP_201_CREATED,
    response_model=CargaArchivoRead,
)
async def declarar_sin_datos(
    payload: DeclaracionSinDatosRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Declare that HMCL has no backorder, facturas or ingresos at
    `fecha`: an APLICADO carga with zero rows that the corrida preflight
    accepts like any other, auditable and anulable. See
    `services.ingesta.sin_datos`."""
    try:
        carga = await sin_datos_mod.declarar_sin_datos(
            db, payload.tipo, payload.fecha, uuid.UUID(user.user_id))
    except sin_datos_mod.DeclaracionInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc))
    except sin_datos_mod.DeclaracionEnConflicto as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    await db.commit()
    return CargaArchivoRead.model_validate(carga)


@router.patch("/{carga_id}", response_model=CargaArchivoRead)
async def actualizar_carga(
    carga_id: uuid.UUID,
    payload: CargaArchivoPatch,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
    job_runner: JobRunner = Depends(get_job_runner),
):
    """`PATCH /cargas/{id}` (ADR-9): completa el período SOLO mientras
    `estado='PENDIENTE'` -- `409` en cualquier otro estado (E10, el período
    queda congelado apenas empieza a parsearse). Ya NO completa `tipo` --
    `tipo` se declara upfront en `POST /cargas` y nunca queda pendiente
    (`sdd/motored-cargas-tipo-declarado/design`, D1); `CargaArchivoPatch`
    no expone ese campo."""
    carga = await _carga_or_404(db, carga_id)
    if carga.origen == "BOT":
        # sdd/motored-ventas-perdidas-bot, design D1: un header BOT nunca
        # declara período (nace del registro puntual del asesor, no de un
        # archivo con período declarado) -- rechazado explícitamente,
        # nunca dependiendo de que además nazca `estado='APLICADO'`.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede modificar el período de una carga de origen BOT.",
        )
    if carga.estado != "PENDIENTE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se puede completar tipo/período mientras la carga está PENDIENTE.",
        )
    _check_periodo_no_futuro(payload.periodo_desde, payload.periodo_hasta)

    if payload.periodo_desde is not None:
        carga.periodo_desde = payload.periodo_desde
        carga.periodo_hasta = payload.periodo_hasta or payload.periodo_desde
    elif payload.periodo_hasta is not None:
        carga.periodo_hasta = payload.periodo_hasta

    await db.commit()
    await _despachar_si_completa(carga, job_runner)
    return CargaArchivoRead.model_validate(carga)


_BOT_RANGO_MAX_DIAS = 31


def _validar_rango_bot(desde: Optional[date], hasta: Optional[date]) -> None:
    """`origen=BOT` exige `desde`+`hasta` con un rango de a lo sumo
    `_BOT_RANGO_MAX_DIAS` días -- un scan sin acotar de ~340k headers/año de
    bot es exactamente el problema de volumen que esta decisión evita
    (design D1). Extraído de `listar_cargas` (gga: single-purpose)."""
    if desde is None or hasta is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="origen=BOT requiere 'desde' y 'hasta'.",
        )
    if hasta < desde:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'hasta' no puede ser anterior a 'desde'.",
        )
    if (hasta - desde).days > _BOT_RANGO_MAX_DIAS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El rango 'desde'/'hasta' no puede superar "
                f"{_BOT_RANGO_MAX_DIAS} días para origen=BOT."
            ),
        )


@router.get("/{tipo}/plantilla.xlsx")
async def descargar_plantilla_movimiento(
    tipo: str,
    user: MotoredUser = Depends(_require_write),
):
    """Plantilla `.xlsx` (solo encabezado) del `tipo` de movimiento, para el
    modal de subida (`UploadMovimientoModal`). Las columnas vienen de
    `plantillas.columnas_plantilla` -- las mismas que el backend verifica y
    lee al subir, no una copia. `tipo` fuera de `orquestador.TIPOS_
    MOVIMIENTO` (incluidos `MAESTRO_*`) es `404`. Mismo patrón que
    `GET /maestros/{entidad}/plantilla.xlsx`; sin choque con `/{carga_id}/...`
    (rutas de otra forma, y `carga_id` es `uuid`)."""
    if tipo not in orquestador.TIPOS_MOVIMIENTO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo no encontrado")
    return Response(
        content=plantillas_mod.generar_plantilla_xlsx(tipo),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="plantilla_{tipo.lower()}.xlsx"'},
    )


@router.get("", response_model=List[CargaArchivoRead])
async def listar_cargas(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    origen: str = "EXCEL",
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    """`GET /cargas` -- lista completa para los 4 roles (ver docstring del
    módulo, "Decisión documentada -- scoping de GET /cargas").

    `origen` (sdd/motored-ventas-perdidas-bot, design D1, volume
    mitigation): default `EXCEL` -- comportamiento IDÉNTICO al de hoy para
    todo caller existente (la pantalla de Cargas), porque toda fila
    existente es EXCEL. `origen=BOT` exige `desde`+`hasta` con un rango de
    a lo sumo 31 días -- un scan sin acotar de ~340k headers/año de bot es
    exactamente el problema de volumen que esta decisión evita.

    Post-Phase-3 review, finding #1: un header BOT NUNCA declara período
    (`periodo_desde`/`periodo_hasta` son siempre `NULL` -- design D1, un
    registro puntual del asesor no es un archivo con período). Filtrar por
    esas columnas para `origen=BOT` sería un no-op que no acota NADA
    (`periodo_hasta IS NULL OR ...` y `periodo_desde IS NULL OR ...` son
    ambas vacuamente verdaderas), dejando pasar cualquier fila BOT sin
    importar el rango pedido -- exactamente el problema de volumen que este
    guard existe para evitar. Para `origen=BOT` se filtra por `created_at`
    en su lugar, la columna que sí tiene un valor real en cada fila BOT."""
    if origen == "BOT":
        _validar_rango_bot(desde, hasta)
    stmt = select(CargaArchivo).where(CargaArchivo.origen == origen)
    if tipo:
        stmt = stmt.where(CargaArchivo.tipo == tipo)
    if estado:
        stmt = stmt.where(CargaArchivo.estado == estado)
    if origen == "BOT":
        desde_dt = datetime.combine(desde, time.min)
        hasta_dt = datetime.combine(hasta, time.max)
        stmt = stmt.where(CargaArchivo.created_at >= desde_dt, CargaArchivo.created_at <= hasta_dt)
    else:
        if desde:
            stmt = stmt.where(
                (CargaArchivo.periodo_hasta.is_(None)) | (CargaArchivo.periodo_hasta >= desde)
            )
        if hasta:
            stmt = stmt.where(
                (CargaArchivo.periodo_desde.is_(None)) | (CargaArchivo.periodo_desde <= hasta)
            )
    stmt = stmt.order_by(CargaArchivo.created_at.desc())
    result = await db.execute(stmt)
    return [CargaArchivoRead.model_validate(row) for row in result.scalars().all()]


@router.get("/{carga_id}", response_model=CargaArchivoRead)
async def obtener_carga(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    carga = await _carga_or_404(db, carga_id)
    return CargaArchivoRead.model_validate(carga)


@router.get("/{carga_id}/informe", response_model=CargaInformeResponse)
async def obtener_informe(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    """Informe previo (spec "Two-step validar-then-aplicar con informe
    previo"): declarado vs. detectado, defaults usados (`log`), y variación
    vs. la carga APLICADA anterior del MISMO tipo (±40% warning)."""
    carga = await _carga_or_404(db, carga_id)

    variacion = None
    if carga.tipo:
        anterior_result = await db.execute(
            select(CargaArchivo.filas_validas)
            .where(
                CargaArchivo.tipo == carga.tipo,
                CargaArchivo.estado == "APLICADO",
                CargaArchivo.origen == "EXCEL",
                CargaArchivo.id != carga.id,
            )
            .order_by(CargaArchivo.created_at.desc())
            .limit(1)
        )
        anterior = anterior_result.scalars().first()
        if anterior:
            variacion = ((carga.filas_validas - anterior) / anterior) * 100

    return CargaInformeResponse(
        id=carga.id,
        tipo=carga.tipo,
        estado=carga.estado,
        filas_leidas=carga.filas_leidas,
        filas_validas=carga.filas_validas,
        filas_rechazadas=carga.filas_rechazadas,
        periodo_desde=carga.periodo_desde,
        periodo_hasta=carga.periodo_hasta,
        log=carga.log or {},
        variacion_pct_vs_carga_anterior=variacion,
    )


async def _filtrar_errores_por_sucursal(
    db: AsyncSession, carga_id: uuid.UUID, errores: List[CargaError], user: MotoredUser
) -> List[CargaError]:
    """T19 (hot spot histórico): un `SUCURSAL` solo ve errores de fila cuyo
    `carga_fila_staging.sucursal_id` resuelto es una de las suyas -- ver
    docstring del módulo para el criterio fail-closed en filas sin
    sucursal resuelta o en errores de archivo completo (`fila=0`)."""
    if user.role != "SUCURSAL":
        return errores
    staging_result = await db.execute(
        select(CargaFilaStaging.fila, CargaFilaStaging.sucursal_id)
        .where(CargaFilaStaging.carga_id == carga_id)
    )
    sucursal_por_fila: Dict[int, Any] = dict(staging_result.all())
    propias = set(user.sucursal_ids)
    return [
        error for error in errores
        if sucursal_por_fila.get(error.fila) is not None
        and str(sucursal_por_fila[error.fila]) in propias
    ]


@router.get("/{carga_id}/errores", response_model=List[CargaErrorRead])
async def listar_errores(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    await _carga_or_404(db, carga_id)
    result = await db.execute(select(CargaError).where(CargaError.carga_id == carga_id))
    errores = await _filtrar_errores_por_sucursal(db, carga_id, result.scalars().all(), user)
    return [CargaErrorRead.model_validate(error) for error in errores]


@router.get("/{carga_id}/errores.csv")
async def exportar_errores_csv(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    await _carga_or_404(db, carga_id)
    result = await db.execute(select(CargaError).where(CargaError.carga_id == carga_id))
    errores = await _filtrar_errores_por_sucursal(db, carga_id, result.scalars().all(), user)
    csv_text = errores_mod.generar_csv_errores(errores)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="errores_{carga_id}.csv"'},
    )


def _filtrar_staging_por_sucursal(
    filas: List[CargaFilaStaging], user: MotoredUser
) -> List[CargaFilaStaging]:
    """T19, mismo criterio fail-closed que `_filtrar_errores_por_sucursal`:
    un `SUCURSAL` solo ve filas cuya `sucursal_id` resuelta es una de las
    suyas; una fila sin sucursal resuelta nunca se muestra especulativamente."""
    if user.role != "SUCURSAL":
        return filas
    propias = set(user.sucursal_ids)
    return [
        fila for fila in filas
        if fila.sucursal_id is not None and str(fila.sucursal_id) in propias
    ]


@router.get("/{carga_id}/preview")
async def preview_carga(
    carga_id: uuid.UUID,
    limite: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> List[Dict[str, Any]]:
    await _carga_or_404(db, carga_id)
    result = await db.execute(
        select(CargaFilaStaging)
        .where(CargaFilaStaging.carga_id == carga_id)
        .order_by(CargaFilaStaging.fila)
        .limit(limite)
    )
    filas = _filtrar_staging_por_sucursal(result.scalars().all(), user)
    return [
        {
            "fila": fila.fila,
            "payload": fila.payload,
            "sucursal_id": fila.sucursal_id,
            "referencia_id": fila.referencia_id,
        }
        for fila in filas
    ]


async def _aplicar_mapeo_sucursal(db: AsyncSession, accion) -> bool:
    """Persiste `sucursal_alias` (spec "sucursal_alias resolution write
    path") -- afecta FUTURAS cargas del mismo tipo, nunca re-resuelve
    retroactivamente las filas YA staged de esta carga. Retorna `False`
    (la acción se cuenta como ignorada) si falta `valor`/`sucursal_id`."""
    if not accion.valor or not accion.sucursal_id:
        return False
    texto_normalizado = resolucion_mod.normalizar_texto_sucursal(accion.valor)
    alias_existente = await db.execute(
        select(SucursalAlias).where(SucursalAlias.texto_normalizado == texto_normalizado)
    )
    alias = alias_existente.scalars().first()
    if alias is None:
        db.add(SucursalAlias(texto_normalizado=texto_normalizado, sucursal_id=accion.sucursal_id))
    else:
        alias.sucursal_id = accion.sucursal_id
    return True


async def _aplicar_creacion_referencia(db: AsyncSession, accion) -> bool:
    """Crea la referencia bajo el proveedor `OTROS` (`unidad_empaque=1`) --
    retorna `False` (ignorada) si falta `valor` o si ya existe."""
    codigo = (accion.valor or "").strip()
    if not codigo:
        return False
    proveedor_otros = await maestros_mod.get_proveedor_by_codigo(db, "OTROS")
    if proveedor_otros is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No existe el proveedor 'OTROS' -- no se puede crear la referencia.",
        )
    # Por CODIGO (único): si ya existe bajo cualquier proveedor no se duplica.
    if await maestros_mod.get_referencia_by_codigo(db, codigo) is not None:
        return False
    db.add(Referencia(codigo=codigo, proveedor_id=proveedor_otros.id, unidad_empaque=1))
    return True


@router.post("/{carga_id}/resolver", response_model=ResolverErroresResultado)
async def resolver_errores(
    carga_id: uuid.UUID,
    payload: ResolverErroresRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Spec "Error-resolution actions": mapear sucursal, crear referencia
    bajo `OTROS`, o ignorar -- una acción por `CargaError` (ver los
    helpers `_aplicar_mapeo_sucursal`/`_aplicar_creacion_referencia`)."""
    await _carga_or_404(db, carga_id)
    aplicadas = 0
    ignoradas = 0
    for accion in payload.acciones:
        if accion.accion == "mapear_sucursal":
            aplicada = await _aplicar_mapeo_sucursal(db, accion)
        elif accion.accion == "crear_referencia":
            aplicada = await _aplicar_creacion_referencia(db, accion)
        elif accion.accion == "ignorar":
            aplicada = False
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Acción desconocida: {accion.accion!r}",
            )
        aplicadas += int(aplicada)
        ignoradas += int(not aplicada)
    await db.commit()
    return ResolverErroresResultado(acciones_aplicadas=aplicadas, acciones_ignoradas=ignoradas)


async def _incluidas_de(db: AsyncSession, carga: CargaArchivo):
    tipos, _ = await parametros.resolver_tipos_inventario_incluidos(
        db, carga.periodo_desde or date.today())
    return lineas_mod.normalizar_incluidas(tipos)


async def _payload_sin_linea(
    db: AsyncSession, carga: CargaArchivo, user: Optional[MotoredUser] = None,
) -> Dict[str, Any]:
    propias = (set(user.sucursal_ids)
               if user is not None and user.role == "SUCURSAL" else None)
    payload = await lineas_mod.informe(
        db, carga.id, await _incluidas_de(db, carga), propias)
    permitidas = await _lineas_permitidas(db)
    payload["opciones_linea"] = [
        {"valor": norm, "etiqueta": tablero_comisiones.etiqueta_de(norm)}
        for norm in permitidas if norm != lineas_mod.LINEA_NO_COMERCIAL
    ] + [{"valor": lineas_mod.LINEA_NO_COMERCIAL,
          "etiqueta": "No es de repuestos (descartar)"}]
    return payload


def _exigir_ventas_abierta(carga: CargaArchivo) -> None:
    if carga.tipo != "VENTAS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo las cargas de VENTAS tienen referencias sin línea.")
    if carga.estado in ("APLICADO", "ANULADO"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La carga ya está {carga.estado.lower()}: no se pueden "
                   "asignar líneas.")


async def _lineas_permitidas(db: AsyncSession) -> Dict[str, str]:
    """`{línea normalizada: texto a guardar}`: `lineas_comerciales` vigente
    más NO COMERCIAL (sacar la referencia del reparto sin bloquear)."""
    clave = "lineas_comerciales"
    valores = await parametros.leer_con_memoria(
        db, datetime.now(timezone.utc).date(),
        {clave: list(parametros_claves.REGISTRO[clave].default)}, {},
        deshacer=False)
    permitidas = {lineas_mod.normalizar_linea(v): str(v).strip()
                  for v in valores[clave]}
    permitidas[lineas_mod.LINEA_NO_COMERCIAL] = lineas_mod.LINEA_NO_COMERCIAL
    return permitidas


async def _asignar_lineas(
    db: AsyncSession, carga: CargaArchivo, user: MotoredUser,
    items: List[AsignacionLineaItem],
) -> None:
    """Todo o nada: valida TODOS los items contra la lista viva de
    `sin_linea` y las líneas permitidas antes de escribir el primero."""
    _exigir_ventas_abierta(carga)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Indique al menos una referencia y su línea.")
    if len({i.referencia_id for i in items}) != len(items):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una referencia aparece más de una vez.")
    vivas = {r["referencia_id"]
             for r in (await _payload_sin_linea(db, carga))["sin_linea"]}
    fuera = [i for i in items if i.referencia_id not in vivas]
    if fuera:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La referencia ya no está en la lista de referencias sin "
                   "línea de esta carga.")
    permitidas = await _lineas_permitidas(db)
    invalidas = [i for i in items
                 if lineas_mod.normalizar_linea(i.linea_comercial)
                 not in permitidas]
    if invalidas:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La línea '{invalidas[0].linea_comercial}' no es una "
                   "línea comercial válida.")
    usuario_id = uuid.UUID(user.user_id)
    auditoria = list((carga.log or {}).get("asignaciones_linea", []))
    for item in items:
        referencia = await db.get(Referencia, item.referencia_id)
        linea = permitidas[lineas_mod.normalizar_linea(item.linea_comercial)]
        await maestros_mod.update_referencia(
            db, referencia, ReferenciaUpdate(linea_comercial=linea),
            usuario_id, verificar_sustituta=False)
        auditoria.append({
            "referencia_id": str(item.referencia_id),
            "codigo": referencia.codigo, "linea": linea,
            "usuario_id": str(usuario_id),
            "en": datetime.now(timezone.utc).isoformat()})
    carga.log = {**(carga.log or {}), "asignaciones_linea": auditoria}
    await db.flush()


@router.get(
    "/{carga_id}/referencias-sin-linea",
    response_model=ReferenciasSinLineaResponse)
async def listar_referencias_sin_linea(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    """Lo que falta resolver de una carga de VENTAS, calculado en vivo
    contra el maestro de hoy (ver `services.ingesta.ventas_lineas`)."""
    carga = await _carga_or_404(db, carga_id)
    return await _payload_sin_linea(db, carga, user)


@router.put(
    "/{carga_id}/referencias-sin-linea",
    response_model=ReferenciasSinLineaResponse)
async def asignar_lineas(
    carga_id: uuid.UUID,
    payload: List[AsignacionLineaItem],
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Asigna la línea de varias referencias a la vez, todo o nada."""
    carga = await _carga_or_404(db, carga_id)
    await _asignar_lineas(db, carga, user, payload)
    await db.commit()
    return await _payload_sin_linea(db, carga)


@router.put(
    "/{carga_id}/referencias-sin-linea/{referencia_id}",
    response_model=ReferenciasSinLineaResponse)
async def asignar_linea(
    carga_id: uuid.UUID,
    referencia_id: uuid.UUID,
    payload: AsignarLineaRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Asigna la línea de UNA referencia sin línea de esta carga."""
    carga = await _carga_or_404(db, carga_id)
    await _asignar_lineas(db, carga, user, [AsignacionLineaItem(
        referencia_id=referencia_id,
        linea_comercial=payload.linea_comercial)])
    await db.commit()
    return await _payload_sin_linea(db, carga)


@router.get(
    "/{carga_id}/vaciado-previsto", response_model=List[VaciadoPrevistoRead])
async def obtener_vaciado_previsto(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Las tiendas cuyas ventas del mes borraria el apply de una carga
    `reemplaza_mes_completo` porque el archivo no las trae. En vivo; vacio
    si la carga no pidio el reemplazo."""
    carga = await _carga_or_404(db, carga_id)
    return await lineas_mod.vaciado_previsto(
        db, carga, await _incluidas_de(db, carga))


@router.post("/{carga_id}/aplicar", response_model=CargaArchivoRead)
async def aplicar_carga(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    carga = await _carga_or_404(db, carga_id)
    try:
        await orquestador.ejecutar_aplicar(db, carga)
    except orquestador.EstadoInvalidoParaAplicarError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except orquestador.ProveedorPrincipalError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return CargaArchivoRead.model_validate(carga)


async def _anular_bot(
    db: AsyncSession, carga: CargaArchivo, user: MotoredUser
) -> None:
    """sdd/motored-ventas-perdidas-bot, design D4: un header BOT no tiene
    `carga_fila_staging` que borrar -- el ADMIN web delega en el mismo
    servicio que usará el propio endpoint del bot (`validar_ventana=True`,
    Fase 6), pero sin sus reglas de propio-actor/mismo-día
    (`validar_ventana=False`).

    Post-Phase-3 review, finding #2: el guard `estado == "ANULADO"` del
    endpoint es un SELECT + chequeo en Python, no atómico -- dos llamadas
    concurrentes pueden pasarlo ambas. El claim atómico real vive DENTRO de
    `anular_registro_bot` (única barrera común a toda llamada concurrente
    contra la misma fila); acá solo se traduce su `CargaYaAnuladaError` al
    mismo 409 que el guard del endpoint ya usa."""
    try:
        await demanda_perdida_bot_mod.anular_registro_bot(
            db, carga, user, validar_ventana=False
        )
    except demanda_perdida_bot_mod.CargaYaAnuladaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La carga ya está anulada.",
        )
    await db.commit()


async def _aplicar_guarda_corridas(
    db: AsyncSession, carga: CargaArchivo
) -> None:
    """ADR-11: bloquea la carga y consulta las corridas que la usaron. Un
    bloqueo (E-CARGA-050) libera el lock de inmediato con un rollback y se
    responde 409 con el código y el mensaje que nombra la corrida."""
    try:
        await aplicar_guard_anulacion(db, carga)
    except ErrorCorrida as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.codigo, "message": exc.mensaje},
        )


@router.post("/{carga_id}/anular", response_model=CargaArchivoRead)
async def anular_carga(
    carga_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
):
    """Spec "Anulación guard": una carga EXCEL usada por una corrida CERRADA
    no se anula (409 E-CARGA-050); una usada por corridas vivas las marca
    invalidadas y se anula igual. Ver el docstring del módulo."""
    carga = await _carga_or_404(db, carga_id)
    if carga.estado == "ANULADO":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="La carga ya está anulada."
        )

    if carga.origen == "BOT":
        await _anular_bot(db, carga, user)
        return CargaArchivoRead.model_validate(carga)

    await _aplicar_guarda_corridas(db, carga)
    carga.estado = "ANULADO"
    if carga.tipo == "VENTAS":
        # The KPI summaries hide the annulled lines: refresh the months this carga touched, in
        # this same transaction (a failure rolls the annulment back with it). The session runs
        # without autoflush, so the new state is flushed first for the refresh to see it.
        await db.flush()
        await kpi_resumen.refrescar_si_construido(db, await kpi_resumen.claves_de_carga(db, carga_id))
    elif carga.tipo == "INVENTARIO":
        # The cost and inventory summaries hide the annulled cortes: a full rebuild is pending.
        await kpi_resumen.marcar_sucio_si_construido(db)
    await db.execute(delete(CargaFilaStaging).where(CargaFilaStaging.carga_id == carga_id))
    await db.commit()
    return CargaArchivoRead.model_validate(carga)
