"""
Motored budgets -- pure parsing, validation and dry-run summary of the budget
upload (odd/motored-presupuestos-gerencia, T2). No database access: the
lookups arrive as a `Catalogos` value (built by `services/presupuestos.py`),
so every rule is testable directly.

Row numbers (`fila`) are the position among the DATA rows, starting at 1 (the
header is not counted), same convention as the other Motored uploads.
"""
import datetime
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from app.motored.schemas.presupuesto import MONTO_MAXIMO
from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services.ingesta.resolucion import normalizar_texto_sucursal

_MES_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_MES_ISO_DIA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_MES_LATINO_RE = re.compile(r"^(\d{1,2})/(\d{4})$")
_MONTO_MILES_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_MONTO_ENTERO_RE = re.compile(r"^(\d+)(?:\.0+)?$")
_ANIO_RE = re.compile(r"^[1-9]\d{3}$")
_MSG_ANIO = "El año debe tener 4 dígitos (ej. 2026)"
_MSG_MES_NUM = "El mes debe ser un número de 1 a 12"
_MSG_DOS_FORMATOS = (
    "Con la columna Año, el Mes debe ser un número de 1 a 12 (ej. Año "
    "2026, Mes 7). Para usar una sola columna Mes con '2026-07', quite "
    "la columna Año"
)


def parse_mes(valor: Any) -> datetime.date:
    """Excel date cell, `YYYY-MM` or `MM/YYYY` -> first day of that month."""
    if isinstance(valor, datetime.datetime):
        return valor.date().replace(day=1)
    if isinstance(valor, datetime.date):
        return valor.replace(day=1)
    texto = "" if valor is None else str(valor).strip()
    try:
        if _MES_ISO_DIA_RE.match(texto):  # a date cell that arrived as text
            return datetime.date.fromisoformat(texto[:10]).replace(day=1)
        for patron, orden in ((_MES_ISO_RE, (1, 2)), (_MES_LATINO_RE, (2, 1))):
            encontrado = patron.match(texto)
            if encontrado:
                return datetime.date(int(encontrado.group(orden[0])), int(encontrado.group(orden[1])), 1)
    except ValueError:
        pass
    raise ValueError("El mes debe ser una fecha, 'AAAA-MM' o 'MM/AAAA'")


def _entero_texto(valor: Any) -> str:
    """Number or numeric text ('10', '10.0' from an Excel float) -> digits;
    anything else -> ''."""
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else ""
    texto = "" if valor is None else str(valor).strip()
    encontrado = _MONTO_ENTERO_RE.match(texto)
    return encontrado.group(1) if encontrado else ""


def parse_anio(valor: Any) -> int:
    """Year column: exactly 4 digits."""
    digitos = _entero_texto(valor)
    if not _ANIO_RE.match(digitos):
        raise ValueError(_MSG_ANIO)
    return int(digitos)


def _parece_mes_completo(valor: Any) -> bool:
    if isinstance(valor, datetime.date):  # datetime is a date subclass
        return True
    texto = "" if valor is None else str(valor).strip()
    return any(p.match(texto) for p in (
        _MES_ISO_RE, _MES_ISO_DIA_RE, _MES_LATINO_RE))


def parse_mes_numero(valor: Any) -> int:
    """Month column of the two-column layout: 1 to 12."""
    digitos = _entero_texto(valor)
    if digitos and 1 <= int(digitos) <= 12:
        return int(digitos)
    if _parece_mes_completo(valor):
        raise ValueError(_MSG_DOS_FORMATOS)
    raise ValueError(_MSG_MES_NUM)


class ErrorMesFila(ValueError):
    """A month error that names the offending column."""

    def __init__(self, columna: str, mensaje: str):
        super().__init__(mensaje)
        self.columna = columna


def mes_de_fila(fila: Mapping[str, Any]) -> datetime.date:
    """First day of the row's month. Layout by header: a canonical row with
    the `anio` key came from a file WITH an "Año" column (two columns);
    otherwise `mes` holds a date, 'AAAA-MM' or 'MM/AAAA'."""
    if "anio" not in fila:
        return parse_mes(fila.get("mes"))
    try:
        anio = parse_anio(fila.get("anio"))
    except ValueError as exc:
        raise ErrorMesFila("Año", str(exc)) from exc
    try:
        mes = parse_mes_numero(fila.get("mes"))
    except ValueError as exc:
        raise ErrorMesFila("Mes", str(exc)) from exc
    return datetime.date(anio, mes, 1)


def parse_monto(valor: Any) -> int:
    """Integer pesos > 0: a number, digits, or digits with thousands separators."""
    mensaje = "El presupuesto debe ser un número entero de pesos mayor a 0"
    if isinstance(valor, float):
        if not valor.is_integer():
            raise ValueError(mensaje)
        monto = int(valor)
    elif isinstance(valor, int) and not isinstance(valor, bool):
        monto = valor
    else:
        texto = "" if valor is None else str(valor).strip()
        if _MONTO_MILES_RE.match(texto):
            monto = int(re.sub(r"[.,]", "", texto))
        else:
            encontrado = _MONTO_ENTERO_RE.match(texto)
            if not encontrado:
                raise ValueError(mensaje)
            monto = int(encontrado.group(1))
    if monto <= 0:
        raise ValueError(mensaje)
    if monto > MONTO_MAXIMO:
        raise ValueError(f"El presupuesto no puede superar {MONTO_MAXIMO:,}".replace(",", ".") + " pesos")
    return monto


