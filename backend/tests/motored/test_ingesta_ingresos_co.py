"""
INGRESOS_FACTURAS: the optional "C.O." column fills `sucursal_id`.

A known C.O. (normalized, case-insensitive) sets `sucursal_id` on the
staging row and on the upserted `ingreso_factura`; an unknown or empty
C.O. leaves it NULL with no row error. Files without the column still
load, and the column never becomes required.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from tests.motored.sql_upsert import upsert_set_clause

from app.motored.services.ingesta import columnas, ingresos, orquestador

CARGA_ID = uuid.uuid4()
SUCURSAL_MR = uuid.uuid4()
SUCURSAL_POR_CO = {"MR": SUCURSAL_MR}

_ENCABEZADO = ingresos.COLUMNAS_ESPERADAS + ("C.O.",)


def _mapa(encabezado=_ENCABEZADO):
    esperadas = ingresos.COLUMNAS_ESPERADAS + ingresos.ALIAS_COLUMNA_CO
    return columnas.construir_mapa_columnas(encabezado, esperadas)


def _fila(co):
    return (
        "16-00000036", date(2026, 7, 15), "Facturado", "RH193043",
        Decimal("2290580"), co,
    )


def _procesar(fila_raw, mapa=None, sucursal_por_co=SUCURSAL_POR_CO):
    return ingresos.procesar_fila(
        fila_raw, numero_fila=2, lote=1,
        mapa_columnas=_mapa() if mapa is None else mapa,
        carga_id=CARGA_ID, sucursal_por_co=sucursal_por_co,
    )


def test_el_encabezado_c_o_normalizado_mapea_la_columna():
    mapa = _mapa()

    assert ingresos.tiene_columna_co(mapa)
    assert mapa["C.O."] == 5


def test_un_co_conocido_llena_la_sucursal_sin_importar_mayusculas():
    fila_staging, errores = _procesar(_fila(" mr "))

    assert errores == []
    assert fila_staging.sucursal_id == SUCURSAL_MR
    assert fila_staging.payload["sucursal_id"] == str(SUCURSAL_MR)


def test_un_co_desconocido_deja_la_sucursal_nula_sin_error():
    fila_staging, errores = _procesar(_fila("ZZ"))

    assert errores == []
    assert fila_staging.sucursal_id is None
    assert fila_staging.payload.get("sucursal_id") is None


def test_un_co_vacio_deja_la_sucursal_nula_sin_error():
    fila_staging, errores = _procesar(_fila(None))

    assert errores == []
    assert fila_staging.sucursal_id is None


def test_un_archivo_sin_la_columna_sigue_cargando():
    encabezado = ingresos.COLUMNAS_ESPERADAS
    fila_staging, errores = _procesar(
        _fila("MR")[:5], mapa=_mapa(encabezado), sucursal_por_co=None,
    )

    assert errores == []
    assert fila_staging.sucursal_id is None


def test_la_columna_c_o_es_opcional_para_la_verificacion():
    tipo = "INGRESOS_FACTURAS"

    assert "C.O." in orquestador._columnas_opcionales(tipo)
    assert "C.O." not in orquestador._COLUMNAS_POR_TIPO[tipo]


def test_agregar_documentos_conserva_la_sucursal():
    fila_staging, _ = _procesar(_fila("MR"))

    consolidado = ingresos.agregar_documentos([fila_staging])

    assert consolidado[("RH", 193043)]["sucursal_id"] == SUCURSAL_MR


def test_el_upsert_inserta_y_actualiza_la_sucursal():
    consolidado = {
        ("RH", 193043): {
            "valor_neto": Decimal("10"), "fecha_ingreso": date(2026, 7, 15),
            "sucursal_id": SUCURSAL_MR,
        },
    }

    stmt = ingresos.construir_statement_upsert(consolidado, CARGA_ID)

    assert upsert_set_clause(stmt)["sucursal_id"] == "excluded.sucursal_id"
    parametros = stmt.compile(dialect=postgresql.dialect()).params
    assert SUCURSAL_MR in parametros.values()
