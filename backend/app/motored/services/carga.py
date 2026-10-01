"""
Motored Pedidos — carga masiva de maestros (sdd/motored-pedidos-cimientos,
Fase 3, task 3.4, ADR-6). Todo-o-nada (owner decision #1): se valida el
archivo COMPLETO primero (`validators.validate_rows`, que acumula TODOS los
errores en un solo pase); si hay AL MENOS una fila inválida, no se escribe
absolutamente nada y se retorna el reporte completo. Un archivo totalmente
válido se sube en una única transacción, con upsert por llave natural
(owner decision #2), reutilizando exactamente las mismas funciones de
`services/maestros.py` que usa el CRUD unitario -- una sola fuente de
verdad para la coerción de `unidad_empaque` y el trim de `sucursal.nombre`.

Nota de alcance (Fase 1): para `referencia`, la resolución de
`proveedor_codigo` -> `proveedor_id` es responsabilidad del llamador (router
de Fase 4, que arma cada fila del Excel con el `proveedor_id` ya resuelto
contra un caché de proveedores). Esta función exige que la fila ya traiga
`proveedor_id`; solo usa `proveedor_codigo` para el mensaje de validación
"campo requerido".
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.motored.schemas.carga import CargaErrorRow, CargaResultado
from app.motored.schemas.referencia import ReferenciaUpdate
from app.motored.services import maestros
from app.motored.services.validators import _SCHEMA_BY_ENTIDAD, ENTIDADES_DE_REEMPLAZO, validate_rows

# Clave interna de fila (nunca llega al schema Pydantic): código de la
# sustituta cuando es OTRA fila del mismo archivo y proveedor. La setea
# `api/carga.py::_resolve_referencia_relaciones`; la consume
# `_enlazar_sustitutas_del_archivo` en la segunda pasada.
SUSTITUTA_EN_ARCHIVO = "_sustituta_codigo_en_archivo"

_UPSERT_BY_ENTIDAD = {
    "sucursal": maestros.upsert_sucursal,
    "bodega": maestros.upsert_bodega,
    "proveedor": maestros.upsert_proveedor,
    "referencia": maestros.upsert_referencia,
}


def _row_to_schema(entidad: str, row: Dict[str, Any]):
    """Reconstruye el mismo schema que `validators.validate_rows` ya
    construyó (y descartó) durante la validación -- para esta fila, ya se
    probó que construye sin lanzar `ValidationError`, así que esta segunda
    construcción es segura por diseño, nunca un punto nuevo de fallo."""
    schema_cls = _SCHEMA_BY_ENTIDAD[entidad]
    payload = {k: v for k, v in row.items() if not k.startswith("_")}
    return schema_cls(**payload)


async def _upsert_row(
    db, entidad: str, row: Dict[str, Any], usuario_id: Optional[uuid.UUID]
) -> tuple:
    """Sube UNA fila ya validada y retorna `(obj, created, advertencias)`.

    Las 4 funciones `upsert_*` retornan `(obj, advertencia_o_None,
    created)` -- `created` es explícito, decidido por la propia rama
    if/else de `upsert_fn`, NO inferido después mirando qué quedó
    "pendiente" en la sesión. Una sesión real de SQLAlchemy no expone eso
    como un atributo público inspeccionable de esa forma (no existe
    `session.added`; lo más parecido, `session.new`, tiene otra semántica y
    no es la fuente de verdad para esto), así que inferirlo post-hoc es
    frágil por diseño -- pedirle el dato a quien ya lo sabe es la única
    forma robusta."""
    row_warnings = list(row.get("_warnings") or [])
    payload = _row_to_schema(entidad, row)

    upsert_fn = _UPSERT_BY_ENTIDAD[entidad]
    obj, upsert_warning, created = await upsert_fn(db, payload, usuario_id)
    if upsert_warning:
        row_warnings.append(upsert_warning)

    return obj, created, row_warnings


async def _enlazar_sustitutas_del_archivo(
    db, pendientes: List[Tuple[Any, str]], objs: List[Any], usuario_id: Optional[uuid.UUID]
) -> None:
    """Segunda pasada: setea `sustituida_por` para las filas cuya sustituta
    es otra fila del mismo archivo. `flush()` primero, para que todas las
    filas nuevas ya estén insertadas cuando se escribe la FK. El resolver ya
    garantizó que cada objetivo existe en el archivo bajo el mismo proveedor
    y que no hay ciclos, así que la búsqueda en `por_llave` no puede fallar."""
    if not pendientes:
        return
    await db.flush()
    por_llave = {(obj.codigo, obj.proveedor_id): obj for obj in objs}
    for obj, codigo_sustituta in pendientes:
        sustituta = por_llave[(codigo_sustituta, obj.proveedor_id)]
        await maestros.update_referencia(
            db, obj, ReferenciaUpdate(sustituida_por=sustituta.id), usuario_id, verificar_sustituta=False
        )


_REEMPLAZO_POR_ENTIDAD = {
    "cliente_tecnired": maestros.reemplazar_clientes_tecnired,
}


async def _reemplazar_lista(
    db, entidad: str, valid_rows: List[Dict[str, Any]], usuario_id: Optional[uuid.UUID]
) -> CargaResultado:
    """Carga que REEMPLAZA la lista completa: el archivo ya validó entero, así
    que se borra todo y se inserta lo nuevo en la misma transacción, con un
    único `commit()`."""
    insertados, eliminados, advertencias = await _REEMPLAZO_POR_ENTIDAD[entidad](
        db, valid_rows, usuario_id
    )
    await db.commit()
    return CargaResultado(
        ok=True,
        total_filas=len(valid_rows),
        insertados=insertados,
        eliminados=eliminados,
        advertencias=advertencias,
    )


async def procesar_carga(
    db,
    entidad: str,
    rows: List[Dict[str, Any]],
    usuario_id: Optional[uuid.UUID] = None,
    errores_previos: Optional[List[Dict[str, Any]]] = None,
) -> CargaResultado:
    """Valida TODO el archivo antes de escribir NADA. Si `validate_rows`
    reporta cualquier error, retorna de inmediato (`ok=False`) sin haber
    tocado la sesión -- ni un `db.add`, ni un `db.commit`. Solo si el
    archivo entero es válido se hace upsert fila por fila y se hace UN
    `commit()` al final (transacción única, spec "A fully valid file
    commits atomically").

    `errores_previos` (ad-hoc bugfix, no trackeado bajo ningún sdd/*): el
    caller (`api/carga.py`'s `_resolve_referencia_relaciones`) puede haber
    encontrado ya un error ANTES de invocar esta función (p.ej. un
    `sustituida_por_codigo` sin match) -- se mezcla acá con los errores de
    `validate_rows` ANTES del chequeo todo-o-nada, así que un error de
    resolución por sí solo alcanza para bloquear TODO el archivo, exacto
    mismo contrato que ya promete esta función para un error de
    validación."""
    total_filas = len(rows)
    valid_rows, row_errors = validate_rows(entidad, rows)
    row_errors = list(errores_previos or []) + row_errors

    if row_errors:
        return CargaResultado(
            ok=False,
            total_filas=total_filas,
            errores=[CargaErrorRow(fila=e["fila"], motivo=e["motivo"]) for e in row_errors],
        )

    if entidad in ENTIDADES_DE_REEMPLAZO:
        return await _reemplazar_lista(db, entidad, valid_rows, usuario_id)

    insertados = 0
    actualizados = 0
    advertencias: List[Dict[str, Any]] = []

    objs: List[Any] = []
    pendientes: List[Tuple[Any, str]] = []
    for index, row in enumerate(valid_rows, start=1):
        obj, created, row_warnings = await _upsert_row(db, entidad, row, usuario_id)
        objs.append(obj)
        if row.get(SUSTITUTA_EN_ARCHIVO):
            pendientes.append((obj, row[SUSTITUTA_EN_ARCHIVO]))
        if created:
            insertados += 1
        else:
            actualizados += 1
        if row_warnings:
            advertencias.append({"fila": index, "advertencias": row_warnings})

    await _enlazar_sustitutas_del_archivo(db, pendientes, objs, usuario_id)
    await db.commit()

    return CargaResultado(
        ok=True,
        total_filas=total_filas,
        insertados=insertados,
        actualizados=actualizados,
        advertencias=advertencias,
    )
