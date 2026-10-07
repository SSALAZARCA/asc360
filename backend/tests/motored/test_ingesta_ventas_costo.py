"""
VENTAS optional column "Costo promedio total": the ERP cost of the sale
line (line total) stored on `venta_detalle.costo`. Absent / blank /
unparsable -> NULL (never a `carga_error`); the value is stored as-is
(negatives kept); "Costo prom. uni." is ignored. A file without the column
(the old 13-column files) stages exactly the same payload and log as before.
"""
import uuid
from decimal import Decimal

import pytest

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services.ingesta import deteccion, plantillas, ventas
from tests.motored.test_ingesta_ventas_co import (
    SUCURSAL_BODEGA,
    _MAPA_SIN_CO,
    _dry_run,
    _fila,
)
from tests.motored.test_ingesta_ventas_co import _procesar as _procesar_base

COLUMNA = "Costo promedio total"
_MAPA_CON_COSTO = {**_MAPA_SIN_CO, COLUMNA: len(ventas.COLUMNAS_ESPERADAS)}


def _fila_costo(costo, **kwargs):
    return _fila(**kwargs)[:-1] + (costo,)


def _procesar(costo, mapa=_MAPA_CON_COSTO, **kwargs):
    return _procesar_base(
        _fila_costo(costo, **kwargs), mapa=mapa, por_co=None)


# --- columns / plantilla -----------------------------------------------------


def test_costo_es_columna_opcional_de_ventas_y_va_a_la_plantilla():
    assert deteccion.COLUMNAS_OPCIONALES_POR_TIPO["VENTAS"] == (COLUMNA,)
    assert COLUMNA not in ventas.COLUMNAS_ESPERADAS
    assert plantillas.columnas_plantilla("VENTAS")[-1] == COLUMNA


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize("crudo, esperado", [
    (14697.5, "14697.5"),
    ("14.697,50", "14697.50"),
    ("14697.5", "14697.5"),
    ("$14.697,50", "14697.50"),
    (0, "0"),
    ("0", "0"),
    (-5000, "-5000"),
    ("-$1.234.567,25", "-1234567.25"),
    (1234567, "1234567"),
])
def test_costo_valido_se_guarda_tal_cual(crudo, esperado):
    staging, errores = _procesar(crudo)

    assert errores == []
    assert Decimal(staging.payload[ventas.CLAVE_COSTO]) == Decimal(esperado)
    assert ventas.tiene_costo_invalido(staging) is False


@pytest.mark.parametrize("crudo", [None, "", "   "])
def test_costo_vacio_queda_en_null_sin_error_ni_conteo(crudo):
    staging, errores = _procesar(crudo)

    assert errores == []
    assert ventas.CLAVE_COSTO not in staging.payload
    assert ventas.tiene_costo_invalido(staging) is False


@pytest.mark.parametrize("crudo", ["abc", "1.234", True, 10 ** 15, "#N/A"])
def test_costo_no_interpretable_queda_en_null_sin_rechazar_la_fila(crudo):
    staging, errores = _procesar(crudo)

    assert errores == []
    assert staging is not None
    assert ventas.CLAVE_COSTO not in staging.payload
    assert ventas.tiene_costo_invalido(staging) is True


def test_archivo_viejo_sin_la_columna_stagea_el_mismo_payload_de_antes():
    fila = _fila(co=None)[:-1]

    staging, errores = _procesar_base(
        fila, mapa=_MAPA_SIN_CO, por_co=None)

    assert errores == []
    assert ventas.CLAVE_COSTO not in staging.payload
    assert ventas.CLAVE_COSTO_INVALIDO not in staging.payload
    assert set(staging.payload) == {
        "anio", "mes", "dia", "origen", "cantidad", "vendedor",
        "valor_bruto", "valor_descuentos", "cliente_factura",
        "nro_documento", "linea_clase"}


def test_costo_unitario_se_ignora():
    mapa = {**_MAPA_SIN_CO, "Costo prom. uni.": 13}
    staging, errores = _procesar_base(
        _fila(co=None)[:-1] + (999,), mapa=mapa, por_co=None)

    assert errores == []
    assert ventas.CLAVE_COSTO not in staging.payload


