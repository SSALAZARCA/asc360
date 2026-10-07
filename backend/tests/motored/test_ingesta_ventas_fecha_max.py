"""
Motored Pedidos F3 "Motor", slice S0 (sdd/motored-pedidos-motor, addendum
"Ingest delta - VENTAS records fecha_max_detectada", design ADR-12).

El ingest de VENTAS conserva el DIA de la venta (`payload["dia"]`) y deja la
fecha maxima detectada en `carga_archivo.log["fecha_max_detectada"]` (ISO).
Es un cambio aditivo: `venta_mensual` no cambia y una carga vieja sin la clave
sigue siendo valida. Todas las fechas y filas son sinteticas.
"""
import io
import uuid
from datetime import date, datetime

import openpyxl

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import orquestador, periodo, ventas
from app.motored.services.ingesta.resolucion import CacheResolucion

PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()

_ENCABEZADO = [
    "Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
    "Desc.bodega", "Bodega", "Referencia", "Nombre vendedor", "Valor bruto",
    "Valor descuentos", "Cliente factura", "Nro documento",
]
_MAPA_COLUMNAS = {nombre: idx for idx, nombre in enumerate(_ENCABEZADO)}


def _fila_excel(fecha):
    return [
        "Aprobada", "MOSTRADOR", fecha, 10, "REPUESTOS",
        "CALI NORTE", "BA061", "REF1", "Ana Pérez", 1000, 0, "Taller", "FV-1",
    ]


def _xlsx(fechas) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(_ENCABEZADO)
    for fecha in fechas:
        sheet.append(_fila_excel(fecha))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _carga(desde: date, hasta: date, **overrides) -> CargaArchivo:
    base = dict(
        id=uuid.uuid4(), tipo="VENTAS", nombre_archivo="ventas.xlsx",
        hash_sha256="a" * 64, ruta_objeto="VENTAS/2026/09/x.xlsx", bytes=100,
        estado="PROCESANDO", filas_leidas=0, filas_validas=0, filas_rechazadas=0,
        periodo_desde=desde, periodo_hasta=hasta, lotes_staged=0,
        ultimo_lote_aplicado=0, latido_en=None, log=None,
        subido_por=uuid.uuid4(), aplicado_en=None,
    )
    base.update(overrides)
    return CargaArchivo(**base)


def _cola_dry_run():
    return [
        [(SUCURSAL_ID, "CALI NORTE", None)],
        [],  # bodegas
        [],  # sucursal_alias
        [("REF1", PROVEEDOR_ID, REFERENCIA_ID)],
        [PROVEEDOR_ID],
        [],  # tipos_inventario_incluidos -> default
        [],  # bodegas_excluidas -> default
        [],  # ventas_tipos_excluidos -> default
        [(REFERENCIA_ID, "REPUESTOS")],  # linea del maestro
        [],  # periodo_tolerancia_pct -> entorno
    ]


async def _dry_run(monkeypatch, carga, fechas) -> None:
    contenido = _xlsx(fechas)
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    session = FakeAsyncSession(execute_queue=_cola_dry_run() + [[]])
    await orquestador._dry_run(session, carga)


def _procesar(fecha):
    return ventas.procesar_fila(
        _fila_excel(fecha),
        numero_fila=2, lote=1, mapa_columnas=_MAPA_COLUMNAS,
        cache=CacheResolucion(
            sucursal_por_texto={"CALI NORTE": SUCURSAL_ID},
            referencia_por_codigo={"REF1": (REFERENCIA_ID, PROVEEDOR_ID)},
        ),
        carga_id=uuid.uuid4(), proveedor_id=PROVEEDOR_ID,
        tipos_inventario_incluidos=["REPUESTOS"],
        linea_por_referencia={REFERENCIA_ID: "REPUESTOS"},
    )


def _staged(anio, mes, dia=None):
    payload = {"anio": anio, "mes": mes, "origen": "MOSTRADOR", "cantidad": "1"}
    if dia is not None:
        payload["dia"] = dia
    return CargaFilaStaging(
        carga_id=uuid.uuid4(), fila=1, lote=1, payload=payload,
        sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID,
    )


# ---------------------------------------------------------------------------
# Transform: el payload conserva el dia
# ---------------------------------------------------------------------------


