"""
Motored Pedidos — Ingesta: parser compartido de celdas numéricas
(cantidades y valores de los 6 tipos de movimiento).

Una sola regla para todos los transforms, para que una celda vacía o con un
error de Excel nunca se convierta en un cero silencioso que pise datos
existentes:

- Celda en blanco (`None`, texto vacío) o valor de error de Excel (`#N/A`,
  `#NAME?`, `#VALUE!`, `#REF!`, `#DIV/0!`, `#NUM!`, `#NULL!`): FALTANTE
  (`CeldaFaltanteError`).
- Texto que no es un número inequívoco, `NaN`/`Infinity` o un booleano:
  INVÁLIDO (`CeldaInvalidaError`).
- Texto con formato colombiano (`.` de miles, `,` decimal, p.ej.
  `1.234,5`) se interpreta de forma determinista. Un texto ambiguo como
  `1.234` o `1,234` (podría ser mil doscientos treinta y cuatro o uno con
  234 milésimas) se rechaza: la fila queda como error y el usuario corrige
  el archivo, en vez de que el sistema adivine.

`resolver_decimal_o_error` traduce ambos casos a un `CargaError` por fila;
cada transform decide qué hacer con el resultado (hoy, todos rechazan la
fila).
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any, Optional, Tuple

from app.motored.models.carga_error import CargaError
from app.motored.services.ingesta import errores as errores_mod

CODIGO_VALOR_FALTANTE = "VALOR_FALTANTE"

_ERRORES_EXCEL = frozenset(
    {"#N/A", "#NAME?", "#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#NULL!"}
)

_PLANO = re.compile(r"^[+-]?(\d+)(?:\.(\d+))?$")
_MILES_COLOMBIANOS = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$")
_COMA_DECIMAL = re.compile(r"^[+-]?(\d+),(\d+)$")


class CeldaFaltanteError(Exception):
    """Celda en blanco o con un valor de error de Excel."""


class CeldaInvalidaError(Exception):
    """Celda con un valor que no se puede interpretar sin ambigüedad."""


def _parece_miles(parte_entera: str, parte_decimal: str) -> bool:
    """`1.234`/`1,234`: 1-3 dígitos sin cero inicial y exactamente 3
    decimales -- indistinguible de un separador de miles."""
    return len(parte_entera) <= 3 and not parte_entera.startswith("0") and len(parte_decimal) == 3


def _parsear_texto(texto: str) -> Decimal:
    plano = _PLANO.match(texto)
    if plano:
        entera, decimal = plano.group(1), plano.group(2)
        if decimal is not None and _parece_miles(entera, decimal):
            raise CeldaInvalidaError(texto)
        return Decimal(texto)
    if _MILES_COLOMBIANOS.match(texto):
        return Decimal(texto.replace(".", "").replace(",", "."))
    coma = _COMA_DECIMAL.match(texto)
    if coma and not _parece_miles(coma.group(1), coma.group(2)):
        return Decimal(texto.replace(",", "."))
    raise CeldaInvalidaError(texto)


def parsear_decimal(valor: Any) -> Decimal:
    """Retorna el `Decimal` de una celda o lanza `CeldaFaltanteError`/
    `CeldaInvalidaError` -- ver docstring del módulo."""
    if valor is None:
        raise CeldaFaltanteError()
    if isinstance(valor, bool):
        raise CeldaInvalidaError(str(valor))
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto or texto.upper() in _ERRORES_EXCEL:
            raise CeldaFaltanteError()
        return _parsear_texto(texto)
    try:
        numero = Decimal(str(valor))
    except ArithmeticError as exc:
        raise CeldaInvalidaError(str(valor)) from exc
    if not numero.is_finite():
        raise CeldaInvalidaError(str(valor))
    return numero


def _texto_o_none(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def resolver_decimal_o_error(
    valor: Any,
    columna: str,
    carga_id: uuid.UUID,
    numero_fila: int,
    codigo_invalido: str,
    mensaje_invalido: str,
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`(decimal, None)` si la celda es un número válido; `(None, error)` si
    está vacía/con error de Excel (`CODIGO_VALOR_FALTANTE`) o no es
    interpretable (`codigo_invalido`/`mensaje_invalido` del tipo). Nunca
    propaga una excepción cruda."""
    try:
        return parsear_decimal(valor), None
    except CeldaFaltanteError:
        texto = _texto_o_none(valor)
        detalle = f"vacía o con error ({texto})" if texto else "vacía"
        mensaje = (
            f"{columna} {detalle} en la fila {numero_fila}: "
            "corregí el archivo y volvé a cargarlo."
        )
        codigo = CODIGO_VALOR_FALTANTE
    except CeldaInvalidaError:
        texto = _texto_o_none(valor)
        mensaje, codigo = mensaje_invalido, codigo_invalido
    return None, errores_mod.construir_error(
        carga_id, numero_fila, columna, texto, codigo, mensaje
    )
