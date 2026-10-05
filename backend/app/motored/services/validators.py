"""
Motored Pedidos — validadores puros (sdd/motored-pedidos-cimientos, Fase 3,
task 3.2/3.3). Sin acceso a base de datos: usados tanto por CRUD unitario
(`services/maestros.py`) como por la carga masiva (`services/carga.py`),
que necesita EXACTAMENTE la misma regla en ambos caminos.

`validate_rows` es el corazón de la regla "todo o nada" (owner decision #1):
recorre TODAS las filas y acumula TODOS los errores en un solo pase --
nunca se detiene en la primera fila inválida (spec "Multiple invalid rows
are all reported at once").
"""
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.motored.schemas.bodega import BodegaCreate
from app.motored.schemas.cliente_tecnired import ClienteTecniredCreate, normalizar_nit
from app.motored.schemas.proveedor import ProveedorCreate
from app.motored.schemas.referencia import ReferenciaCreate
from app.motored.schemas.sucursal import (
    SucursalCreate,
    motivo_codigo_co_invalido,
    normalizar_codigo_co,
)
from app.motored.schemas.vendedor import VendedorCreate, limpiar_cedula, normalizar_cargo_de_fila
from app.motored.services.texto import normalizar_encabezado

Row = Dict[str, Any]
RowError = Dict[str, Any]

_SCHEMA_BY_ENTIDAD = {
    "sucursal": SucursalCreate,
    "bodega": BodegaCreate,
    "proveedor": ProveedorCreate,
    "referencia": ReferenciaCreate,
    "cliente_tecnired": ClienteTecniredCreate,
    "vendedor": VendedorCreate,
}

# Entidades cuya carga REEMPLAZA la lista completa (en vez de upsert por llave
# natural). Un archivo sin filas se rechaza: borraria la lista entera.
ENTIDADES_DE_REEMPLAZO = frozenset({"cliente_tecnired"})


def coerce_unidad_empaque(value: Optional[int]) -> Tuple[int, Optional[str]]:
    """`referencia.unidad_empaque` JAMÁS se guarda como 0 (proposal §4.1/
    §5.8, spec "unidad_empaque coercion"). `None`, `0` o cualquier valor
    no positivo se corrige a 1 y se devuelve una advertencia identificando
    el caso; un valor positivo válido se retorna intacto, sin advertencia."""
    if value is None or value <= 0:
        return 1, "unidad_empaque era 0/nulo/negativo -- corregido a 1"
    return value, None


def normalize_sucursal_nombre(nombre: str) -> str:
    """`sucursal.nombre` es UNIQUE y canónico; los exports del ERP llegan
    con espacios sobrantes (proposal §5, H11) -- el trim es obligatorio
    antes de persistir o comparar (spec "Trailing-whitespace sucursal name
    is normalized")."""
    return nombre.strip()


# ---------------------------------------------------------------------------
# Validación de filas de carga masiva -- acumula TODOS los errores, nunca
# falla en la primera fila inválida (owner decision #1 / spec "Bulk Excel
# upload is all-or-nothing").
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "sucursal": ["nombre"],
    "bodega": ["codigo"],
    "proveedor": ["codigo", "nombre"],
    "referencia": ["codigo", "proveedor_codigo"],
    "cliente_tecnired": ["nit"],
    "vendedor": ["nombre", "cargo", "cedula"],
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _validate_single_row(entidad: str, row: Row) -> List[str]:
    """Retorna la lista de motivos de error para UNA fila (vacía si la fila
    es válida). No incluye advertencias -- esas no rechazan la fila."""
    reasons: List[str] = []
    for field in REQUIRED_FIELDS.get(entidad, []):
        if _is_blank(row.get(field)):
            reasons.append(f"Campo requerido '{field}' vacío o ausente")
    return reasons


