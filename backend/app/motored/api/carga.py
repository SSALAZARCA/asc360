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
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.schemas.carga import CargaRequest, CargaResultado
from app.motored.services.carga import SUSTITUTA_EN_ARCHIVO, procesar_carga
from app.motored.services.carga_excel import CargaExcelError, LimiteFilasExcedidoError, parse_excel_rows
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal
from app.motored.services.ingesta.ventas import normalizar_vendedor
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
    codigo: str,
    proveedor_id: Optional[uuid.UUID],
    candidatas: List[Referencia],
    existe_en_archivo_otro_proveedor: bool = False,
) -> Tuple[Optional[uuid.UUID], Optional[str]]:
    """Elige la referencia sustituta para `codigo` entre `candidatas` (todas
    las referencias existentes con ese código -- la UNIQUE es
    `(codigo, proveedor_id)`, así que puede haber varias). Regla de negocio
    (decisión del usuario, 2026-09-28): la sustituta DEBE ser del MISMO
    proveedor que la fila. Retorna `(id, None)` o
    `(None, motivo_de_error)` -- nunca se descarta en silencio.
    `existe_en_archivo_otro_proveedor`: el código no está en la base bajo este
    proveedor, pero sí aparece en el mismo archivo bajo OTRO proveedor -- el
    motivo lo dice igual que si estuviera en la base."""
    for candidata in candidatas:
        if proveedor_id is not None and candidata.proveedor_id == proveedor_id:
            return candidata.id, None
    if candidatas or existe_en_archivo_otro_proveedor:
        return None, (
            f"'Código de referencia sustituta' '{codigo}' existe, pero de otro proveedor. "
            "La referencia sustituta debe ser del mismo proveedor."
        )
    return None, (
        f"'Código de referencia sustituta' '{codigo}' no corresponde a ninguna referencia existente "
        "de este proveedor ni a otra fila del archivo"
    )


_Llave = Tuple[str, uuid.UUID]  # (codigo, proveedor_id) -- la llave natural de `referencia`


def _ciclos_de_sustitucion(enlaces: Dict[_Llave, _Llave]) -> Dict[_Llave, List[_Llave]]:
    """`enlaces`: fila del archivo -> sustituta que es OTRA fila del archivo.
    Cada llave tiene a lo sumo un enlace (grafo funcional), así que basta con
    seguir la cadena desde cada nodo. Retorna, para cada llave que forma parte
    de un ciclo, el ciclo completo en orden (sin repetir el primero). Una
    fila que solo APUNTA a un ciclo no es parte de él. Iterativo, O(n)."""
    estado: Dict[_Llave, int] = {}  # 1 = en el camino actual, 2 = ya resuelto
    ciclos: Dict[_Llave, List[_Llave]] = {}
    for inicio in enlaces:
        camino: List[_Llave] = []
        nodo: Optional[_Llave] = inicio
        while nodo is not None and nodo not in estado:
            estado[nodo] = 1
            camino.append(nodo)
            nodo = enlaces.get(nodo)
        if nodo is not None and estado.get(nodo) == 1:
            ciclo = camino[camino.index(nodo):]
            for miembro in ciclo:
                ciclos[miembro] = ciclo
        for visitado in camino:
            estado[visitado] = 2
    return ciclos


def _motivo_ciclo(ciclo: List[_Llave], desde: _Llave) -> str:
    """El ciclo contado desde la fila que recibe el error, para que cada
    fila lea su propia cadena: 'A -> B -> C -> A'."""
    i = ciclo.index(desde)
    codigos = [llave[0] for llave in ciclo[i:] + ciclo[:i]]
    return (
        f"'Código de referencia sustituta' '{codigos[1 % len(codigos)]}' forma un ciclo de sustitución "
        f"dentro del archivo ({' -> '.join(codigos + [codigos[0]])}). Una referencia no puede terminar "
        "sustituyéndose a sí misma."
    )


async def _cargar_proveedores_y_candidatas(
    db: AsyncSession, filas: List[Dict[str, Any]]
) -> Tuple[Dict[str, uuid.UUID], Dict[str, List[Referencia]]]:
    """Los DOS únicos queries de la resolución (`IN (...)`, nunca uno por
    fila): `proveedor_codigo` -> `proveedor_id`, y todas las referencias de
    la base cuyo código aparece como sustituta (de cualquier proveedor --
    `_pick_sustituta` decide cuál sirve)."""
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

    return proveedor_id_by_codigo, referencias_by_codigo


