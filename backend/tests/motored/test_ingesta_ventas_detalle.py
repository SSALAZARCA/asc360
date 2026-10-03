"""
VENTAS per-line detail (`venta_detalle`): the five required columns
("Nombre vendedor", "Valor bruto", "Valor descuentos", "Cliente factura",
"Nro documento"),
their row-level parsing, the staging payload, header detection and the
apply-time detail statements. `venta_mensual` behaviour is covered by
`test_ingesta_ventas.py` and must not change.
"""
import io
import uuid
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from tests.motored.conftest import FakeAsyncSession
from tests.motored.test_ingesta_orquestador import (
    _build_xlsx_bytes,
    _carga,
    _queue_cache_y_proveedor,
)

from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import deteccion, orquestador, plantillas, ventas
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

NUEVAS = ("Nombre vendedor", "Valor bruto", "Valor descuentos", "Cliente factura",
          "Nro documento")
VIEJAS = ("Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
          "Desc.bodega", "Bodega", "Referencia")
_MAPA = {nombre: idx for idx, nombre in enumerate(ventas.COLUMNAS_ESPERADAS)}
_SERIAL_2026_09_15 = 46280


def _cache():
    return CacheResolucion(
        sucursal_por_texto={"CALI NORTE": SUCURSAL_ID},
        referencia_por_codigo={"REF1": (REFERENCIA_ID, PROVEEDOR_ID)},
    )


def _fila(vendedor="Ana  Pérez", bruto=1000, descuentos=100, cliente="Taller El Rayo",
          nro_doc="FV-1001"):
    return ("Aprobada", "MOSTRADOR", _SERIAL_2026_09_15, 10, "REPUESTOS",
            "CALI NORTE", "BA061", "REF1", vendedor, bruto, descuentos, cliente, nro_doc)


def _procesar(fila_raw):
    return ventas.procesar_fila(
        fila_raw, numero_fila=2, lote=1, mapa_columnas=_MAPA, cache=_cache(),
        carga_id=CARGA_ID, proveedor_id=PROVEEDOR_ID,
        tipos_inventario_incluidos=["REPUESTOS"],
    )


# --- columns -----------------------------------------------------------------


def test_columnas_esperadas_incluye_las_cinco_nuevas_al_final():
    assert ventas.COLUMNAS_ESPERADAS == VIEJAS + NUEVAS


# --- payload -----------------------------------------------------------------


def test_payload_lleva_los_cinco_campos_nuevos_sin_tocar_los_existentes():
    staging, errores = _procesar(_fila())

    assert errores == []
    p = staging.payload
    assert (p["anio"], p["mes"], p["dia"], p["origen"], p["cantidad"]) == (
        2026, 9, 15, "MOSTRADOR", "10")
    assert p["vendedor"] == "Ana Pérez"
    assert Decimal(p["valor_bruto"]) == Decimal("1000")
    assert Decimal(p["valor_descuentos"]) == Decimal("100")
    assert p["cliente_factura"] == "Taller El Rayo"
    assert p["nro_documento"] == "FV-1001"


# --- money parsing -----------------------------------------------------------


@pytest.mark.parametrize("crudo, esperado", [
    ("$1.234.567", "1234567"),
    ("1.234.567,50", "1234567.50"),
    ("1234567", "1234567"),
    (1234567, "1234567"),
    (1234567.5, "1234567.5"),
    ("-$1.000.000", "-1000000"),
    (-250000, "-250000"),
    (" $ 2.500 .000 ", "2500000"),
])
def test_valor_bruto_acepta_formatos_colombianos(crudo, esperado):
    staging, errores = _procesar(_fila(bruto=crudo))

    assert errores == []
    assert Decimal(staging.payload["valor_bruto"]) == Decimal(esperado)


@pytest.mark.parametrize("crudo", [None, "", "   ", "#N/A"])
def test_valor_bruto_vacio_rechaza_la_fila(crudo):
    staging, errores = _procesar(_fila(bruto=crudo))

    assert staging is None
    assert [e.columna for e in errores] == ["Valor bruto"]
    assert "Valor bruto" in errores[0].mensaje


@pytest.mark.parametrize("crudo", ["abc", "1.234", True, 10 ** 15])
def test_valor_bruto_invalido_rechaza_la_fila(crudo):
    staging, errores = _procesar(_fila(bruto=crudo))

    assert staging is None
    assert errores[0].columna == "Valor bruto"
    assert errores[0].codigo_error == ventas.CODIGO_VALOR_BRUTO_INVALIDO


