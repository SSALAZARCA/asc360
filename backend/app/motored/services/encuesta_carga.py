"""
Motored satisfaction survey (slice T3) -- parsing and validation of the
customer-base Excel (Nombre, Cedula, Celular, Linea, Placa, SIC, Centro de
servicio, Tipo).

Reuses the generic pieces of `carga_excel.py` (filename check, read-only
workbook, header alias mapping, blank-row skipping, row cap) and only adds the
survey-specific normalization. Validation is all-or-nothing: the caller writes
nothing when `validar_filas` returns any error.
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.motored.services.carga_excel import (
    _build_canonical_rows,
    _open_workbook,
    _read_validated_column_map,
    _validate_filename,
)

TIPO_SERVICIO_TALLER = "SERVICIO_TALLER"
TIPO_VENTA = "VENTA"
CEDULA_MAX_LENGTH = 32
CELULAR_MIN_DIGITS = 7

COLUMNS: List[Dict[str, Any]] = [
    {"key": "nombre", "label": "Nombre", "required": True, "type": "string",
     "aliases": ["nombre", "nombre cliente", "nombre del cliente"]},
    {"key": "cedula", "label": "Cédula", "required": True, "type": "string",
     "aliases": ["cedula", "cédula"]},
    {"key": "celular", "label": "Celular", "required": True, "type": "string",
     "aliases": ["celular"]},
    {"key": "linea", "label": "Línea", "required": False, "type": "string",
     "aliases": ["linea", "línea"]},
    {"key": "placa", "label": "Placa", "required": True, "type": "string",
     "aliases": ["placa"]},
    {"key": "sic", "label": "SIC", "required": False, "type": "string",
     "aliases": ["sic"]},
    {"key": "centro_servicio", "label": "Centro de servicio", "required": False, "type": "string",
     "aliases": ["centro de servicio", "centro servicio", "nombre del centro de servicio"]},
    {"key": "tipo", "label": "Tipo", "required": True, "type": "string",
     "aliases": ["tipo"]},
]

_TIPO_ALIASES = {
    "servicio taller": TIPO_SERVICIO_TALLER,
    "servicio de taller": TIPO_SERVICIO_TALLER,
    "taller": TIPO_SERVICIO_TALLER,
    "servicio_taller": TIPO_SERVICIO_TALLER,
    "venta": TIPO_VENTA,
}
_EXCEL_FLOAT_RE = re.compile(r"^\d+\.0$")
_TIPOS_ACEPTADOS = "Servicio taller, Venta"


def column_labels() -> List[str]:
    return [col["label"] for col in COLUMNS]


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").strip().lower()


def _digits(value: Any) -> str:
    text = str(value or "").strip()
    if _EXCEL_FLOAT_RE.match(text):  # Excel numeric cell read back as float
        text = text[:-2]
    return re.sub(r"\D", "", text)


def normalize_cedula(value: Any) -> str:
    """Digits-only cedula, the exact form stored by the upload. The public
    survey lookup reuses it so both sides always compare the same text."""
    return _digits(value)


def _normalize_placa(value: Any) -> str:
    return re.sub(r"[\s-]", "", str(value or "")).upper()


def _normalize_tipo(value: Any) -> Optional[str]:
    return _TIPO_ALIASES.get(_fold(str(value or "")))


def _blank_to_none(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def parse_encuesta_excel(filename: Optional[str], file_bytes: bytes) -> List[Dict[str, Any]]:
    """Raises the `CargaExcelError` family (bad extension, unreadable file,
    missing required column, row cap) exactly like the masters upload."""
    _validate_filename(filename)
    workbook = _open_workbook(file_bytes)
    try:
        rows_iter = workbook.active.iter_rows(values_only=True)
        column_map = _read_validated_column_map(rows_iter, COLUMNS)
        return _build_canonical_rows(rows_iter, COLUMNS, column_map, settings.MOTORED_MAX_UPLOAD_ROWS, {})
    finally:
        workbook.close()


def _celular_error(celular: str) -> Optional[str]:
    if not celular:
        return "Celular es obligatorio"
    if len(celular) < CELULAR_MIN_DIGITS:
        return "Celular inválido"
    return None


def _validate_row(raw: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not str(raw.get("nombre") or "").strip():
        return None, "El campo 'Nombre' es obligatorio"
    cedula = normalize_cedula(raw.get("cedula"))
    if not cedula:
        return None, "El campo 'Cédula' es obligatorio y debe contener números"
    if len(cedula) > CEDULA_MAX_LENGTH:
        return None, f"La 'Cédula' supera los {CEDULA_MAX_LENGTH} dígitos permitidos"
    celular = _digits(raw.get("celular"))
    celular_error = _celular_error(celular)
    if celular_error:
        return None, celular_error
    placa = _normalize_placa(raw.get("placa"))
    if not placa:
        return None, "El campo 'Placa' es obligatorio"
    if not str(raw.get("tipo") or "").strip():
        return None, f"El campo 'Tipo' es obligatorio. Valores aceptados: {_TIPOS_ACEPTADOS}"
    tipo = _normalize_tipo(raw.get("tipo"))
    if tipo is None:
        return None, f"'Tipo' '{raw.get('tipo')}' no es válido. Valores aceptados: {_TIPOS_ACEPTADOS}"
    return {
        "nombre": str(raw["nombre"]).strip(),
        "cedula": cedula,
        "celular": celular,
        "linea": _blank_to_none(raw.get("linea")),
        "placa": placa,
        "sic": _blank_to_none(raw.get("sic")),
        "centro_servicio": _blank_to_none(raw.get("centro_servicio")),
        "tipo": tipo,
    }, None


def validar_filas(filas: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns `(registros_normalizados, errores)` with 1-indexed `fila`
    (same numbering as the masters upload). A repeated (cedula, placa, tipo)
    flags the later row."""
    registros: List[Dict[str, Any]] = []
    errores: List[Dict[str, Any]] = []
    vistos: set = set()
    for index, raw in enumerate(filas, start=1):
        registro, motivo = _validate_row(raw)
        if registro is not None:
            llave = (registro["cedula"], registro["placa"], registro["tipo"])
            if llave in vistos:
                registro, motivo = None, "Registro duplicado en el archivo (misma Cédula, Placa y Tipo)"
            vistos.add(llave)
        if registro is None:
            errores.append({"fila": index, "motivo": motivo})
        else:
            registros.append(registro)
    return registros, errores


def advertencias_de(registros: List[Dict[str, Any]]) -> List[str]:
    ventas = sum(1 for r in registros if r["tipo"] == TIPO_VENTA)
    if not ventas:
        return []
    return [f"{ventas} registros de Venta se guardaron pero aún no se encuestan"]