@dataclass(frozen=True)
class Catalogos:
    """What validation needs to know about the database."""
    cedula_activa: Mapping[str, bool]  # cedula -> True if any ACTIVE vendedor has it
    sucursal_por_texto: Mapping[str, uuid.UUID]  # normalized name/alias -> sucursal id
    sucursal_activa: Mapping[uuid.UUID, bool]
    sucursal_nombre: Mapping[uuid.UUID, str]
    version_actual: Mapping[datetime.date, int] = field(default_factory=dict)  # mes -> latest version


@dataclass(frozen=True)
class LineaValida:
    fila: int
    mes: datetime.date
    cedula: str
    sucursal_id: uuid.UUID
    monto: int


@dataclass
class Validacion:
    filas: int = 0
    lineas: List[LineaValida] = field(default_factory=list)
    errores: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


def _incidencia(fila: int, columna: str, mensaje: str) -> Dict[str, Any]:
    return {"fila": fila, "columna": columna, "mensaje": mensaje}


def _validar_cedula(fila: int, crudo: Any, catalogos: Catalogos, resultado: Validacion) -> Optional[str]:
    try:
        cedula = limpiar_cedula(crudo)
    except ValueError as exc:
        resultado.errores.append(_incidencia(fila, "Cédula", str(exc)))
        return None
    if cedula not in catalogos.cedula_activa:
        resultado.errores.append(
            _incidencia(fila, "Cédula", f"La cédula {cedula} no corresponde a ningún vendedor"))
        return None
    if not catalogos.cedula_activa[cedula]:
        resultado.warnings.append(
            _incidencia(fila, "Cédula", f"La cédula {cedula} corresponde a un vendedor inactivo"))
    return cedula


def _validar_tienda(fila: int, crudo: Any, catalogos: Catalogos, resultado: Validacion) -> Optional[uuid.UUID]:
    texto = "" if crudo is None else str(crudo).strip()
    if not texto:
        resultado.errores.append(_incidencia(fila, "Tienda", "La tienda es obligatoria"))
        return None
    sucursal_id = catalogos.sucursal_por_texto.get(normalizar_texto_sucursal(texto))
    if sucursal_id is None:
        resultado.errores.append(_incidencia(fila, "Tienda", f"La tienda '{texto}' no existe"))
        return None
    if not catalogos.sucursal_activa.get(sucursal_id, False):
        resultado.errores.append(_incidencia(fila, "Tienda", f"La tienda '{texto}' está inactiva"))
        return None
    return sucursal_id


def _valor_o_error(analizar, fila: int, columna: str, crudo: Any, resultado: Validacion):
    try:
        return analizar(crudo)
    except ValueError as exc:
        columna = getattr(exc, "columna", columna)
        resultado.errores.append(_incidencia(fila, columna, str(exc)))
        return None


def validar_filas(filas: List[Dict[str, Any]], catalogos: Catalogos) -> Validacion:
    """Validates canonical rows (`cedula`, `mes`, `tienda`, `presupuesto`).
    Valid rows come back as `lineas`; a cedula repeated in the same month errors
    ALL its rows (the user must keep one) and none of them becomes a line."""
    resultado = Validacion(filas=len(filas))
    candidatas: List[LineaValida] = []
    for numero, fila in enumerate(filas, start=1):
        cedula = _validar_cedula(numero, fila.get("cedula"), catalogos, resultado)
        mes = _valor_o_error(mes_de_fila, numero, "Mes", fila, resultado)
        sucursal_id = _validar_tienda(numero, fila.get("tienda"), catalogos, resultado)
        monto = _valor_o_error(parse_monto, numero, "Presupuesto", fila.get("presupuesto"), resultado)
        if None not in (cedula, mes, sucursal_id, monto):
            candidatas.append(LineaValida(numero, mes, cedula, sucursal_id, monto))

    filas_por_clave: Dict[tuple, List[int]] = {}
    for linea in candidatas:
        filas_por_clave.setdefault((linea.mes, linea.cedula), []).append(linea.fila)
    repetidas = {clave for clave, numeros in filas_por_clave.items() if len(numeros) > 1}
    for mes, cedula in sorted(repetidas):
        for numero in filas_por_clave[(mes, cedula)]:
            resultado.errores.append(_incidencia(
                numero, "Cédula", f"Cédula {cedula} repetida en el mes {mes:%Y-%m}"))
    resultado.lineas = [c for c in candidatas if (c.mes, c.cedula) not in repetidas]
    resultado.errores.sort(key=lambda e: e["fila"])
    return resultado


def resumir(resultado: Validacion, catalogos: Catalogos) -> Dict[str, Any]:
    """Dry-run summary: per month asesores/total/total per store and the
    version it would replace, plus the global errors and warnings."""
    por_mes: Dict[datetime.date, List[LineaValida]] = {}
    for linea in resultado.lineas:
        por_mes.setdefault(linea.mes, []).append(linea)

    meses = []
    for mes in sorted(por_mes):
        por_tienda: Dict[uuid.UUID, List[int]] = {}
        for linea in por_mes[mes]:
            por_tienda.setdefault(linea.sucursal_id, []).append(linea.monto)
        meses.append({
            "mes": f"{mes:%Y-%m}",
            "asesores": len(por_mes[mes]),
            "total": sum(linea.monto for linea in por_mes[mes]),
            "reemplaza_version": catalogos.version_actual.get(mes),
            "por_tienda": sorted(
                (
                    {
                        "sucursal_id": str(sucursal_id),
                        "tienda": catalogos.sucursal_nombre.get(sucursal_id, ""),
                        "asesores": len(montos),
                        "total": sum(montos),
                    }
                    for sucursal_id, montos in por_tienda.items()
                ),
                key=lambda t: t["tienda"],
            ),
        })
    return {
        "valido": not resultado.errores,
        "filas": resultado.filas,
        "meses": meses,
        "errores": resultado.errores,
        "warnings": resultado.warnings,
    }
