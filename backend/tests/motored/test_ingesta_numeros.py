"""
Shared numeric-cell parser (`services/ingesta/numeros.py`) used by every
movement transform for quantity/value cells. Blank cells and Excel error
values are "missing"; unparseable, ambiguous, NaN and Infinity values are
"invalid". Each transform then turns both into a `carga_error` row.
"""
import uuid
from decimal import Decimal

import pytest

from app.motored.services.ingesta import numeros

CARGA_ID = uuid.uuid4()


@pytest.mark.parametrize(
    "valor",
    [10, 0, -3, 2.5, Decimal("7.25"), "12", "  12 ", "12.5", "-4", "0.123"],
)
def test_parsea_valores_numericos_sin_ambiguedad(valor):
    assert numeros.parsear_decimal(valor) == Decimal(str(valor).strip())


def test_cero_real_es_valido_y_sigue_siendo_cero():
    assert numeros.parsear_decimal(0) == Decimal("0")
    assert numeros.parsear_decimal("0") == Decimal("0")


@pytest.mark.parametrize(
    "valor",
    [None, "", "   ", "#N/A", "#NAME?", "#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#NULL!", " #n/a "],
)
def test_vacio_o_error_de_excel_es_faltante(valor):
    with pytest.raises(numeros.CeldaFaltanteError):
        numeros.parsear_decimal(valor)


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("1.234,5", Decimal("1234.5")),
        ("12.345.678", Decimal("12345678")),
        ("1.234.567,89", Decimal("1234567.89")),
        ("1,5", Decimal("1.5")),
        ("-2,25", Decimal("-2.25")),
        ("1234.567", Decimal("1234.567")),
    ],
)
def test_texto_con_formato_colombiano_se_parsea_de_forma_determinista(texto, esperado):
    assert numeros.parsear_decimal(texto) == esperado


@pytest.mark.parametrize(
    "valor",
    [
        "abc", "1.234", "1,234", "1,234,567", "1.2.3", "12,3,4", "1e5", "--1", True,
        float("nan"), float("inf"), "NaN", "Infinity", "-Infinity",
    ],
)
def test_ambiguo_no_numerico_nan_o_infinito_es_invalido(valor):
    with pytest.raises(numeros.CeldaInvalidaError):
        numeros.parsear_decimal(valor)


def test_resolver_devuelve_el_decimal_sin_error():
    valor, error = numeros.resolver_decimal_o_error(
        5, "Existencia", CARGA_ID, 7, "EXISTENCIA_INVALIDA", "no numérica"
    )
    assert valor == Decimal("5") and error is None


def test_resolver_faltante_emite_error_valor_faltante_con_columna_valor_y_mensaje():
    valor, error = numeros.resolver_decimal_o_error(
        "#N/A", "Existencia", CARGA_ID, 7, "EXISTENCIA_INVALIDA", "no numérica"
    )
    assert valor is None
    assert error.codigo_error == numeros.CODIGO_VALOR_FALTANTE
    assert error.fila == 7 and error.columna == "Existencia" and error.valor == "#N/A"
    assert "Existencia" in error.mensaje and "fila 7" in error.mensaje
    assert "#N/A" in error.mensaje and "corregí el archivo" in error.mensaje


def test_resolver_celda_en_blanco_emite_error_con_valor_none():
    valor, error = numeros.resolver_decimal_o_error(
        None, "Cantidad", CARGA_ID, 3, "CANTIDAD_INVALIDA", "no numérica"
    )
    assert valor is None
    assert error.codigo_error == numeros.CODIGO_VALOR_FALTANTE
    assert error.valor is None and "vacía" in error.mensaje


def test_resolver_invalido_emite_el_codigo_y_mensaje_del_tipo():
    valor, error = numeros.resolver_decimal_o_error(
        "abc", "Cantidad", CARGA_ID, 3, "CANTIDAD_INVALIDA", "no numérica"
    )
    assert valor is None
    assert error.codigo_error == "CANTIDAD_INVALIDA"
    assert error.valor == "abc" and error.mensaje == "no numérica"