def test_payload_conserva_el_dia_desde_una_celda_de_fecha():
    fila_staging, _ = _procesar(datetime(2026, 9, 14))

    assert fila_staging.payload["dia"] == 14
    assert (fila_staging.payload["anio"], fila_staging.payload["mes"]) == (2026, 9)


def test_payload_conserva_el_dia_desde_un_serial_de_excel():
    fila_staging, _ = _procesar(46279)  # 2026-09-14 como serial

    assert fila_staging.payload["dia"] == 14
    assert (fila_staging.payload["anio"], fila_staging.payload["mes"]) == (2026, 9)


def test_fecha_maxima_de_filas_toma_el_maximo_entre_meses():
    filas = [_staged(2026, 8, 30), _staged(2026, 9, 3), _staged(2026, 9, 14), _staged(2026, 8, 31)]

    assert ventas.fecha_maxima_de_filas(filas) == date(2026, 9, 14)


def test_fecha_maxima_de_filas_ignora_filas_sin_dia_y_sin_filas():
    assert ventas.fecha_maxima_de_filas([_staged(2026, 9), _staged(2026, 9, 5)]) == date(2026, 9, 5)
    assert ventas.fecha_maxima_de_filas([_staged(2026, 9)]) is None
    assert ventas.fecha_maxima_de_filas([]) is None


# ---------------------------------------------------------------------------
# Dry-run: log["fecha_max_detectada"]
# ---------------------------------------------------------------------------


async def test_dry_run_registra_fecha_max_detectada(monkeypatch):
    carga = _carga(date(2026, 9, 1), date(2026, 9, 30))

    await _dry_run(monkeypatch, carga, [datetime(2026, 9, 2), datetime(2026, 9, 14)])

    assert carga.estado == "VALIDADO"
    assert carga.log["fecha_max_detectada"] == "2026-09-14"


async def test_dry_run_fecha_max_es_el_maximo_de_todo_el_archivo_multi_mes(monkeypatch):
    carga = _carga(date(2026, 8, 1), date(2026, 9, 30))

    await _dry_run(
        monkeypatch, carga,
        [datetime(2026, 8, 20), datetime(2026, 9, 14), datetime(2026, 8, 30)],
    )

    assert carga.estado == "VALIDADO"
    assert carga.log["fecha_max_detectada"] == "2026-09-14"


async def test_dry_run_rechazado_por_periodo_no_rompe_y_mantiene_el_veredicto(monkeypatch):
    carga = _carga(date(2026, 9, 1), date(2026, 9, 30))

    await _dry_run(monkeypatch, carga, [datetime(2026, 8, 15)])

    assert carga.estado == "CON_ERRORES"
    assert carga.log["periodo_veredicto"] == "RECHAZO"


# ---------------------------------------------------------------------------
# Aplicar: el valor del dry-run es el persistido; cargas viejas siguen validas
# ---------------------------------------------------------------------------


async def _aplicar(monkeypatch, carga) -> None:
    async def _aplicar_falso(session, filas_staging, desde, hasta, carga_id, tolerancia_pct=None):
        return periodo.VeredictoPeriodo(tipo=periodo.TipoVeredictoPeriodo.ACEPTADO)

    monkeypatch.setattr(orquestador.ventas_mod, "aplicar_con_periodo", _aplicar_falso)
    # staging, tipos incluidos, tolerancia, delete staging
    await orquestador.ejecutar_aplicar(FakeAsyncSession(execute_queue=[[], [], [], []]), carga)


async def test_aplicar_conserva_el_valor_calculado_en_el_dry_run(monkeypatch):
    carga = _carga(
        date(2026, 9, 1), date(2026, 9, 30), estado="VALIDADO",
        log={"fecha_max_detectada": "2026-09-14", "periodo_veredicto": "ACEPTADO"},
    )

    await _aplicar(monkeypatch, carga)

    assert carga.estado == "APLICADO"
    assert carga.log["fecha_max_detectada"] == "2026-09-14"


async def test_carga_anterior_sin_la_clave_se_aplica_sin_error(monkeypatch):
    carga = _carga(
        date(2026, 9, 1), date(2026, 9, 30), estado="VALIDADO",
        log={"periodo_veredicto": "ACEPTADO"},
    )

    await _aplicar(monkeypatch, carga)

    assert carga.estado == "APLICADO"
    assert carga.log.get("fecha_max_detectada") is None
    assert carga.log["periodo_veredicto"] == "ACEPTADO"
