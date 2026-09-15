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
from typing import Any, Dict, List, Optional

from app.motored.schemas.carga import CargaErrorRow, CargaResultado
from app.motored.services import maestros
from app.motored.services.validators import _SCHEMA_BY_ENTIDAD, validate_rows

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
    payload = {k: v for k, v in row.items() if k != "_warnings"}
    return schema_cls(**payload)


async def _upsert_row(
    db, entidad: str, row: Dict[str, Any], usuario_id: Optional[uuid.UUID]
) -> tuple:
    """Sube UNA fila ya validada y retorna `(created, advertencias)`.

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
    _obj, upsert_warning, created = await upsert_fn(db, payload, usuario_id)
    if upsert_warning:
        row_warnings.append(upsert_warning)

    return created, row_warnings


async def procesar_carga(
    db, entidad: str, rows: List[Dict[str, Any]], usuario_id: Optional[uuid.UUID] = None
) -> CargaResultado:
    """Valida TODO el archivo antes de escribir NADA. Si `validate_rows`
    reporta cualquier error, retorna de inmediato (`ok=False`) sin haber
    tocado la sesión -- ni un `db.add`, ni un `db.commit`. Solo si el
    archivo entero es válido se hace upsert fila por fila y se hace UN
    `commit()` al final (transacción única, spec "A fully valid file
    commits atomically")."""
    total_filas = len(rows)
    valid_rows, row_errors = validate_rows(entidad, rows)

    if row_errors:
        return CargaResultado(
            ok=False,
            total_filas=total_filas,
            errores=[CargaErrorRow(fila=e["fila"], motivo=e["motivo"]) for e in row_errors],
        )

    insertados = 0
    actualizados = 0
    advertencias: List[Dict[str, Any]] = []

    for index, row in enumerate(valid_rows, start=1):
        created, row_warnings = await _upsert_row(db, entidad, row, usuario_id)
        if created:
            insertados += 1
        else:
            actualizados += 1
        if row_warnings:
            advertencias.append({"fila": index, "advertencias": row_warnings})

    await db.commit()

    return CargaResultado(
        ok=True,
        total_filas=total_filas,
        insertados=insertados,
        actualizados=actualizados,
        advertencias=advertencias,
    )
