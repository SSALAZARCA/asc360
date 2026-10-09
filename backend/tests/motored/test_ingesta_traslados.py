"""
TRASLADOS load (odd/tasks/motored-traslados-pendientes.md, T1): the ERP file
of transfers between stores still alive in the ERP, one row per transfer
line. Text cells arrive padded with spaces; `Nro documento` repeats across
origin bodegas; an unknown destination is a row error, an unknown origin or
reference is kept.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.motored.services.ingesta import (
    columnas, deteccion, orquestador, plantillas, resolucion, traslados,
)

CARGA_ID = uuid.uuid4()
SUC_ORIGEN = uuid.uuid4()
SUC_DESTINO = uuid.uuid4()
REF_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()

CACHE = resolucion.CacheResolucion(
    sucursal_por_texto={"BB181": SUC_ORIGEN, "BB011": SUC_DESTINO},
    referencia_por_codigo={"BB2.5L-C-BS": (REF_ID, PROVEEDOR_ID)},
)

ENCABEZADO = (
    "Nro documento", "Fecha", "Bod. salida", "Desc. bod. salida",
    "Bod. entrada", "Desc. bod. entrada", "Referencia", "Desc. item",
    "Item resumen", "U.M.", "Cant. Saldo",
)


def _mapa(encabezado=ENCABEZADO):
    return columnas.construir_mapa_columnas(
        encabezado, traslados.COLUMNAS_ESPERADAS + traslados.COLUMNAS_OPCIONALES)


def _fila(**cambios):
    base = {
        "Nro documento": "79-00000067", "Fecha": datetime(2026, 8, 3),
        "Bod. salida": "BB181", "Desc. bod. salida": "BODEGA 1 DE MAYO TRES   ",
        "Bod. entrada": "BB011", "Desc. bod. entrada": "BOGOTA VENECIA",
        "Referencia": "BB2.5L-C-BS                    ",
        "Desc. item": "BATERIA BS SLA        ", "Item resumen": "x",
        "U.M.": "UND ", "Cant. Saldo": 2,
    }
    base.update(cambios)
    return tuple(base[c] for c in ENCABEZADO)


def _procesar(fila, mapa=None, cache=CACHE):
    return traslados.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=mapa or _mapa(),
        cache=cache, carga_id=CARGA_ID, proveedor_id=PROVEEDOR_ID)


def test_fila_valida_recorta_textos_y_resuelve_tiendas_y_referencia():
    staging, errores = _procesar(_fila())

    assert errores == []
    assert staging.sucursal_id == SUC_DESTINO
    assert staging.referencia_id == REF_ID
    p = staging.payload
    assert p["nro_documento"] == "79-00000067"
    assert p["fecha"] == "2026-08-03"
    assert p["bodega_salida"] == "BB181"
    assert p["bodega_entrada"] == "BB011"
    assert p["descripcion_bodega_salida"] == "BODEGA 1 DE MAYO TRES"
    assert p["referencia_codigo"] == "BB2.5L-C-BS"
    assert p["descripcion"] == "BATERIA BS SLA"
    assert p["unidad"] == "UND"
    assert Decimal(p["cantidad"]) == Decimal("2")
    assert p["sucursal_salida_id"] == str(SUC_ORIGEN)


def test_las_columnas_opcionales_pueden_faltar():
    encabezado = traslados.COLUMNAS_ESPERADAS
    fila = tuple(_fila()[ENCABEZADO.index(c)] for c in encabezado)

    staging, errores = _procesar(fila, mapa=_mapa(encabezado))

    assert errores == []
    assert staging.payload["descripcion"] is None
    assert staging.payload["unidad"] is None
    assert staging.payload["descripcion_bodega_salida"] is None


def test_obligatorias_son_las_seis_del_archivo():
    assert traslados.COLUMNAS_ESPERADAS == (
        "Nro documento", "Fecha", "Bod. salida", "Bod. entrada",
        "Referencia", "Cant. Saldo")
    assert set(traslados.COLUMNAS_OPCIONALES) == {
        "Desc. bod. salida", "Desc. bod. entrada", "Desc. item",
        "Item resumen", "U.M."}


def test_destino_desconocido_es_error_de_fila_sin_staging():
    staging, errores = _procesar(_fila(**{
        "Bod. entrada": "ZZ999", "Desc. bod. entrada": "NO EXISTE"}))

    assert staging is None
    assert [e.codigo_error for e in errores] == ["SUCURSAL_NO_ENCONTRADA"]


def test_destino_se_resuelve_por_descripcion_si_el_codigo_no_existe():
    cache = resolucion.CacheResolucion(
        sucursal_por_texto={"BOGOTA VENECIA": SUC_DESTINO},
        referencia_por_codigo={})
    staging, errores = _procesar(_fila(**{"Bod. entrada": "ZZ999"}), cache=cache)

    assert errores == []
    assert staging.sucursal_id == SUC_DESTINO


def test_origen_desconocido_se_guarda_sin_tienda_ni_error():
    cache = resolucion.CacheResolucion(
        sucursal_por_texto={"BB011": SUC_DESTINO}, referencia_por_codigo={})
    staging, errores = _procesar(_fila(**{"Bod. salida": "ZZ1"}), cache=cache)

    assert errores == []
    assert staging.payload["sucursal_salida_id"] is None
    assert staging.payload["bodega_salida"] == "ZZ1"


def test_referencia_desconocida_se_conserva_sin_error():
    staging, errores = _procesar(_fila(Referencia="  NUEVA-REF  "))

    assert errores == []
    assert staging.referencia_id is None
    assert staging.payload["referencia_codigo"] == "NUEVA-REF"


def test_cantidad_cero_o_negativa_es_error():
    for valor in (0, -3):
        staging, errores = _procesar(_fila(**{"Cant. Saldo": valor}))
        assert staging is None
        assert [e.codigo_error for e in errores] == [
            traslados.CODIGO_CANTIDAD_INVALIDA]


def test_cantidad_vacia_o_texto_es_error():
    for valor in (None, "dos"):
        staging, errores = _procesar(_fila(**{"Cant. Saldo": valor}))
        assert staging is None
        assert len(errores) == 1


def test_fecha_invalida_es_error():
    staging, errores = _procesar(_fila(Fecha="no es fecha"))

    assert staging is None
    assert [e.codigo_error for e in errores] == [traslados.CODIGO_FECHA_INVALIDA]


def test_fecha_texto_iso_se_acepta():
    staging, _ = _procesar(_fila(Fecha=date(2026, 8, 3)))

    assert staging.payload["fecha"] == "2026-08-03"


def test_fila_de_relleno_sin_documento_se_descarta_en_silencio():
    assert _procesar(_fila(**{"Nro documento": None})) == (None, [])
    assert _procesar(_fila(**{"Nro documento": "   "})) == (None, [])


def test_bodega_de_salida_vacia_es_error():
    staging, errores = _procesar(_fila(**{"Bod. salida": " "}))

    assert staging is None
    assert [e.codigo_error for e in errores] == [
        traslados.CODIGO_BODEGA_SALIDA_VACIA]


def test_el_tipo_esta_registrado_como_movimiento_con_firma_y_plantilla():
    assert "TRASLADOS" in orquestador.TIPOS_MOVIMIENTO
    assert deteccion.columnas_esperadas_de("TRASLADOS") == (
        traslados.COLUMNAS_ESPERADAS)
    assert deteccion.ETIQUETAS_TIPO["TRASLADOS"] == "Traslados"
    assert plantillas.columnas_plantilla("TRASLADOS") == (
        traslados.COLUMNAS_ESPERADAS + traslados.COLUMNAS_OPCIONALES)
    assert "TRASLADOS" in orquestador._CONSTRUCTORES_PROCESADOR


def test_la_firma_detecta_el_archivo_real():
    deteccion.verificar_tipo("TRASLADOS", [ENCABEZADO, _fila()])
