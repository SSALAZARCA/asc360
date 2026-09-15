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
from app.motored.schemas.proveedor import ProveedorCreate
from app.motored.schemas.referencia import ReferenciaCreate
from app.motored.schemas.sucursal import SucursalCreate

Row = Dict[str, Any]
RowError = Dict[str, Any]

_SCHEMA_BY_ENTIDAD = {
    "sucursal": SucursalCreate,
    "bodega": BodegaCreate,
    "proveedor": ProveedorCreate,
    "referencia": ReferenciaCreate,
}


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
    debe rechazarse SIN escribir nada (esa decisión la toma
    `services/carga.py`, esta función solo reporta).
    """
    valid_rows: List[Row] = []
    errors: List[RowError] = []

    for index, row in enumerate(rows, start=1):
        reasons = _validate_single_row(entidad, row)
        if reasons:
            for reason in reasons:
                errors.append({"fila": index, "motivo": reason})
            continue

        cleaned = dict(row)
        warnings: List[str] = []

        if entidad == "sucursal" and isinstance(cleaned.get("nombre"), str):
            cleaned["nombre"] = normalize_sucursal_nombre(cleaned["nombre"])

        if entidad == "referencia":
            coerced_value, warning = coerce_unidad_empaque(cleaned.get("unidad_empaque"))
            cleaned["unidad_empaque"] = coerced_value
            if warning:
                warnings.append(warning)

        # Un campo requerido presente pero con formato inválido (p.ej.
        # `proveedor_id: "no-es-un-uuid"`, `precio_normal: "abc"`) pasa el
        # chequeo de "no vacío" de arriba, pero rompería recién al escribir
        # -- adentro del loop de `services/carga.py::procesar_carga`, DESPUÉS
        # de haber decidido "archivo válido, proceder a escribir". Eso
        # violaría todo-o-nada: algunas filas ya habrían pasado por `db.add`
        # antes del crash. Construir el schema Pydantic ACÁ, durante la
        # validación (y descartar el resultado -- `carga.py` reconstruye el
        # mismo schema desde este mismo dict ya limpio, sin riesgo de que
        # falle distinto la segunda vez), mueve ese error al único lugar
        # donde "todo o nada" puede cumplirse: antes de tocar la sesión.
        schema_cls = _SCHEMA_BY_ENTIDAD.get(entidad)
        if schema_cls is not None:
            payload = {k: v for k, v in cleaned.items() if k != "_warnings"}
            try:
                schema_cls(**payload)
            except ValidationError as exc:
                motivo = "; ".join(
                    f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()
                )
                errors.append({"fila": index, "motivo": motivo})
                continue

        cleaned["_warnings"] = warnings
        valid_rows.append(cleaned)

    return valid_rows, errors
