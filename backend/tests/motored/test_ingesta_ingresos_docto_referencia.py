"""
INGRESOS_FACTURAS against the real ERP export header set (owner decision,
2026-10-08).

The ERP export names the reference column "Docto. referencia" (normalized
`doctoreferencia`), not "Dct.referencia" (`dctreferencia`). Both names must
work at upload verification (`deteccion`/`api.cargas`) and at processing
(`columnas` + `orquestador`).

A reference that is not a parts invoice (`CH-74745`, `OH 1234`,
`NRH1234`, `FCI12345`) is skipped silently, like an `Anulado` row, and
counted in `carga.log["filas_no_repuestos"]`. All values are synthetic.
"""
import io
import uuid
from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from fastapi import HTTPException

from tests.motored.conftest import FakeAsyncSession

from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services import kpi_resumen
from app.motored.services.ingesta import columnas, deteccion, ingresos
from app.motored.services.ingesta import orquestador

ENCABEZADO_ERP = (
    "C.O.", "Nro documento", "Fecha", "Estado", "Clase docto.",
    "Razón social proveedor", "Docto. referencia", "Moneda ",
    "Valor bruto local", "Valor neto local",
)
CARGA_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _sin_marca_de_sucio(monkeypatch):
    async def marcar(db):
        return True

    monkeypatch.setattr(kpi_resumen, "marcar_sucio_si_construido", marcar)


def _fila_erp(referencia, estado="Facturado", numero="00000001"):
    return (
        "001", numero, date(2026, 9, 15), estado, "FCP",
        "PROVEEDOR SINTETICO SAS", referencia, "COP",
        Decimal("1000"), Decimal("900"),
    )


def _xlsx(filas):
    workbook = openpyxl.Workbook()
    hoja = workbook.active
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _mapa_erp():
    return columnas.construir_mapa_columnas(
        ENCABEZADO_ERP, ingresos.COLUMNAS_ESPERADAS
    )


def _procesar(fila):
    return ingresos.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=_mapa_erp(),
        carga_id=CARGA_ID,
    )


# -- column alias ----------------------------------------------------------


def test_docto_referencia_maps_to_dct_referencia():
    mapa = _mapa_erp()

    assert set(mapa) == set(ingresos.COLUMNAS_ESPERADAS)
    assert mapa["Dct.referencia"] == ENCABEZADO_ERP.index(
        "Docto. referencia"
    )


def test_old_dct_referencia_name_still_maps():
    encabezado = ("Nrodocumento", "Fecha", "Estado", "Dct.referencia",
                  "Valornetolocal")

    mapa = columnas.construir_mapa_columnas(
        encabezado, ingresos.COLUMNAS_ESPERADAS
    )

    assert mapa["Dct.referencia"] == 3


def test_canonical_name_wins_when_both_names_are_present():
    encabezado = ("Docto. referencia", "Nrodocumento", "Fecha", "Estado",
                  "Dct.referencia", "Valornetolocal")

    mapa = columnas.construir_mapa_columnas(
        encabezado, ingresos.COLUMNAS_ESPERADAS
    )

    assert mapa["Dct.referencia"] == 4


def test_header_row_ratio_counts_the_alias():
    ratio = columnas.mejor_ratio_de_encabezado(
        [ENCABEZADO_ERP], ingresos.COLUMNAS_ESPERADAS
    )

    assert ratio == 1.0


def test_alias_does_not_leak_into_other_types():
    mapa = columnas.construir_mapa_columnas(
        ("Docto. referencia", "Factura"), ("Factura",)
    )

    assert mapa == {"Factura": 1}


# -- upload verification ---------------------------------------------------


def test_erp_header_passes_upload_verification():
    archivo = _xlsx([ENCABEZADO_ERP, _fila_erp("RH123456")])

    cargas_api._verificar_tipo_o_400("INGRESOS_FACTURAS", archivo)


