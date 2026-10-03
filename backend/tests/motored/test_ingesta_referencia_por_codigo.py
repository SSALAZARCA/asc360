"""
Motored `motored-referencia-identidad` (R1): los movimientos (VENTAS,
INVENTARIO, ...) resuelven la referencia por su CODIGO, sea cual sea su
proveedor. Antes solo resolvian las del proveedor principal (HMCL), asi que
una referencia de otro proveedor terminaba como "referencia no encontrada" y
nunca llegaba a `venta_mensual`, `venta_detalle` ni `inventario_detalle`.

(a) caracterizacion: con datos SOLO de HMCL el resultado es el mismo de
    siempre (escrita contra el codigo anterior y mantenida verde).
(b) una referencia de otro proveedor ahora resuelve en VENTAS e INVENTARIO.
(d) una referencia inactiva igual resuelve en la ingesta.
(c) el movimiento de proveedor conserva id y ventas: vive en
    `pg_real/test_referencia_identidad_pg.py` (necesita Postgres real).
"""
import uuid
from datetime import date
from decimal import Decimal

from tests.motored.conftest import FakeAsyncSession

from app.motored.services.ingesta import inventario, ventas
from app.motored.services.ingesta.resolucion import construir_cache

CARGA_ID = uuid.uuid4()
HMCL = uuid.uuid4()
OTRO = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REF_HMCL_1, REF_HMCL_2, REF_OTRO, REF_INACTIVA = (uuid.uuid4() for _ in range(4))

_MAPA_VENTAS = {
    "Estado": 0, "Módulo": 1, "Fecha": 2, "Cantidad inv.": 3, "Tipo inventario": 4,
    "Desc.bodega": 5, "Bodega": 6, "Referencia": 7, "Nombre vendedor": 8,
    "Valor bruto": 9, "Valor descuentos": 10, "Cliente factura": 11, "Nro documento": 12,
}
_MAPA_INVENTARIO = {"Desc.bodega": 0, "Bodega": 1, "Referencia": 2, "Existencia": 3}
_SERIAL_2026_09_15 = 46280

_REFERENCIAS = [
    ("H-1", HMCL, REF_HMCL_1),
    ("H-2", HMCL, REF_HMCL_2),
    ("O-1", OTRO, REF_OTRO),
    ("INACT-1", HMCL, REF_INACTIVA),  # la consulta de ingesta no filtra `activa`
]


async def _cache(referencias=_REFERENCIAS):
    session = FakeAsyncSession(execute_queue=[
        [(SUCURSAL_ID, "CALI NORTE", None)], [], [], list(referencias)])
    return await construir_cache(session)


def _fila_venta(referencia, cantidad):
    return ("Aprobada", "MOSTRADOR", _SERIAL_2026_09_15, cantidad, "0002 - REPUESTOS",
            "CALI NORTE", "BA061", referencia, "Ana Pérez", 1000, 0, "Taller El Rayo", f"FV-{referencia}")


def _procesar_ventas(cache, filas):
    staging, errores = [], []
    for numero, fila in enumerate(filas, start=2):
        fila_staging, errores_fila = ventas.procesar_fila(
            fila, numero_fila=numero, lote=1, mapa_columnas=_MAPA_VENTAS, cache=cache,
            carga_id=CARGA_ID, proveedor_id=HMCL, tipos_inventario_incluidos=["0002 - REPUESTOS"])
        if fila_staging is not None:
            staging.append(fila_staging)
        errores += errores_fila
    return staging, errores


def _procesar_inventario(cache, filas):
    staging, errores = [], []
    for numero, fila in enumerate(filas, start=2):
        fila_staging, errores_fila = inventario.procesar_fila(
            fila, numero_fila=numero, lote=1, mapa_columnas=_MAPA_INVENTARIO, cache=cache,
            carga_id=CARGA_ID, proveedor_id=HMCL)
        if fila_staging is not None:
            staging.append(fila_staging)
        errores += errores_fila
    return staging, errores


# --- (a) HMCL-only: igual que antes ------------------------------------------


async def test_ventas_solo_hmcl_da_los_mismos_totales_log_y_staging():
    cache = await _cache()
    filas = [_fila_venta("H-1", 10), _fila_venta("H-1", -2), _fila_venta("H-2", 5),
             _fila_venta("NO-EXISTE", 7)]

    staging, errores = _procesar_ventas(cache, filas)

    assert [(f.fila, f.referencia_id) for f in staging] == [
        (2, REF_HMCL_1), (3, REF_HMCL_1), (4, REF_HMCL_2), (5, None)]
    assert [(e.fila, e.codigo_error, e.valor) for e in errores] == [
        (5, "REFERENCIA_NO_ENCONTRADA", "NO-EXISTE")]
    assert ventas.agregar_unidades(staging) == {
        (SUCURSAL_ID, REF_HMCL_1, 2026, 9, "MOSTRADOR"): Decimal("8"),
        (SUCURSAL_ID, REF_HMCL_2, 2026, 9, "MOSTRADOR"): Decimal("5"),
    }


async def test_inventario_solo_hmcl_da_los_mismos_totales_log_y_staging():
    cache = await _cache()
    filas = [("CALI NORTE", "BA061", "H-1", 4), ("CALI NORTE", "BA066", "H-1", 6),
             ("CALI NORTE", "BA061", "NO-EXISTE", 1)]

    staging, errores = _procesar_inventario(cache, filas)

    assert [(f.fila, f.referencia_id) for f in staging] == [(2, REF_HMCL_1), (3, REF_HMCL_1), (4, None)]
    assert [(e.fila, e.codigo_error) for e in errores] == [(4, "REFERENCIA_NO_ENCONTRADA")]
    assert inventario.consolidar_existencias(staging) == {(SUCURSAL_ID, REF_HMCL_1): Decimal("10")}


# --- (b) otro proveedor: ahora resuelve ----------------------------------------


async def test_ventas_de_una_referencia_de_otro_proveedor_llega_a_venta_mensual_y_detalle():
    cache = await _cache()

    staging, errores = _procesar_ventas(cache, [_fila_venta("O-1", 3)])

    assert errores == []
    assert staging[0].referencia_id == REF_OTRO
    assert ventas.agregar_unidades(staging) == {
        (SUCURSAL_ID, REF_OTRO, 2026, 9, "MOSTRADOR"): Decimal("3")}
    detalle = ventas.construir_detalle(staging, CARGA_ID)
    assert [d["referencia_id"] for d in detalle] == [REF_OTRO]


async def test_inventario_de_una_referencia_de_otro_proveedor_llega_al_snapshot_y_detalle():
    cache = await _cache()

    staging, errores = _procesar_inventario(cache, [("CALI NORTE", "BA061", "O-1", 9)])

    assert errores == []
    assert inventario.consolidar_existencias(staging) == {(SUCURSAL_ID, REF_OTRO): Decimal("9")}
    assert [d["referencia_id"] for d in inventario.construir_detalle(staging, date(2026, 9, 21), CARGA_ID)] == [REF_OTRO]


# --- (d) inactiva: igual resuelve ---------------------------------------------


async def test_una_referencia_inactiva_igual_resuelve_en_ventas_e_inventario():
    cache = await _cache()

    staging_v, errores_v = _procesar_ventas(cache, [_fila_venta("INACT-1", 2)])
    staging_i, errores_i = _procesar_inventario(cache, [("CALI NORTE", "BA061", "INACT-1", 2)])

    assert errores_v == [] and errores_i == []
    assert staging_v[0].referencia_id == REF_INACTIVA and staging_i[0].referencia_id == REF_INACTIVA