def _asignar_proveedor_id(
    filas: List[Dict[str, Any]], proveedor_id_by_codigo: Dict[str, uuid.UUID]
) -> List[Dict[str, Any]]:
    """Copia cada fila y setea `proveedor_id` cuando `proveedor_codigo`
    matchea. Sin match la fila queda sin `proveedor_id` (FK REQUERIDA en
    `ReferenciaCreate`) y `validate_rows` ya reporta un "campo requerido"
    claro más adelante -- acá no hace falta un error propio."""
    resolved: List[Dict[str, Any]] = []
    for fila in filas:
        fila = dict(fila)
        proveedor_codigo = fila.get("proveedor_codigo")
        if proveedor_codigo in proveedor_id_by_codigo:
            fila["proveedor_id"] = proveedor_id_by_codigo[proveedor_codigo]
        resolved.append(fila)
    return resolved


def _motivo_autorreferencia(codigo: str) -> str:
    return (
        f"'Código de referencia sustituta' '{codigo}' es el mismo código de la fila: "
        "una referencia no puede sustituirse a sí misma."
    )


def _clasificar_sustitutas(
    resolved: List[Dict[str, Any]], referencias_by_codigo: Dict[str, List[Referencia]]
) -> Tuple[Dict[int, str], Dict[_Llave, _Llave], Dict[_Llave, List[int]]]:
    """Clasifica cada `sustituida_por_codigo` (SOLO del mismo proveedor), en
    este orden:
    1. Autorreferencia -> error de fila.
    2. Otra fila del MISMO archivo con ese código y proveedor: la fila queda
       marcada con `SUSTITUTA_EN_ARCHIVO` y `procesar_carga` setea el enlace
       en una segunda pasada, después de insertar todo (odd/tasks/motored-
       sustituta-mismo-archivo.md). Se prefiere al match de base porque la
       fila del archivo es la versión que va a quedar, y el chequeo de
       ciclos la necesita.
    3. La base, vía `_pick_sustituta` -> `sustituida_por` directo; sin match
       es error de fila (nunca se descarta en silencio: "todo o nada", owner
       decision #1).
    Muta `resolved` in-place. Retorna `(errores_by_index, enlaces,
    index_by_llave)`: errores por fila 1-indexada, los enlaces dentro del
    archivo (fila -> sustituta) y qué filas corresponden a cada llave."""
    llaves_en_archivo = {
        (fila.get("codigo"), fila["proveedor_id"]) for fila in resolved if fila.get("proveedor_id")
    }
    codigos_en_archivo = {codigo for codigo, _ in llaves_en_archivo}

    errores_by_index: Dict[int, str] = {}
    enlaces: Dict[_Llave, _Llave] = {}
    index_by_llave: Dict[_Llave, List[int]] = {}
    for index, fila in enumerate(resolved, start=1):
        sustituida_por_codigo = fila.get("sustituida_por_codigo")
        if not sustituida_por_codigo:
            continue
        proveedor_id = fila.get("proveedor_id")
        llave_sustituta = (sustituida_por_codigo, proveedor_id)

        if proveedor_id is not None and sustituida_por_codigo == fila.get("codigo"):
            errores_by_index[index] = _motivo_autorreferencia(sustituida_por_codigo)
        elif proveedor_id is not None and llave_sustituta in llaves_en_archivo:
            fila[SUSTITUTA_EN_ARCHIVO] = sustituida_por_codigo
            llave = (fila.get("codigo"), proveedor_id)
            enlaces[llave] = llave_sustituta
            index_by_llave.setdefault(llave, []).append(index)
        else:
            sustituta_id, motivo = _pick_sustituta(
                sustituida_por_codigo,
                proveedor_id,
                referencias_by_codigo.get(sustituida_por_codigo, []),
                existe_en_archivo_otro_proveedor=sustituida_por_codigo in codigos_en_archivo,
            )
            if sustituta_id is not None:
                fila["sustituida_por"] = sustituta_id
            else:
                errores_by_index[index] = motivo

    return errores_by_index, enlaces, index_by_llave


def _marcar_ciclos(
    resolved: List[Dict[str, Any]],
    errores_by_index: Dict[int, str],
    enlaces: Dict[_Llave, _Llave],
    index_by_llave: Dict[_Llave, List[int]],
) -> None:
    """Cada fila que forma parte de un ciclo dentro del archivo recibe su
    error de fila (in-place en `errores_by_index`) y pierde la marca
    `SUSTITUTA_EN_ARCHIVO` -- nunca llega a la segunda pasada."""
    for llave, ciclo in _ciclos_de_sustitucion(enlaces).items():
        for index in index_by_llave[llave]:
            errores_by_index[index] = _motivo_ciclo(ciclo, llave)
            resolved[index - 1].pop(SUSTITUTA_EN_ARCHIVO, None)