def test_wrong_tab_400_has_a_spanish_message_naming_tab_and_columns():
    archivo = _xlsx([ENCABEZADO_ERP, _fila_erp("RH123456")])

    with pytest.raises(HTTPException) as excinfo:
        cargas_api._verificar_tipo_o_400("FACTURAS_PEDIDOS", archivo)

    detail = excinfo.value.detail
    assert detail["tipo_declarado"] == "FACTURAS_PEDIDOS"
    assert detail["sin_coincidencia"] is False
    mensaje = detail["mensaje"]
    assert mensaje.startswith(
        "Este archivo no parece de Facturas de pedidos"
    )
    for columna in detail["columnas_faltantes"]:
        assert columna in mensaje
    assert "otra pestaña" in mensaje


def test_no_match_400_message_names_the_tab():
    archivo = _xlsx([("nada", "que", "ver"), (1, 2, 3)])

    with pytest.raises(HTTPException) as excinfo:
        cargas_api._verificar_tipo_o_400("INGRESOS_FACTURAS", archivo)

    detail = excinfo.value.detail
    assert detail["sin_coincidencia"] is True
    assert "Ingresos de facturas" in detail["mensaje"]
    assert "otra pestaña" in detail["mensaje"]


# -- row processing --------------------------------------------------------


def test_rh_reference_is_still_processed():
    fila_staging, errores = _procesar(_fila_erp("RH123456"))

    assert errores == []
    assert fila_staging.payload["prefijo_rh"] == "RH"
    assert fila_staging.payload["numero_rh"] == 123456


@pytest.mark.parametrize(
    "referencia", ["CH-74745", "OH 1234", "NRH1234", "FCI12345", " ch-1 "]
)
def test_non_parts_reference_is_skipped_without_error(referencia):
    resultado = _procesar(_fila_erp(referencia))

    assert resultado is ingresos.MarcaIngreso.NO_ES_REPUESTO


@pytest.mark.parametrize("estado", ["Anulado", "ANULADO", " anulado "])
def test_anulado_is_skipped_in_any_case(estado):
    fila_staging, errores = _procesar(_fila_erp("RH123456", estado=estado))

    assert fila_staging is None
    assert errores == []


def test_anulado_non_parts_row_is_skipped_as_anulado():
    fila_staging, errores = _procesar(
        _fila_erp("CH-74745", estado="Anulado")
    )

    assert fila_staging is None
    assert errores == []


# -- end to end through the dry run -----------------------------------------


def _carga():
    return CargaArchivo(
        id=uuid.uuid4(), tipo="INGRESOS_FACTURAS",
        nombre_archivo="ingresos.xlsx", hash_sha256="a" * 64,
        ruta_objeto="INGRESOS_FACTURAS/2026/10/x.xlsx", bytes=100,
        estado="PROCESANDO", filas_leidas=0, filas_validas=0,
        filas_rechazadas=0, periodo_desde=None, periodo_hasta=None,
        lotes_staged=0, ultimo_lote_aplicado=0, latido_en=None, log=None,
        subido_por=uuid.uuid4(), aplicado_en=None,
    )


async def test_dry_run_counts_non_parts_rows_and_stages_rh(monkeypatch):
    archivo = _xlsx([
        ENCABEZADO_ERP,
        _fila_erp("RH100001", numero="00000001"),
        _fila_erp("CH-74745", numero="00000002"),
        _fila_erp("OH 1234", numero="00000003"),
        _fila_erp("NRH1234", numero="00000004"),
        _fila_erp("FCI12345", numero="00000005"),
        _fila_erp("RH100002", estado="ANULADO", numero="00000006"),
        _fila_erp("RH100003", estado="Contabilizado", numero="00000007"),
    ])
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: archivo
    )
    carga = _carga()
    # The last read is the C.O. -> sucursal map: the ERP header brings
    # the optional C.O. column.
    session = FakeAsyncSession(
        execute_queue=[[], [], [], [], [uuid.uuid4()], []]
    )

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"
    assert carga.filas_leidas == 7
    assert carga.filas_validas == 2
    assert carga.filas_rechazadas == 0
    assert carga.log["filas_no_repuestos"] == 4
    assert carga.log["filas_con_error"] == 0
    staged = session.added_of_type(CargaFilaStaging)
    assert sorted(f.payload["numero_rh"] for f in staged) == [
        100001, 100003,
    ]