@pytest.mark.parametrize("crudo", [None, "", "  "])
def test_descuentos_vacio_cuenta_como_cero(crudo):
    staging, errores = _procesar(_fila(descuentos=crudo))

    assert errores == []
    assert Decimal(staging.payload["valor_descuentos"]) == Decimal("0")


def test_descuentos_no_numerico_rechaza_la_fila():
    staging, errores = _procesar(_fila(descuentos="mucho"))

    assert staging is None
    assert errores[0].columna == "Valor descuentos"
    assert errores[0].codigo_error == ventas.CODIGO_DESCUENTO_INVALIDO


def test_valor_bruto_y_descuentos_negativos_se_conservan_para_notas_credito():
    staging, errores = _procesar(_fila(bruto=-500, descuentos=-50))

    assert errores == []
    assert Decimal(staging.payload["valor_bruto"]) == Decimal("-500")
    assert Decimal(staging.payload["valor_descuentos"]) == Decimal("-50")


# --- text columns ------------------------------------------------------------


@pytest.mark.parametrize("vendedor", [None, "", "   "])
def test_vendedor_vacio_rechaza_la_fila(vendedor):
    staging, errores = _procesar(_fila(vendedor=vendedor))

    assert staging is None
    assert errores[0].columna == "Nombre vendedor"
    assert errores[0].codigo_error == ventas.CODIGO_VENDEDOR_FALTANTE


@pytest.mark.parametrize("cliente", [None, "", "   "])
def test_cliente_vacio_rechaza_la_fila(cliente):
    staging, errores = _procesar(_fila(cliente=cliente))

    assert staging is None
    assert errores[0].columna == "Cliente factura"
    assert errores[0].codigo_error == ventas.CODIGO_CLIENTE_FALTANTE


@pytest.mark.parametrize("nro", [None, "", "   "])
def test_nro_documento_vacio_rechaza_la_fila(nro):
    staging, errores = _procesar(_fila(nro_doc=nro))

    assert staging is None
    assert errores[0].columna == "Nro documento"
    assert errores[0].codigo_error == ventas.CODIGO_NRO_DOCUMENTO_FALTANTE


def test_nro_documento_numerico_de_excel_se_guarda_como_texto_sin_decimales():
    staging, errores = _procesar(_fila(nro_doc=10234.0))

    assert errores == []
    assert staging.payload["nro_documento"] == "10234"


def test_nro_documento_se_recorta():
    staging, _ = _procesar(_fila(nro_doc="  FV-77  "))

    assert staging.payload["nro_documento"] == "FV-77"


@pytest.mark.parametrize("campo, columna, largo", [
    ("vendedor", "Nombre vendedor", 256), ("cliente", "Cliente factura", 256),
    ("nro_doc", "Nro documento", 51),
])
def test_texto_demasiado_largo_rechaza_la_fila(campo, columna, largo):
    staging, errores = _procesar(_fila(**{campo: "x" * largo}))

    assert staging is None
    assert errores[0].columna == columna
    assert errores[0].codigo_error == ventas.CODIGO_TEXTO_DEMASIADO_LARGO


def test_fila_filtrada_por_negocio_no_exige_los_campos_nuevos():
    fila = list(_fila(vendedor=None, cliente=None, nro_doc=None))
    fila[0] = "Pendiente"

    assert _procesar(tuple(fila)) == (None, [])


def test_normalizar_vendedor_quita_tildes_mayusculas_y_espacios():
    assert ventas.normalizar_vendedor("  José   Núñez ") == "JOSE NUNEZ"


# --- detection / required check ---------------------------------------------


def _hoja_vieja_con_fila():
    return [list(VIEJAS),
            ["Aprobada", "MOSTRADOR", _SERIAL_2026_09_15, 10, "REPUESTOS",
             "CALI NORTE", "BA061", "REF1"]]


def test_archivo_viejo_de_8_columnas_se_detecta_como_ventas():
    deteccion.verificar_tipo("VENTAS", [list(VIEJAS)])  # must not raise (8/13 ~ 0.615 >= 0.6)


def test_encabezado_de_7_de_13_falla_como_tipo_no_coincide_con_mensaje_claro():
    with pytest.raises(deteccion.TipoNoCoincideError) as exc:
        deteccion.verificar_tipo("VENTAS", [list(VIEJAS[:7])])  # 7/13 ~ 0.54 < 0.6

    assert exc.value.sin_coincidencia is False
    assert exc.value.columnas_faltantes == ["Referencia", *NUEVAS]
    assert str(exc.value) == (
        "El archivo no coincide con el tipo declarado (VENTAS). "
        "Faltan columnas: Referencia, Nombre vendedor, Valor bruto, "
        "Valor descuentos, Cliente factura, Nro documento."
    )


