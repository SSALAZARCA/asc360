"""
Motored Pedidos — parseo server-side de archivos `.xlsx` para carga masiva
de maestros (sdd/motored-pedidos-cimientos, batch post-Fase-6).

Contexto: `services/carga.py`/`api/carga.py` (Fase 1/4) reciben filas YA
ESTRUCTURADAS (`CargaRequest.filas: list[dict]`) — el parseo del archivo
original quedaba explícitamente fuera de ese slice y lo resolvía el
frontend en el browser con `papaparse` para `.csv`
(`frontend/components/motored/maestros/BulkUploadModal.js`). Para `.xlsx`
NO se agrega una librería JS de parseo (`xlsx`/SheetJS tiene 2 CVEs HIGH sin
parche publicado a npm) -- en su lugar, este módulo parsea el archivo acá,
server-side, con `openpyxl` (ya es dependencia del backend, usada por
`app/services/imports_service.py` para el mismo propósito en el resto del
repo -- este módulo es una implementación Motored-local independiente, sin
importar nada de `imports_service.py`, para no acoplar los dos dominios).

`ALIASES_POR_ENTIDAD` es un PUERTO A PYTHON deliberado y manual de
`COLUMNAS_POR_ENTIDAD` (`BulkUploadModal.js`) -- mismas claves canónicas,
mismos alias, misma bandera `required`. Mantener las dos copias sincronizadas
a mano es un tradeoff aceptado (no hay forma limpia de compartir una
constante entre JS y Python en este repo); si se agrega/renombra una columna
en un lado, hay que replicarlo acá.

Una vez parseadas a `list[dict]` con las mismas claves canónicas que ya
produce el camino JSON, las filas se validan/insertan con EXACTAMENTE la
misma `validate_rows`/`procesar_carga` que ya usa ese camino -- cero lógica
de validación/upsert duplicada, sólo cambia cómo llegan las filas.
"""
import io
import re
import unicodedata
from decimal import Decimal
from typing import Any, Dict, List, Optional, get_args

import openpyxl

from app.config import settings
from app.motored.services.validators import _SCHEMA_BY_ENTIDAD


class CargaExcelError(Exception):
    """Base para cualquier error de parseo de un archivo Excel de carga
    masiva -- el caller (router) la traduce a un 400 genérico salvo que sea
    una de las subclases más específicas de abajo."""


class ColumnaObligatoriaFaltanteError(CargaExcelError):
    """Falta una columna requerida en el encabezado -- mismo mensaje que el
    check equivalente del frontend (`missingRequiredColumns` en
    `BulkUploadModal.js`), para que el usuario vea el mismo texto sin
    importar si subió `.csv` (validado en el browser) o `.xlsx` (validado
    acá)."""


class ArchivoExcelInvalidoError(CargaExcelError):
    """El archivo no se pudo abrir como un `.xlsx` válido (corrupto, vacío,
    o no es realmente un archivo Excel a pesar de la extensión) -- SIEMPRE
    se traduce a 400, nunca debe llegar a un 500 sin manejar."""


class FormatoNoSoportadoError(CargaExcelError):
    """Extensión no soportada. Incluye el caso explícito de `.xls` (formato
    binario legado que `openpyxl` no puede leer) -- alcance deliberadamente
    NO cubierto (no se agrega `xlrd` ni ninguna otra dependencia para eso)."""


class LimiteFilasExcedidoError(CargaExcelError):
    """El archivo supera `settings.MOTORED_MAX_UPLOAD_ROWS`. Se distingue de
    las demás porque el router la traduce a 422 (mismo código que el guard
    equivalente del camino JSON, `_check_size_guards`), no a 400."""


