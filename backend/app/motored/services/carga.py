"""
Motored Pedidos — carga masiva de maestros (sdd/motored-pedidos-cimientos,
Fase 3, task 3.4, ADR-6). Todo-o-nada (owner decision #1): se valida el
archivo COMPLETO primero (`validators.validate_rows`, que acumula TODOS los
errores en un solo pase); si hay AL MENOS una fila inválida, no se escribe
absolutamente nada y se retorna el reporte completo. Un archivo totalmente
válido se sube en una única transacción, con upsert por llave natural
(owner decision #2; `referencia` por `codigo`), reutilizando exactamente las mismas funciones de
`services/maestros.py` que usa el CRUD unitario -- una sola fuente de
verdad para la coerción de `unidad_empaque` y el trim de `sucursal.nombre`.

`referencia` es la excepción (motored-referencia-identidad, R2): su carga es
un REEMPLAZO COMPLETO (`services/reemplazo_referencias.py`) -- celda en blanco
borra, las ausentes se desactivan, resumen previo y confirmaciones.

Nota de alcance (Fase 1): para `referencia`, la resolución de
`proveedor_codigo` -> `proveedor_id` es responsabilidad del llamador (router
de Fase 4, que arma cada fila del Excel con el `proveedor_id` ya resuelto
contra un caché de proveedores). Esta función exige que la fila ya traiga
`proveedor_id`; solo usa `proveedor_codigo` para el mensaje de validación
"campo requerido".
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.motored.schemas.carga import CargaErrorRow, CargaResultado
from app.motored.services import (
    bodegas_secundarias,
    maestros,
    reemplazo_referencias,
    sucursal_grupo,
)
from app.motored.services.validators import _SCHEMA_BY_ENTIDAD, ENTIDADES_DE_REEMPLAZO, validate_rows

_UPSERT_BY_ENTIDAD = {
    "sucursal": maestros.upsert_sucursal,
    "bodega": maestros.upsert_bodega,
    "proveedor": maestros.upsert_proveedor,
    "vendedor": maestros.upsert_vendedor,
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
    try:
        await db.commit()
    except IntegrityError:
        # Otra carga reemplazo la lista entre el DELETE y este COMMIT y choco
        # con el indice unico: se ve como un conflicto, no como un 500.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Otra carga está reemplazando esta lista en este momento. "
                "Espere unos segundos y vuelva a subir el archivo."
            ),
        )
    return CargaResultado(
        ok=True,
        total_filas=len(valid_rows),
        insertados=insertados,
        eliminados=eliminados,
        advertencias=advertencias,
    )


def _conflicto(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)


async def _reemplazar_referencias(
    db,
    valid_rows: List[Dict[str, Any]],
    usuario_id: Optional[uuid.UUID],
    confirmar_reemplazo: bool,
    confirmar_inactivacion_masiva: bool,
    codigos_inactivar: Optional[List[str]] = None,
) -> CargaResultado:
    """Aplica el reemplazo completo de referencias en UNA transacción. El plan
    y el resumen se RECALCULAN acá contra el estado actual y el archivo que
    llegó a este request (no se confía en lo que `validar` mostró): si exige la
    doble confirmación y no vino, 409 sin escribir nada."""
    if not confirmar_reemplazo:
        raise _conflicto(
            "La carga de referencias reemplaza el maestro completo: las celdas en blanco borran lo guardado "
            "y solo se inactivan las referencias ausentes que usted elija. "
            "Revise el resumen y confirme el reemplazo."
        )

    plan = await reemplazo_referencias.planificar(db, valid_rows)
    if plan.errores:
        return CargaResultado(
            ok=False,
            total_filas=len(valid_rows),
            errores=[CargaErrorRow(fila=e["fila"], motivo=e["motivo"]) for e in plan.errores],
        )

    try:
        a_inactivar = reemplazo_referencias.elegir_inactivar(plan, codigos_inactivar)
    except reemplazo_referencias.SeleccionInvalida as exc:
        raise _conflicto(str(exc))

    resumen = reemplazo_referencias.construir_resumen(plan, codigos_inactivar, con_lista=False)
    if resumen.requiere_doble_confirmacion and not confirmar_inactivacion_masiva:
        raise _conflicto(
            f"Este archivo desactivaría {resumen.seleccionadas + resumen.inactivar_por_sustituta.total} "
            f"de {resumen.activas_actuales} referencias "
            f"activas ({resumen.pct_inactivar:.0%}), más del 10%. Confirme la desactivación masiva para continuar."
        )

    try:
        await reemplazo_referencias.aplicar(db, plan, resumen, usuario_id, a_inactivar)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _conflicto(
            "Otra carga modificó las referencias en este momento. Espere unos segundos y vuelva a subir el archivo."
        )
    return CargaResultado(
        ok=True,
        total_filas=len(valid_rows),
        insertados=len(plan.nuevas),
        actualizados=plan.modificadas,
        advertencias=plan.advertencias_por_fila(),
        resumen_reemplazo=resumen,
    )


async def _aplicar_columnas_de_sucursal(
    db, subidas: List[tuple], usuario_id: Optional[uuid.UUID]
):
    """Sucursales columns that are not schema fields, applied after every
    row was upserted: "Bodegas secundarias" and "Sucursal principal".
    Returns the secondary-bodegas summary, or None without that column."""
    secundarias = [
        (obj, fila[bodegas_secundarias.FILA_CLAVE]) for obj, fila in subidas
        if bodegas_secundarias.FILA_CLAVE in fila
    ]
    principales = [
        (obj, fila[sucursal_grupo.FILA_CLAVE]) for obj, fila in subidas
        if sucursal_grupo.FILA_CLAVE in fila
    ]
    resumen = None
    if secundarias:
        resumen = await bodegas_secundarias.aplicar(
            db, secundarias, usuario_id
        )
    if principales:
        await sucursal_grupo.aplicar(
            db, principales, [obj for obj, _ in subidas], usuario_id
        )
    return resumen


async def procesar_carga(
    db,
    entidad: str,
    rows: List[Dict[str, Any]],
    usuario_id: Optional[uuid.UUID] = None,
    errores_previos: Optional[List[Dict[str, Any]]] = None,
    confirmar_reemplazo: bool = False,
    confirmar_inactivacion_masiva: bool = False,
    codigos_inactivar: Optional[List[str]] = None,
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
    if entidad == "referencia":
        return await _reemplazar_referencias(
            db, valid_rows, usuario_id, confirmar_reemplazo, confirmar_inactivacion_masiva,
            codigos_inactivar,
        )

    insertados = 0
    actualizados = 0
    advertencias: List[Dict[str, Any]] = []
    resumen_bodegas = None

    try:
        subidas: List[tuple] = []  # (obj, fila) in file order
        for index, row in enumerate(valid_rows, start=1):
            obj, created, row_warnings = await _upsert_row(db, entidad, row, usuario_id)
            subidas.append((obj, row))
            if created:
                insertados += 1
            else:
                actualizados += 1
            if row_warnings:
                advertencias.append({"fila": index, "advertencias": row_warnings})

        if entidad == "sucursal":
            resumen_bodegas = await _aplicar_columnas_de_sucursal(
                db, subidas, usuario_id
            )
        await db.commit()
    except IntegrityError:
        # Otra carga creó la misma llave natural (p.ej. la misma bodega
        # secundaria) entre nuestro SELECT y el flush/COMMIT: es un conflicto, no un 500.
        await db.rollback()
        raise _conflicto(
            "Otra carga modificó estos registros en este momento. Espere unos segundos y vuelva a subir el archivo."
        )

    return CargaResultado(
        ok=True,
        total_filas=total_filas,
        insertados=insertados,
        actualizados=actualizados,
        advertencias=advertencias,
        bodegas_secundarias=resumen_bodegas,
    )