def test_fila_solo_detalle_tambien_lleva_el_costo():
    staging, errores = _procesar_base(
        _fila_costo("14.697,50", tipo="MOTOCICLETA"), mapa=_MAPA_CON_COSTO,
        por_co=None, linea="MOTOCICLETA")

    assert errores == []
    assert staging is not None and ventas.es_solo_detalle(staging)
    assert Decimal(staging.payload[ventas.CLAVE_COSTO]) == Decimal("14697.50")


# --- apply statements ----------------------------------------------------------


def _staging(payload_extra):
    payload = {
        "anio": 2026, "mes": 9, "dia": 15, "origen": "MOSTRADOR",
        "cantidad": "5", "vendedor": "Ana", "valor_bruto": "1000",
        "valor_descuentos": "0", "cliente_factura": "T",
        "nro_documento": "FV-1", **payload_extra}
    return CargaFilaStaging(
        id=uuid.uuid4(), carga_id=uuid.uuid4(), lote=1, fila=2,
        sucursal_id=uuid.uuid4(), referencia_id=uuid.uuid4(),
        payload=payload)


def test_construir_detalle_lleva_el_costo_o_null():
    con = _staging({ventas.CLAVE_COSTO: "-14697.50"})
    sin = _staging({})

    detalle = ventas.construir_detalle([con, sin], uuid.uuid4())

    assert detalle[0]["costo"] == Decimal("-14697.50")
    assert detalle[1]["costo"] is None


def test_modelo_tiene_la_columna_costo_nullable():
    columna = VentaDetalle.__table__.c.costo
    assert columna.nullable is True
    assert columna.type.precision == 18 and columna.type.scale == 2


# --- orchestrator log -----------------------------------------------------------


_ENCABEZADO = ventas.COLUMNAS_ESPERADAS + (COLUMNA,)


async def test_dry_run_cuenta_los_costos_invalidos_en_el_log(monkeypatch):
    filas = [
        _fila_costo("14.697,50", co=None, doc="FV-1"),
        _fila_costo("basura", co=None, doc="FV-2"),
        _fila_costo(None, co=None, doc="FV-3"),
        _fila_costo("1.234", co=None, doc="FV-4"),
    ]

    carga, session = await _dry_run(monkeypatch, _ENCABEZADO, filas, [])

    assert carga.estado == "VALIDADO"
    assert carga.log["filas_costo_invalido"] == 2
    assert carga.log["filas_con_error"] == 0
    por_doc = {f.payload["nro_documento"]: f.payload
               for f in session.added_of_type(CargaFilaStaging)}
    assert por_doc["FV-1"][ventas.CLAVE_COSTO] == "14697.50"
    assert ventas.CLAVE_COSTO not in por_doc["FV-2"]
    assert ventas.CLAVE_COSTO not in por_doc["FV-3"]


async def test_dry_run_de_un_archivo_viejo_deja_el_mismo_log_y_filas(
        monkeypatch):
    filas = [_fila(co=None, doc="FV-1")[:-1]]

    carga, session = await _dry_run(
        monkeypatch, ventas.COLUMNAS_ESPERADAS, filas, [])

    assert carga.estado == "VALIDADO"
    assert "filas_costo_invalido" not in carga.log
    (fila,) = session.added_of_type(CargaFilaStaging)
    assert fila.sucursal_id == SUCURSAL_BODEGA
    assert ventas.CLAVE_COSTO not in fila.payload


# --- migration -------------------------------------------------------------------


def test_la_migracion_agrega_costo_nullable_sobre_codigo_co():
    import importlib.util
    from pathlib import Path

    ruta = (Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
            / "d2b7a94e5c61_venta_detalle_costo.py")
    spec = importlib.util.spec_from_file_location("mig_costo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    assert modulo.revision == "d2b7a94e5c61"
    assert modulo.down_revision == "c6e1f8a2d953"