# ---------------------------------------------------------------------------
# Puerto manual de `COLUMNAS_POR_ENTIDAD` (BulkUploadModal.js) -- ver
# docstring del módulo. `aliases` no necesita variantes sin tilde: el
# encabezado del Excel Y cada alias se normalizan con `_normalize_header`
# antes de compararse, así que una sola forma (con o sin tilde) alcanza.
# ---------------------------------------------------------------------------
ALIASES_POR_ENTIDAD: Dict[str, List[Dict[str, Any]]] = {
    "sucursal": [
        {"key": "nombre", "label": "Nombre", "required": True, "aliases": ["nombre", "sucursal"]},
        {"key": "sic", "label": "SIC", "required": False, "aliases": ["sic"]},
        {
            "key": "dias_seguridad", "label": "Días de seguridad", "required": False,
            "aliases": ["dias_seguridad", "dias seguridad", "días de seguridad", "días seguridad"],
        },
        {
            "key": "dias_empaque", "label": "Días de empaque", "required": False,
            "aliases": ["dias_empaque", "dias empaque", "días de empaque", "días empaque"],
        },
        {
            "key": "dias_transito", "label": "Días de tránsito", "required": False,
            "aliases": ["dias_transito", "dias transito", "días de tránsito", "días tránsito"],
        },
        {
            "key": "bodega_principal", "label": "Bodega principal", "required": False,
            "aliases": ["bodega_principal", "bodega principal"],
        },
        {"key": "departamento", "label": "Departamento", "required": False, "aliases": ["departamento"]},
        {"key": "ciudad", "label": "Ciudad", "required": False, "aliases": ["ciudad"]},
        {
            "key": "fecha_apertura", "label": "Fecha de apertura", "required": False,
            "aliases": ["fecha_apertura", "fecha apertura"],
        },
    ],
    # Nota de alcance (idéntica a la del frontend): la sucursal de cada
    # bodega NO se asigna por Excel en esta carga masiva.
    "bodega": [
        {"key": "codigo", "label": "Código", "required": True, "aliases": ["codigo", "código", "bodega"]},
        {"key": "descripcion", "label": "Descripción", "required": False, "aliases": ["descripcion", "descripción"]},
        {
            "key": "bodega_principal", "label": "Bodega principal", "required": False,
            "aliases": ["bodega_principal", "bodega principal"],
        },
    ],
    "proveedor": [
        {"key": "codigo", "label": "Código", "required": True, "aliases": ["codigo", "código", "proveedor"]},
        {"key": "nombre", "label": "Nombre", "required": True, "aliases": ["nombre"]},
        {
            "key": "es_principal", "label": "Principal (Sí/No)", "required": False, "type": "boolean",
            "aliases": ["es_principal", "principal", "principal (si/no)", "principal (sí/no)"],
        },
        {
            "key": "dias_seguridad_default", "label": "Días de seguridad (por defecto)", "required": False,
            "aliases": [
                "dias_seguridad_default", "dias seguridad default",
                "días de seguridad (por defecto)",
            ],
        },
    ],
    # `proveedor_codigo` (no el id) -- igual que el camino CSV, el router de
    # `api/carga.py` resuelve ese código al id real antes de escribir.
    "referencia": [
        {"key": "codigo", "label": "Código", "required": True, "aliases": ["codigo", "código", "referencia"]},
        {
            "key": "proveedor_codigo", "label": "Código del proveedor", "required": True, "type": "string",
            "aliases": ["proveedor_codigo", "codigo proveedor", "código proveedor", "proveedor"],
        },
        {"key": "nombre", "label": "Nombre", "required": False, "aliases": ["nombre"]},
        {
            "key": "linea_comercial", "label": "Línea comercial", "required": False,
            "aliases": ["linea_comercial", "línea comercial"],
        },
        {
            "key": "unidad_empaque", "label": "Unidad de empaque", "required": False,
            "aliases": ["unidad_empaque", "unidad de empaque"],
        },
        {
            "key": "precio_normal", "label": "Precio normal", "required": False,
            "aliases": ["precio_normal", "precio normal"],
        },
    ],
}

_BOOLEAN_TRUE_VALUES = {"si", "sí", "true", "1", "yes", "x"}
_SIMPLE_COMMA_DECIMAL_RE = re.compile(r"^-?\d+,\d+$")


