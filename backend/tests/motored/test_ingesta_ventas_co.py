"""
VENTAS rows resolve their sucursal by the "C.O." column (owner rule: "Cada
venta se registra en la sucursal de su C.O. (columna G), sin importar de
qué bodega salió el repuesto"). `bodegas_excluidas` is still checked
first; a blank C.O. falls back to the bodega and is counted in
`carga.log["filas_co_vacio"]`; a file without the column keeps the
bodega-first resolution; an unknown C.O. is a row error.
"""
import io
import uuid
from datetime import date

import openpyxl
import pytest

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import columnas
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import orquestador, resolucion, ventas
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_BODEGA = uuid.uuid4()
SUCURSAL_CO = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()
EXCLUIDAS = frozenset({"99999", "PYM01"})
SERIAL_2026_09_15 = 46280
POR_CO = {"F03": SUCURSAL_CO}

_MAPA_SIN_CO = {n: i for i, n in enumerate(ventas.COLUMNAS_ESPERADAS)}
_MAPA_CON_CO = {**_MAPA_SIN_CO, "C.O.": len(ventas.COLUMNAS_ESPERADAS)}


def _cache():
    return CacheResolucion(
        sucursal_por_texto={"CALI NORTE": SUCURSAL_BODEGA,
                            "BA061": SUCURSAL_BODEGA},
        referencia_por_codigo={"REF1": (REFERENCIA_ID, PROVEEDOR_ID)},
    )


def _fila(co="F03", bodega="BA061", desc="CALI NORTE", tipo="REPUESTOS",
          doc="FV-1"):
    return ("Aprobada", "MOSTRADOR", SERIAL_2026_09_15, 5, tipo, desc,
            bodega, "REF1", "Ana Pérez", 1000, 0, "Taller", doc, co)


def _procesar(fila, mapa=_MAPA_CON_CO, por_co=POR_CO, linea="REPUESTOS"):
    return ventas.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=mapa, cache=_cache(),
        carga_id=CARGA_ID, proveedor_id=PROVEEDOR_ID,
        tipos_inventario_incluidos=["REPUESTOS"],
        bodegas_excluidas=EXCLUIDAS, sucursal_por_co=por_co,
        linea_por_referencia={REFERENCIA_ID: linea})


# --- procesar_fila ----------------------------------------------------------


def test_una_fila_cruzada_va_a_la_sucursal_de_su_co():
    staging, errores = _procesar(_fila())

    assert errores == []
    assert staging.sucursal_id == SUCURSAL_CO
    assert ventas.CLAVE_CO_VACIO not in staging.payload


@pytest.mark.parametrize("co", ["F03 ", " f03", "f03"])
def test_el_co_se_recorta_y_pasa_a_mayusculas(co):
    staging, errores = _procesar(_fila(co=co))

    assert errores == []
    assert staging.sucursal_id == SUCURSAL_CO


def test_un_co_desconocido_es_error_de_fila_sin_caer_a_la_bodega():
    staging, errores = _procesar(_fila(co="MR "))

    assert staging.sucursal_id is None
    assert [e.codigo_error for e in errores] == [
        ventas.CODIGO_CO_NO_ENCONTRADO]
    error = errores[0]
    assert error.columna == "C.O."
    assert error.valor == "MR"
    assert error.mensaje == (
        "El C.O. 'MR' no corresponde a ninguna sucursal. "
        "Cárguelo en Maestros > Sucursales.")


@pytest.mark.parametrize("co", [None, "", "   "])
def test_un_co_vacio_cae_a_la_bodega_y_queda_marcado(co):
    staging, errores = _procesar(_fila(co=co))

    assert errores == []
    assert staging.sucursal_id == SUCURSAL_BODEGA
    assert ventas.tiene_co_vacio(staging) is True


def test_un_co_vacio_con_bodega_desconocida_sigue_dando_error_de_sucursal():
    staging, errores = _procesar(_fila(co=None, bodega="ZZ9", desc="RARA"))

    assert staging.sucursal_id is None
    assert [e.codigo_error for e in errores] == [
        errores_mod.CODIGO_SUCURSAL_NO_ENCONTRADA]


def test_sin_columna_co_resuelve_por_bodega_como_antes():
    fila = _fila()[:-1]

    staging, errores = _procesar(fila, mapa=_MAPA_SIN_CO, por_co=None)

    assert errores == []
    assert staging.sucursal_id == SUCURSAL_BODEGA
    assert ventas.tiene_co_vacio(staging) is False


def test_la_bodega_excluida_se_mira_antes_que_el_co():
    resultado = _procesar(_fila(bodega="PYM01", co="F03"))

    assert resultado is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_la_bodega_excluida_gana_aunque_el_co_sea_desconocido():
    resultado = _procesar(_fila(bodega="99999", co="MR"))

    assert resultado is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_una_fila_solo_detalle_tambien_usa_el_co():
    staging, errores = _procesar(_fila(), linea="MOTOS")

    assert errores == []
    assert ventas.es_solo_detalle(staging)
    assert staging.sucursal_id == SUCURSAL_CO