async def test_archivo_viejo_se_rechaza_listando_las_cinco_columnas(monkeypatch):
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    contenido = _build_xlsx_bytes(_hoja_vieja_con_fila())
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    session = FakeAsyncSession(execute_queue=_queue_cache_y_proveedor() + [[]])

    await orquestador._dry_run(session, carga)

    assert carga.estado == "CON_ERRORES"
    assert carga.log["columnas_faltantes"] == list(NUEVAS)
    mensajes = [a.mensaje for a in session.added if hasattr(a, "mensaje")]
    assert mensajes == [
        "Faltan columnas obligatorias: Nombre vendedor, Valor bruto, "
        "Valor descuentos, Cliente factura, Nro documento."
    ]


async def test_archivo_completo_de_13_columnas_pasa(monkeypatch):
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    contenido = _build_xlsx_bytes([list(ventas.COLUMNAS_ESPERADAS), list(_fila())])
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    session = FakeAsyncSession(execute_queue=_queue_cache_y_proveedor() + [[]])

    await orquestador._dry_run(session, carga)

    assert carga.estado == "VALIDADO"
    assert "columnas_faltantes" not in (carga.log or {})


# --- template ----------------------------------------------------------------


def test_plantilla_ventas_trae_las_cinco_columnas_nuevas():
    workbook = openpyxl.load_workbook(io.BytesIO(plantillas.generar_plantilla_xlsx("VENTAS")))
    encabezado = [c.value for c in next(workbook.active.iter_rows())]

    for nombre in NUEVAS:
        assert nombre in encabezado
    assert encabezado[: len(VIEJAS)] == list(VIEJAS)


# --- detail rows -------------------------------------------------------------


def _staging(fila=1, sucursal=SUCURSAL_ID, referencia=REFERENCIA_ID, anio=2026, mes=9,
             dia=15, extra=True, vendedor="Ana Pérez", nro_doc="FV-1001"):
    payload = {"anio": anio, "mes": mes, "dia": dia, "origen": "MOSTRADOR", "cantidad": "10"}
    if extra:
        payload.update(vendedor=vendedor, valor_bruto="1000", valor_descuentos="100",
                       cliente_factura="Taller", nro_documento=nro_doc)
    return CargaFilaStaging(carga_id=CARGA_ID, fila=fila, lote=1, payload=payload,
                            sucursal_id=sucursal, referencia_id=referencia)


def test_construir_detalle_toma_las_mismas_filas_que_venta_mensual():
    filas = [
        _staging(1),
        _staging(2, sucursal=None),
        _staging(3, referencia=None),
        _staging(4, extra=False),  # staged by a pre-detail version: skipped
    ]

    detalle = ventas.construir_detalle(filas, CARGA_ID)

    assert len(detalle) == 1
    d = detalle[0]
    assert d["fecha"] == date(2026, 9, 15)
    assert (d["anio"], d["mes"], d["origen"], d["cantidad"]) == (2026, 9, "MOSTRADOR", Decimal("10"))
    assert d["vendedor"] == "Ana Pérez" and d["vendedor_norm"] == "ANA PEREZ"
    assert d["valor_bruto"] == Decimal("1000") and d["valor_descuentos"] == Decimal("100")
    assert d["cliente_factura"] == "Taller" and d["carga_id"] == CARGA_ID
    assert d["nro_documento"] == "FV-1001"


async def test_aplicar_detalle_borra_por_clave_y_luego_inserta():
    session = FakeAsyncSession(execute_queue=[[], []])

    await ventas.aplicar_detalle(session, [_staging(1), _staging(2)], CARGA_ID)

    borrado, insercion = session.executed_statements
    assert borrado.is_delete and borrado.table.name == "venta_detalle"
    assert insercion.is_insert and insercion.table.name == "venta_detalle"


async def test_aplicar_detalle_inserta_en_lotes():
    filas = [_staging(i) for i in range(ventas.TAMANO_LOTE_DETALLE * 2 + 1)]
    session = FakeAsyncSession(execute_queue=[[]] * 4)

    await ventas.aplicar_detalle(session, filas, CARGA_ID)

    assert len(session.executed_statements) == 1 + 3  # delete + 3 chunks


async def test_aplicar_detalle_sin_filas_no_ejecuta_nada():
    session = FakeAsyncSession()

    await ventas.aplicar_detalle(session, [_staging(1, extra=False)], CARGA_ID)

    assert session.executed_statements == []