def _field_kind_by_key(entidad: str) -> Dict[str, str]:
    """Inspecciona el schema Pydantic real (`_SCHEMA_BY_ENTIDAD`) para saber
    qué campos son texto (`str`) y cuáles numéricos (`int`/`float`/
    `Decimal`) -- openpyxl devuelve cada celda con su tipo NATIVO (número,
    texto, fecha), que no siempre coincide con lo que el schema espera: un
    número real en una celda de un campo `str` (ej. `sic` escrito sin
    comillas) rompe la validación ("Input should be a valid string") a
    menos que se convierta a texto acá. Se usa el schema como única fuente
    de verdad en vez de anotar el tipo una tercera vez a mano (ya vive en el
    modelo y en el schema)."""
    schema_cls = _SCHEMA_BY_ENTIDAD.get(entidad)
    if schema_cls is None:
        return {}

    kinds: Dict[str, str] = {}
    for name, field in schema_cls.model_fields.items():
        args = [a for a in get_args(field.annotation) if a is not type(None)]
        real_type = args[0] if args else field.annotation
        if real_type is str:
            kinds[name] = "string"
        elif real_type in (int, float, Decimal):
            kinds[name] = "numeric"
    return kinds


def _normalize_comma_decimal(value: str) -> str:
    """Convierte "2,5" a "2.5" -- una celda de Excel en configuración
    regional en español a veces queda guardada como texto literal con coma
    decimal en vez de convertirse a un número real, y `Decimal("2,5")`
    lanza `InvalidOperation`. Solo actúa sobre el patrón simple
    dígitos,dígitos (sin separador de miles) para no corromper un valor con
    formato ambiguo (ej. "15.000,50")."""
    if _SIMPLE_COMMA_DECIMAL_RE.match(value):
        return value.replace(",", ".")
    return value


def _normalize_header(value: Any) -> str:
    """Mismo criterio que `normalizeHeader` en `BulkUploadModal.js`: saca
    tildes/diacríticos, recorta espacios, pasa a minúsculas -- para que
    "Días de seguridad", "dias_seguridad" y "DIAS SEGURIDAD" comparen
    igual."""
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFD", str(value))
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return without_accents.strip().lower()


def _to_boolean(value: Any) -> bool:
    """Mismo criterio que `toBoolean` en `BulkUploadModal.js`."""
    return str(value).strip().lower() in _BOOLEAN_TRUE_VALUES


def _build_column_map(spec: List[Dict[str, Any]], raw_headers: List[str]) -> Dict[int, str]:
    """Retorna {índice_de_columna (0-based) -> clave_canónica} para las
    columnas del encabezado que matchean algún alias conocido."""
    normalized_headers = [_normalize_header(h) for h in raw_headers]
    column_map: Dict[int, str] = {}
    for col in spec:
        normalized_aliases = {_normalize_header(a) for a in col["aliases"]}
        for idx, header in enumerate(normalized_headers):
            if header in normalized_aliases:
                column_map[idx] = col["key"]
                break
    return column_map


def _missing_required_columns(spec: List[Dict[str, Any]], column_map: Dict[int, str]) -> List[str]:
    """Retorna la LABEL (no la clave canónica) de cada columna obligatoria
    ausente -- mismo criterio que `missingRequiredColumns` en
    `BulkUploadModal.js`, para que el mensaje sea legible por un usuario de
    negocio, no una clave interna."""
    present_keys = set(column_map.values())
    return [col["label"] for col in spec if col["required"] and col["key"] not in present_keys]


def _validate_filename(filename: Optional[str]) -> None:
    """Rechaza `.xls` (formato legado, `openpyxl` no lo lee -- no se agrega
    `xlrd`) y cualquier extensión que no sea `.xlsx`, ANTES de tocar el
    archivo."""
    lower_name = (filename or "").lower()
    if lower_name.endswith(".xls"):
        raise FormatoNoSoportadoError(
            "Formato .xls no soportado -- convertí el archivo a .xlsx antes de subirlo."
        )
    if not lower_name.endswith(".xlsx"):
        raise FormatoNoSoportadoError("Solo se acepta el formato .xlsx.")


def _resolve_spec(entidad: str) -> List[Dict[str, Any]]:
    spec = ALIASES_POR_ENTIDAD.get(entidad)
    if spec is None:
        raise ArchivoExcelInvalidoError(f"Maestro desconocido: '{entidad}'")
    return spec


def _open_workbook(file_bytes: bytes):
    """`read_only=True`: streaming, no materializa la hoja completa en
    memoria -- necesario para que el guard de filas de `_build_canonical_
    rows` pueda abortar a mitad de parseo."""
    try:
        return openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as exc:  # cualquier fallo de openpyxl -> 400, nunca 500
        raise ArchivoExcelInvalidoError(
            "No se pudo leer el archivo. Verificá que sea un .xlsx válido."
        ) from exc