def _strip_blank_values(row: Row) -> Row:
    """Una celda en blanco (columna presente en el archivo, sin valor para
    esa fila) significa "no provisto", en TODOS los caminos: `.csv`
    (papaparse) la entrega como `""`; `.xlsx` la entrega como `""` también
    (`carga_excel` normaliza el `None` de openpyxl), y un cliente JSON puede
    mandar `null`. Se sacan ACÁ las claves con `None`, `""` o solo espacios,
    antes de cualquier coerción/validación de schema: así nunca llegan como
    kwarg explícito al `*Create`, y el `model_dump(exclude_unset=True)` del
    upsert NO pisa el valor ya guardado (bug real, review 2026-09-28: un
    `None` de `.xlsx` sobrevivía y borraba `nombre`, `homologados`, etc. en
    cada actualización). Además evita los bugs originales: "" en un Decimal
    opcional rechazaba la fila, y "" en `unidad_empaque` crasheaba
    `coerce_unidad_empaque` (`str <= int`)."""
    return {k: v for k, v in row.items() if not _is_blank(v)}


def _apply_entity_normalizations(entidad: str, cleaned: Row) -> List[str]:
    """Aplica los trims/coerciones específicos por entidad IN-PLACE sobre
    `cleaned` y retorna las advertencias no bloqueantes resultantes."""
    warnings: List[str] = []

    if entidad == "sucursal" and isinstance(cleaned.get("nombre"), str):
        cleaned["nombre"] = normalize_sucursal_nombre(cleaned["nombre"])

    if entidad == "cliente_tecnired" and isinstance(cleaned.get("nit"), str):
        cleaned["nit"] = normalizar_nit(cleaned["nit"])

    # Solo si vino un valor: un `unidad_empaque` ausente/en blanco es "no
    # provisto" (un update conserva el guardado; `create_referencia` pone 1
    # con advertencia para una referencia nueva).
    if entidad == "referencia" and "unidad_empaque" in cleaned:
        coerced_value, warning = coerce_unidad_empaque(cleaned.get("unidad_empaque"))
        cleaned["unidad_empaque"] = coerced_value
        if warning:
            warnings.append(warning)

    return warnings


_ACTIVA_SI = frozenset({"si", "s", "yes", "y", "true", "1", "x"})
_ACTIVA_NO = frozenset({"no", "n", "false", "0"})


def _activa_error(entidad: str, cleaned: Row) -> Optional[str]:
    """Interpreta la columna "Activa" de una sucursal IN-PLACE con un Sí/No
    estricto (sin importar mayúsculas ni tildes). A diferencia de
    `carga_excel._to_boolean`, un texto desconocido NO se vuelve False: es
    un error de fila, porque inactivar una tienda por un typo no se nota.
    Una celda en blanco ya no llega acá (`_strip_blank_values`). Retorna el
    motivo del error, o `None`."""
    valor = cleaned.get("activa")
    if entidad != "sucursal" or valor is None or isinstance(valor, bool):
        return None
    texto = normalizar_encabezado(valor)
    if texto in _ACTIVA_SI or texto in _ACTIVA_NO:
        cleaned["activa"] = texto in _ACTIVA_SI
        return None
    return (
        f"Columna 'Activa': el valor '{valor}' no es válido. "
        "Escriba Sí o No, o deje la celda en blanco."
    )


def _codigo_co_error(entidad: str, cleaned: Row) -> Optional[str]:
    """Normalizes the "Código C.O." cell IN-PLACE (trim, upper case) and
    checks its format, naming the column. A blank cell already left
    (`_strip_blank_values`): it keeps the stored code. Uniqueness needs the
    database: `maestros.errores_codigo_co_carga`."""
    if entidad != "sucursal" or "codigo_co" not in cleaned:
        return None
    codigo = normalizar_codigo_co(cleaned["codigo_co"])
    cleaned["codigo_co"] = codigo
    motivo = motivo_codigo_co_invalido(codigo)
    return f"Columna 'Código C.O.': {motivo}" if motivo else None


def _sucursal_error(entidad: str, cleaned: Row) -> Optional[str]:
    """Sucursal columns checked before the schema: "Activa" and "Código
    C.O." (both normalize the row IN-PLACE). The first reason, or None."""
    return _activa_error(entidad, cleaned) or _codigo_co_error(
        entidad, cleaned
    )