async def _sucursal_id_por_texto(db: AsyncSession) -> Dict[str, uuid.UUID]:
    """`normalizar_texto_sucursal(nombre | alias)` -> `sucursal_id`, con DOS
    queries (nombres reales primero, `sucursal_alias` solo rellena lo que
    falte) -- la misma prioridad que `ingesta.resolucion.construir_cache`."""
    por_texto: Dict[str, uuid.UUID] = {}
    for sucursal_id, nombre in (await db.execute(select(Sucursal.id, Sucursal.nombre))).all():
        if nombre:
            por_texto[normalizar_texto_sucursal(nombre)] = sucursal_id
    alias_rows = (
        await db.execute(select(SucursalAlias.texto_normalizado, SucursalAlias.sucursal_id))
    ).all()
    for texto_normalizado, sucursal_id in alias_rows:
        por_texto.setdefault(texto_normalizado, sucursal_id)
    return por_texto


async def _resolve_vendedor_relaciones(
    db: AsyncSession, filas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Para `vendedor`: resuelve `sucursal_nombre` -> `sucursal_id` (un nombre
    que no existe es error de fila, nunca se descarta en silencio) y marca como
    error un vendedor repetido en el archivo (misma `normalizar_vendedor`: dos
    escrituras de la misma persona son ambiguas, el usuario debe dejar una).
    Sin ningun nombre de sucursal en el archivo no consulta la base."""
    hay_sucursales = any(str(f.get("sucursal_nombre") or "").strip() for f in filas)
    por_texto = await _sucursal_id_por_texto(db) if hay_sucursales else {}

    resueltas: List[Dict[str, Any]] = []
    errores: List[Dict[str, Any]] = []
    primera_fila: Dict[str, int] = {}
    for index, fila in enumerate(filas, start=1):
        fila = dict(fila)
        nombre = str(fila.get("nombre") or "").strip()
        if nombre:
            clave = normalizar_vendedor(nombre)
            if clave in primera_fila:
                errores.append({
                    "fila": index,
                    "motivo": (
                        f"Vendedor repetido en el archivo (igual a la fila {primera_fila[clave]}). "
                        "Dejá una sola fila por persona."
                    ),
                })
            else:
                primera_fila[clave] = index
        texto_sucursal = str(fila.get("sucursal_nombre") or "").strip()
        if texto_sucursal:
            sucursal_id = por_texto.get(normalizar_texto_sucursal(texto_sucursal))
            if sucursal_id is None:
                errores.append({
                    "fila": index,
                    "motivo": f"'Sucursal' '{texto_sucursal}' no corresponde a ninguna sucursal existente",
                })
            else:
                fila["sucursal_id"] = sucursal_id
        resueltas.append(fila)
    return resueltas, errores


async def _resolve_referencia_relaciones(
    db: AsyncSession, entidad: str, filas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Para `referencia` ÚNICAMENTE: resuelve `proveedor_codigo` ->
    `proveedor_id` y `sustituida_por_codigo` -> sustituta antes de
    validar/escribir, con dos queries en total (alcance documentado en
    `services/carga.py`'s docstring: 'la resolución... es responsabilidad
    del llamador'). Retorna `(filas_resueltas, errores_resolucion)`, con
    `errores_resolucion` en el mismo shape `{fila, motivo}` 1-indexado que
    `validate_rows.RowError`, que el caller mezcla antes de decidir
    todo-o-nada. Como `validar` y `carga` comparten esta función, el dry-run
    da el mismo veredicto. Detalle de cada paso en sus helpers."""
    if entidad != "referencia":
        return filas, []

    proveedor_id_by_codigo, referencias_by_codigo = await _cargar_proveedores_y_candidatas(db, filas)
    resolved = _asignar_proveedor_id(filas, proveedor_id_by_codigo)
    errores_by_index, enlaces, index_by_llave = _clasificar_sustitutas(resolved, referencias_by_codigo)
    _marcar_ciclos(resolved, errores_by_index, enlaces, index_by_llave)

    errores_resolucion = [{"fila": i, "motivo": errores_by_index[i]} for i in sorted(errores_by_index)]
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
    filas, errores_resolucion = await _resolver_relaciones(db, entidad, filas)
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
    filas, errores_resolucion = await _resolver_relaciones(db, entidad, filas)
    return await procesar_carga(db, entidad, filas, usuario_id, errores_previos=errores_resolucion)


async def _resolver_relaciones(
    db: AsyncSession, entidad: str, filas: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Resuelve, según la entidad, las relaciones que el archivo trae como
    texto: `vendedor` -> `_resolve_vendedor_relaciones`, `referencia` ->
    `_resolve_referencia_relaciones`; el resto no resuelve nada. Mismo shape
    de retorno `(filas_resueltas, errores_resolucion)` en los tres casos."""
    if entidad == "vendedor":
        return await _resolve_vendedor_relaciones(db, filas)
    return await _resolve_referencia_relaciones(db, entidad, filas)


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