def test_una_fila_solo_detalle_con_co_desconocido_se_omite_en_silencio():
    staging, errores = _procesar(_fila(co="ZZZ"), linea="MOTOS")

    assert (staging, errores) == (None, [])


@pytest.mark.parametrize("encabezado", [
    "C.O.", "CO", "Centro de operación", "Centro de operacion", " c.o. ",
])
def test_reconoce_los_alias_de_la_columna(encabezado):
    mapa = columnas.construir_mapa_columnas(
        ["Bodega", encabezado],
        ventas.COLUMNAS_ESPERADAS + ventas.ALIAS_COLUMNA_CO)

    assert ventas.tiene_columna_co(mapa) is True


def test_sin_ningun_alias_no_hay_columna_co():
    assert ventas.tiene_columna_co({"Bodega": 0}) is False


# --- lectura del mapa C.O. ---------------------------------------------------


async def test_leer_sucursal_por_co_normaliza_las_claves():
    otra = uuid.uuid4()
    session = FakeAsyncSession(
        execute_queue=[[("F03", SUCURSAL_CO), (" e05 ", otra)]])

    mapa = await resolucion.leer_sucursal_por_co(session)

    assert mapa == {"F03": SUCURSAL_CO, "E05": otra}


# --- orquestador ------------------------------------------------------------


def _xlsx(encabezado, filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(encabezado))
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _carga():
    return CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", nombre_archivo="a.xlsx",
        hash_sha256="a" * 64, ruta_objeto="VENTAS/x.xlsx", bytes=100,
        estado="PROCESANDO", filas_leidas=0, filas_validas=0,
        filas_rechazadas=0, lotes_staged=0, ultimo_lote_aplicado=0,
        subido_por=uuid.uuid4(), log=None, periodo_desde=date(2026, 9, 1),
        periodo_hasta=date(2026, 9, 30))


def _cola(lectura_co):
    """cache (4) + proveedor + tipos + bodegas_excluidas + [C.O.] +
    periodo_tolerancia_pct."""
    base = [
        [(SUCURSAL_BODEGA, "CALI NORTE", None)], [], [],
        [("REF1", PROVEEDOR_ID, REFERENCIA_ID)], [PROVEEDOR_ID], [], [],
    ]
    # ... + ventas_tipos_excluidos + linea del maestro + tolerancia.
    return base + lectura_co + [[], [(REFERENCIA_ID, "REPUESTOS")], []]


@pytest.fixture(autouse=True)
def _sin_memoria():
    orquestador._memoria_bodegas_excluidas.clear()
    yield
    orquestador._memoria_bodegas_excluidas.clear()


async def _dry_run(monkeypatch, encabezado, filas, lectura_co):
    carga = _carga()
    contenido = _xlsx(encabezado, filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    session = FakeAsyncSession(execute_queue=_cola(lectura_co))
    await orquestador._dry_run(session, carga)
    return carga, session


def _sucursal_por_doc(session):
    return {f.payload["nro_documento"]: f.sucursal_id
            for f in session.added_of_type(CargaFilaStaging)}


@pytest.mark.parametrize("columna", ["C.O.", "Centro de operación", "CO"])
async def test_dry_run_resuelve_por_co_y_cuenta_los_vacios(
        monkeypatch, columna):
    filas = [
        _fila(co="F03 ", doc="FV-1"),
        _fila(co=None, doc="FV-2"),
        _fila(co="X99 ", bodega="BX991", desc="DESCONOCIDA", doc="FV-3"),
        _fila(co="F03", bodega="99999", doc="FV-4"),
    ]

    carga, session = await _dry_run(
        monkeypatch, ventas.COLUMNAS_ESPERADAS + (columna,), filas,
        [[("F03", SUCURSAL_CO)]])

    assert carga.estado == "VALIDADO"
    assert _sucursal_por_doc(session) == {
        "FV-1": SUCURSAL_CO, "FV-2": SUCURSAL_BODEGA, "FV-3": None}
    errores = session.added_of_type(CargaError)
    assert [(e.codigo_error, e.valor) for e in errores] == [
        (ventas.CODIGO_CO_NO_ENCONTRADO, "X99")]
    assert carga.log["filas_co_vacio"] == 1
    assert carga.log["filas_bodega_excluida"] == 1
    assert carga.log["filas_con_error"] == 1


async def test_dry_run_sin_columna_co_no_lee_el_mapa_y_usa_la_bodega(
        monkeypatch):
    filas = [_fila(doc="FV-1")[:-1]]

    carga, session = await _dry_run(
        monkeypatch, ventas.COLUMNAS_ESPERADAS, filas, [])

    assert carga.estado == "VALIDADO"
    assert _sucursal_por_doc(session) == {"FV-1": SUCURSAL_BODEGA}
    assert "filas_co_vacio" not in carga.log