def _schema_validation_error(entidad: str, cleaned: Row) -> Optional[str]:
    """Un campo requerido presente pero con formato inválido (p.ej.
    `proveedor_id: "no-es-un-uuid"`, `precio_normal: "abc"`) pasa el chequeo
    de "no vacío" de `_validate_single_row`, pero rompería recién al
    escribir -- adentro del loop de `services/carga.py::procesar_carga`,
    DESPUÉS de haber decidido "archivo válido, proceder a escribir". Eso
    violaría todo-o-nada: algunas filas ya habrían pasado por `db.add` antes
    del crash. Construir el schema Pydantic ACÁ, durante la validación (y
    descartar el resultado -- `carga.py` reconstruye el mismo schema desde
    este mismo dict ya limpio, sin riesgo de que falle distinto la segunda
    vez), mueve ese error al único lugar donde "todo o nada" puede
    cumplirse: antes de tocar la sesión. Retorna el motivo del error, o
    `None` si el schema construye sin problema."""
    schema_cls = _SCHEMA_BY_ENTIDAD.get(entidad)
    if schema_cls is None:
        return None

    payload = {k: v for k, v in cleaned.items() if k != "_warnings"}
    try:
        schema_cls(**payload)
    except ValidationError as exc:
        return "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
    return None


def _advertencias_cedula_compartida(valid_rows: List[Row]) -> None:
    """Una persona puede estar en el ERP con varios nombres y por eso aparecer
    en varias filas con la MISMA cedula (el maestro guarda una fila por nombre
    del ERP). Si esas filas difieren en cargo o sucursal no es un error, pero
    se avisa en la fila que difiere de la primera con esa cedula. Edita
    `_warnings` IN-PLACE."""
    primera_por_cedula: Dict[str, Row] = {}
    for row in valid_rows:
        cedula = limpiar_cedula(row["cedula"])
        primera = primera_por_cedula.setdefault(cedula, row)
        if primera is row:
            continue
        diferencias = []
        if normalizar_cargo_de_fila(primera["cargo"]) != normalizar_cargo_de_fila(row["cargo"]):
            diferencias.append("cargo")
        if primera.get("sucursal_id") != row.get("sucursal_id"):
            diferencias.append("sucursal")
        if diferencias:
            row["_warnings"].append(
                f"La cédula {cedula} ya está en la fila de '{primera['nombre']}' con otro "
                f"{' y otra '.join(diferencias)}: se guarda igual, revise que sea la misma persona."
            )


def validate_rows(entidad: str, rows: List[Row]) -> Tuple[List[Row], List[RowError]]:
    """Valida TODAS las filas de una carga masiva para `entidad` en un solo
    pase. Retorna `(filas_validas, errores)`:

    - `filas_validas`: copia de cada fila que pasó, con las coerciones ya
      aplicadas (p.ej. `unidad_empaque` normalizado a 1, `nombre` trimmed) y
      una clave `_warnings` (lista, puede estar vacía) con advertencias no
      bloqueantes de esa fila.
    - `errores`: uno por cada fila que falló, con `fila` (1-indexado) y
      `motivo`. Nunca se detiene en la primera fila inválida -- reúne TODAS
      antes de retornar (spec "Multiple invalid rows are all reported at
      once").

    Un `errores` no vacío es la señal de "todo o nada": la fila-completa
    debe rechazarse SIN escribir nada (lo decide `services/carga.py`;
    esta función solo reporta y orquesta el orden de los pasos).
    """
    valid_rows: List[Row] = []
    errors: List[RowError] = []

    if entidad in ENTIDADES_DE_REEMPLAZO and not rows:
        return valid_rows, [{
            "fila": 0,
            "motivo": "El archivo no tiene filas: no se reemplaza la lista actual. "
                      "Cargá al menos una fila.",
        }]

    for index, row in enumerate(rows, start=1):
        reasons = _validate_single_row(entidad, row)
        if reasons:
            for reason in reasons:
                errors.append({"fila": index, "motivo": reason})
            continue

        cleaned = _strip_blank_values(dict(row))
        warnings = _apply_entity_normalizations(entidad, cleaned)

        row_error = _sucursal_error(entidad, cleaned)
        row_error = row_error or _schema_validation_error(entidad, cleaned)
        if row_error:
            errors.append({"fila": index, "motivo": row_error})
            continue

        cleaned["_warnings"] = warnings
        valid_rows.append(cleaned)

    if entidad == "vendedor":
        _advertencias_cedula_compartida(valid_rows)

    return valid_rows, errors
