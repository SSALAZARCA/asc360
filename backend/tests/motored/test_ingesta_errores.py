"""
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra" (sdd/motored-
pedidos-ingesta, task 3.5) — `services/ingesta/errores.py`.

Pure, DB-free tests: emisión de `carga_error` con los códigos mínimos
requeridos por spec (`SUCURSAL_NO_ENCONTRADA`, `REFERENCIA_NO_ENCONTRADA`)
y export CSV que neutraliza valores con apariencia de fórmula
(`=`, `+`, `-`, `@`) para que nunca se ejecuten al abrir en una planilla
(spec "CSV export neutralizes formula-like values").
"""
import uuid

from app.motored.models.carga_error import CargaError
from app.motored.services.ingesta import errores


def test_construir_error_builds_a_carga_error_row():
    carga_id = uuid.uuid4()

    error = errores.construir_error(
        carga_id=carga_id, fila=42, columna="sucursal", valor="CALI RARA",
        codigo_error="SUCURSAL_NO_ENCONTRADA", mensaje="No se encontró la sucursal",
    )

    assert isinstance(error, CargaError)
    assert error.carga_id == carga_id
    assert error.fila == 42
    assert error.columna == "sucursal"
    assert error.valor == "CALI RARA"
    assert error.codigo_error == "SUCURSAL_NO_ENCONTRADA"


def test_error_sucursal_no_encontrada_uses_the_minimum_required_code():
    carga_id = uuid.uuid4()

    error = errores.error_sucursal_no_encontrada(carga_id, fila=1, columna="sucursal", valor="X")

    assert error.codigo_error == errores.CODIGO_SUCURSAL_NO_ENCONTRADA
    assert error.codigo_error == "SUCURSAL_NO_ENCONTRADA"
    assert "X" in error.mensaje


def test_error_referencia_no_encontrada_uses_the_minimum_required_code():
    carga_id = uuid.uuid4()

    error = errores.error_referencia_no_encontrada(carga_id, fila=2, columna="referencia", valor="REF9")

    assert error.codigo_error == errores.CODIGO_REFERENCIA_NO_ENCONTRADA
    assert error.codigo_error == "REFERENCIA_NO_ENCONTRADA"
    assert "REF9" in error.mensaje


def test_generar_csv_errores_includes_header_and_rows():
    carga_id = uuid.uuid4()
    lista = [
        errores.error_sucursal_no_encontrada(carga_id, fila=5, columna="sucursal", valor="Y"),
    ]

    csv_text = errores.generar_csv_errores(lista)

    lineas = csv_text.strip().splitlines()
    assert lineas[0] == "fila,columna,valor,codigo_error,mensaje"
    assert "5" in lineas[1]
    assert "SUCURSAL_NO_ENCONTRADA" in lineas[1]


def test_generar_csv_errores_neutralizes_leading_equals_sign():
    import csv as csv_module
    import io

    carga_id = uuid.uuid4()
    lista = [
        errores.construir_error(
            carga_id=carga_id, fila=1, columna="valor", valor="=cmd|'/c calc'!A1",
            codigo_error="REFERENCIA_NO_ENCONTRADA", mensaje="valor sospechoso",
        )
    ]

    csv_text = errores.generar_csv_errores(lista)

    filas = list(csv_module.reader(io.StringIO(csv_text)))
    valor_neutralizado = filas[1][2]
    assert valor_neutralizado == "'=cmd|'/c calc'!A1"


def test_generar_csv_errores_neutralizes_all_four_dangerous_prefixes():
    carga_id = uuid.uuid4()
    peligrosos = ["=1+1", "+1+1", "-1+1", "@SUM(A1)"]
    lista = [
        errores.construir_error(
            carga_id=carga_id, fila=i, columna="valor", valor=v,
            codigo_error="REFERENCIA_NO_ENCONTRADA", mensaje="m",
        )
        for i, v in enumerate(peligrosos)
    ]

    csv_text = errores.generar_csv_errores(lista)

    import csv as csv_module
    import io

    filas = list(csv_module.reader(io.StringIO(csv_text)))
    valores_neutralizados = [fila[2] for fila in filas[1:]]
    for original, neutralizado in zip(peligrosos, valores_neutralizados):
        assert neutralizado.startswith("'")
        assert neutralizado[1:] == original


def test_generar_csv_errores_leaves_safe_values_untouched():
    carga_id = uuid.uuid4()
    lista = [
        errores.construir_error(
            carga_id=carga_id, fila=1, columna="valor", valor="CALI NORTE",
            codigo_error="SUCURSAL_NO_ENCONTRADA", mensaje="m",
        )
    ]

    csv_text = errores.generar_csv_errores(lista)

    assert "CALI NORTE" in csv_text
    assert "'CALI NORTE" not in csv_text