def _read_validated_column_map(rows_iter, spec: List[Dict[str, Any]]) -> Dict[int, str]:
    """Lee la fila de encabezado (consume el primer `next()` del iterador) y
    la mapea a claves canónicas, rechazando si falta alguna columna
    obligatoria -- mismo criterio que `missingRequiredColumns` en
    `BulkUploadModal.js`."""
    try:
        raw_headers = next(rows_iter)
    except StopIteration:
        raise ArchivoExcelInvalidoError("El archivo está vacío.")

    raw_headers = [h if h is not None else "" for h in raw_headers]
    column_map = _build_column_map(spec, raw_headers)

    faltantes_labels = _missing_required_columns(spec, column_map)
    if faltantes_labels:
        raise ColumnaObligatoriaFaltanteError(
            f"Al archivo le falta la columna obligatoria: {', '.join(faltantes_labels)}"
        )
    return column_map


def _build_canonical_rows(
    rows_iter, spec: List[Dict[str, Any]], column_map: Dict[int, str], max_rows: int, field_kinds: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Itera las filas de datos (después del encabezado) y las convierte a
    la forma canónica, enforzando `max_rows` MIENTRAS itera (streaming) --
    aborta apenas se excede, nunca materializa de más antes de rechazar.

    `field_kinds` normaliza el desfase de tipos entre lo que openpyxl
    devuelve (tipo nativo de la celda) y lo que el schema espera: un valor
    numérico en un campo `str` se convierte a texto (bug real: "sic" como
    número entero o decimal rompía la validación sin importar el separador
    decimal, porque el problema nunca fue el formato del número, sino que
    dejaba de ser texto); un valor string con coma decimal en un campo
    numérico se normaliza a punto. `type_by_key` cubre además las claves
    que NO son un campo real del schema (ej. `proveedor_codigo`, que
    `api/carga.py` resuelve aparte contra `Proveedor.codigo`) vía
    `"type": "string"` explícito en `ALIASES_POR_ENTIDAD`."""
    type_by_key = {col["key"]: col.get("type") for col in spec}

    rows: List[Dict[str, Any]] = []
    for row_values in rows_iter:
        if row_values is None or all(v is None for v in row_values):
            continue  # fila vacía -- mismo criterio que `skipEmptyLines` de papaparse

        if len(rows) >= max_rows:
            raise LimiteFilasExcedidoError(f"El archivo supera el límite de {max_rows} filas")

        canonical: Dict[str, Any] = {}
        for idx, key in column_map.items():
            value = row_values[idx] if idx < len(row_values) else None
            kind = field_kinds.get(key) or (type_by_key.get(key) if type_by_key.get(key) == "string" else None)

            if kind == "string" and value is not None and not isinstance(value, str):
                value = str(value)

            if isinstance(value, str):
                value = value.strip()
                if kind == "numeric":
                    value = _normalize_comma_decimal(value)

            if type_by_key.get(key) == "boolean":
                value = _to_boolean(value)
            canonical[key] = value
        rows.append(canonical)

    return rows


def parse_excel_rows(entidad: str, filename: Optional[str], file_bytes: bytes) -> List[Dict[str, Any]]:
    """Parsea un `.xlsx` a `list[dict]` con las mismas claves canónicas que
    ya produce el camino JSON (`rowsToCanonical` en el frontend). Solo
    orquesta el orden -- cada paso vive en su propia función (`_validate_
    filename`, `_resolve_spec`, `_open_workbook`, `_read_validated_column_
    map`, `_build_canonical_rows`).

    `settings.MOTORED_MAX_UPLOAD_MB` se enforza vía `Content-Length` en el
    router (`api/carga.py`), igual que en el camino JSON -- este módulo no
    conoce el tamaño del request HTTP, solo el límite de FILAS.
    """
    _validate_filename(filename)
    spec = _resolve_spec(entidad)
    field_kinds = _field_kind_by_key(entidad)
    workbook = _open_workbook(file_bytes)

    try:
        rows_iter = workbook.active.iter_rows(values_only=True)
        column_map = _read_validated_column_map(rows_iter, spec)
        return _build_canonical_rows(rows_iter, spec, column_map, settings.MOTORED_MAX_UPLOAD_ROWS, field_kinds)
    finally:
        workbook.close()
