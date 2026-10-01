"""
VENTAS: tipos de inventario de TALLER y detalle independiente del tipo.

Decision del owner: la demanda de taller cuenta para el pedido. El ERP marca
los repuestos de taller "IRPTOSYACC" y los lubricantes "IVNLUBGR"; el default
de `tipos_inventario_incluidos` los incluye. Aparte, `venta_detalle` guarda
TODA linea aprobada sin importar el tipo ("0001 - MOTOCICLETA" incluido): esas
filas se stagean con `solo_detalle` y `venta_mensual`, el periodo detectado y
`fecha_max_detectada` jamas las ven.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.motored.conftest import FakeAsyncSession
from tests.motored.test_ingesta_orquestador import (
    PROVEEDOR_ID,
    REFERENCIA_ID,
    SUCURSAL_ID,
    _build_xlsx_bytes,
    _carga,
    _queue_cache_y_proveedor,
)

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services import parametros, parametros_claves
from app.motored.services.ingesta import orquestador, periodo as periodo_mod, ventas
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
_MAPA = {nombre: idx for idx, nombre in enumerate(ventas.COLUMNAS_ESPERADAS)}
_SERIAL_2026_09_15 = 46280
_SERIAL_2026_08_15 = 46249
TIPOS_NUEVO_DEFAULT = ["0002 - REPUESTOS", "IRPTOSYACC", "IVNLUBGR", "0003 - OTROS"]


def _cache():
    return CacheResolucion(
        sucursal_por_texto={"CALI NORTE": SUCURSAL_ID},
        referencia_por_codigo_proveedor={("REF1", PROVEEDOR_ID): REFERENCIA_ID},
    )


def _fila(tipo="0002 - REPUESTOS", modulo="MOSTRADOR", fecha=_SERIAL_2026_09_15,
          cantidad=10, bodega="CALI NORTE", ref="REF1", estado="Aprobada",
          vendedor="Ana Pérez", nro_doc="FV-1"):
    return (estado, modulo, fecha, cantidad, tipo, bodega, "BA061", ref,
            vendedor, 1000, 0, "Taller", nro_doc)


def _procesar(fila_raw, tipos=("0002 - REPUESTOS",)):
    return ventas.procesar_fila(
        fila_raw, numero_fila=2, lote=1, mapa_columnas=_MAPA, cache=_cache(),
        carga_id=CARGA_ID, proveedor_id=PROVEEDOR_ID,
        tipos_inventario_incluidos=list(tipos),
    )


# --- defaults ---------------------------------------------------------------


def test_default_del_registro_incluye_los_tipos_de_taller():
    assert parametros_claves.REGISTRO["tipos_inventario_incluidos"].default == (
        TIPOS_NUEVO_DEFAULT)


def test_default_del_resolver_coincide_con_el_del_registro():
    assert parametros.DEFAULT_TIPOS_INVENTARIO_INCLUIDOS == TIPOS_NUEVO_DEFAULT


# --- procesar_fila ----------------------------------------------------------


def test_fila_de_tipo_incluido_no_lleva_la_marca_solo_detalle():
    staging, errores = _procesar(_fila())

    assert errores == []
    assert "solo_detalle" not in staging.payload


def test_fila_taller_irptosyacc_con_el_default_cae_en_venta_mensual_como_taller():
    staging, errores = _procesar(_fila(tipo="IRPTOSYACC", modulo="Taller"),
                                 tipos=TIPOS_NUEVO_DEFAULT)

    assert errores == []
    assert staging.payload["origen"] == "TALLER"
    assert "solo_detalle" not in staging.payload
    assert ventas.agregar_unidades([staging]) == {
        (SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "TALLER"): Decimal("10")}


def test_fila_taller_lubricantes_ivnlubgr_con_el_default_cae_en_venta_mensual():
    staging, errores = _procesar(_fila(tipo="IVNLUBGR", modulo="TALLER"),
                                 tipos=TIPOS_NUEVO_DEFAULT)

    assert errores == []
    assert len(ventas.agregar_unidades([staging])) == 1


def test_tipo_con_espacios_al_final_tambien_coincide():
    staging, _ = _procesar(_fila(tipo="IRPTOSYACC  "), tipos=TIPOS_NUEVO_DEFAULT)

    assert "solo_detalle" not in staging.payload


def test_fila_de_tipo_excluido_se_stagea_solo_para_detalle_sin_errores():
    staging, errores = _procesar(_fila(tipo="0001 - MOTOCICLETA"))

    assert errores == []
    assert staging.payload["solo_detalle"] is True
    assert staging.sucursal_id == SUCURSAL_ID and staging.referencia_id == REFERENCIA_ID


@pytest.mark.parametrize("fila", [
    _fila(tipo="0001 - MOTOCICLETA", ref="NOEXISTE"),
    _fila(tipo="0001 - MOTOCICLETA", bodega="NOEXISTE"),
    _fila(tipo="0001 - MOTOCICLETA", cantidad="abc"),
    _fila(tipo="0001 - MOTOCICLETA", fecha="no es fecha"),
    _fila(tipo="0001 - MOTOCICLETA", vendedor=None),
    _fila(tipo="0001 - MOTOCICLETA", nro_doc=None),
    _fila(tipo="0001 - MOTOCICLETA", estado="Pendiente"),
])
def test_fila_excluida_con_problema_se_omite_en_silencio(fila):
    assert _procesar(fila) == (None, [])


def test_fila_de_tipo_incluido_con_referencia_desconocida_sigue_siendo_error():
    staging, errores = _procesar(_fila(ref="NOEXISTE"))

    assert [e.columna for e in errores] == ["Referencia"]
    assert staging is not None  # semantica previa: se stagea con ref None y error


# --- las rutas de venta_mensual ignoran las filas solo_detalle ---------------


def _staging(mes=9, dia=15, solo_detalle=False, cantidad="10", fila=1):
    payload = {"anio": 2026, "mes": mes, "dia": dia, "origen": "MOSTRADOR",
               "cantidad": cantidad, "vendedor": "Ana", "valor_bruto": "1000",
               "valor_descuentos": "0", "cliente_factura": "T", "nro_documento": "FV"}
    if solo_detalle:
        payload["solo_detalle"] = True
    return CargaFilaStaging(carga_id=CARGA_ID, fila=fila, lote=1, payload=payload,
                            sucursal_id=SUCURSAL_ID, referencia_id=REFERENCIA_ID)


def test_agregar_unidades_ignora_las_filas_solo_detalle():
    filas = [_staging(), _staging(solo_detalle=True, cantidad="99")]

    assert ventas.agregar_unidades(filas) == {
        (SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR"): Decimal("10")}


def test_histograma_y_fecha_maxima_ignoran_las_filas_solo_detalle():
    filas = [_staging(mes=9, dia=15), _staging(mes=10, dia=30, solo_detalle=True)]

    assert ventas.construir_filas_por_periodo(filas) == {(2026, 9): 1}
    assert ventas.fecha_maxima_de_filas(filas) == date(2026, 9, 15)
    assert ventas.fecha_maxima_de_filas([filas[1]]) is None


def test_construir_detalle_incluye_las_filas_solo_detalle():
    detalle = ventas.construir_detalle(
        [_staging(), _staging(solo_detalle=True, fila=2)], CARGA_ID)

    assert len(detalle) == 2


async def test_aplicar_con_periodo_no_rechaza_por_filas_solo_detalle_de_otro_mes():
    # Declarado septiembre; el unico dato de venta_mensual es de septiembre.
    # Cien filas excluidas de agosto no pueden volcar el veredicto a RECHAZO.
    filas = [_staging()] + [_staging(mes=8, solo_detalle=True, fila=i + 2) for i in range(100)]
    session = FakeAsyncSession(execute_queue=[[], [], []])

    veredicto = await ventas.aplicar_con_periodo(
        session, filas, date(2026, 9, 1), date(2026, 9, 30), CARGA_ID)

    assert veredicto.tipo == periodo_mod.TipoVeredictoPeriodo.ACEPTADO
    tablas = [s.table.name for s in session.executed_statements]
    assert tablas[0] == "venta_mensual"


async def test_aplicar_con_periodo_escribe_detalle_de_las_filas_solo_detalle_del_periodo():
    filas = [_staging(), _staging(solo_detalle=True, fila=2)]
    session = FakeAsyncSession(execute_queue=[[], [], []])

    await ventas.aplicar_con_periodo(
        session, filas, date(2026, 9, 1), date(2026, 9, 30), CARGA_ID)

    insercion = session.executed_statements[-1]
    assert insercion.is_insert and insercion.table.name == "venta_detalle"
    assert len(insercion._multi_values[0]) == 2


# --- dry-run de punta a punta -----------------------------------------------

_ENCABEZADO = list(ventas.COLUMNAS_ESPERADAS)


async def _dry_run(monkeypatch, filas, tipos_resueltos=None, extra_queue=()):
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30))
    contenido = _build_xlsx_bytes([_ENCABEZADO] + [list(f) for f in filas])
    monkeypatch.setattr(orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    vigente = [] if tipos_resueltos is None else [tipos_resueltos]
    session = FakeAsyncSession(
        execute_queue=_queue_cache_y_proveedor() + [vigente] + list(extra_queue) + [[]])
    await orquestador._dry_run(session, carga)
    return carga, session


async def test_archivo_solo_mostrador_0002_deja_el_log_identico_al_de_antes(monkeypatch):
    base = [_fila(nro_doc=f"FV-{i}") for i in range(3)]
    con_excluidas = base + [
        _fila(tipo="0001 - MOTOCICLETA", nro_doc="X-1"),
        _fila(tipo="0001 - MOTOCICLETA", fecha=_SERIAL_2026_08_15, nro_doc="X-2"),
        _fila(tipo="0001 - MOTOCICLETA", ref="NOEXISTE", nro_doc="X-3"),
    ]

    carga_a, sesion_a = await _dry_run(monkeypatch, base)
    carga_b, sesion_b = await _dry_run(monkeypatch, con_excluidas)

    # Sin filas excluidas: ninguna clave nueva en el log.
    assert "filas_solo_detalle" not in carga_a.log
    # Con ellas: venta_mensual, periodo y fecha_max son EXACTAMENTE los mismos.
    log_b = dict(carga_b.log)
    assert log_b.pop("filas_solo_detalle") == 2  # la de ref desconocida no se cuenta
    assert log_b == carga_a.log
    assert carga_b.estado == carga_a.estado == "VALIDADO"
    assert carga_b.log["fecha_max_detectada"] == "2026-09-15"
    assert carga_b.filas_validas == carga_a.filas_validas == 3
    assert carga_b.filas_rechazadas == carga_a.filas_rechazadas == 0
    assert (carga_b.periodo_desde, carga_b.periodo_hasta) == (
        carga_a.periodo_desde, carga_a.periodo_hasta)
    assert sesion_b.added_of_type(CargaError) == []
    solo = [f for f in sesion_b.added_of_type(CargaFilaStaging)
            if f.payload.get("solo_detalle")]
    assert len(solo) == 2


async def test_mezcla_de_tipos_deja_taller_en_venta_mensual(monkeypatch):
    filas = [
        _fila(tipo="0002 - REPUESTOS", modulo="MOSTRADOR", nro_doc="M-1"),
        _fila(tipo="IRPTOSYACC", modulo="TALLER", nro_doc="T-1"),
        _fila(tipo="IVNLUBGR", modulo="TALLER", nro_doc="T-2", cantidad=5),
        _fila(tipo="0001 - MOTOCICLETA", modulo="MOSTRADOR", nro_doc="O-1"),
    ]

    carga, sesion = await _dry_run(monkeypatch, filas)  # default nuevo

    staged = sesion.added_of_type(CargaFilaStaging)
    mensuales = [f for f in staged if not f.payload.get("solo_detalle")]
    assert sorted(f.payload["origen"] for f in mensuales) == ["MOSTRADOR", "TALLER", "TALLER"]
    assert ventas.agregar_unidades(staged) == {
        (SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR"): Decimal("10"),
        (SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "TALLER"): Decimal("15"),
    }
    assert carga.filas_validas == 3
    assert carga.log["filas_solo_detalle"] == 1


async def test_fila_solo_detalle_fuera_del_periodo_no_genera_carga_error(monkeypatch):
    # Caso ADVERTENCIA (1 de 200 filas en un mes adyacente): solo la fila de
    # venta_mensual puede recibir A-CARGA-043; la excluida de agosto no.
    filas = [_fila(nro_doc=f"FV-{i}") for i in range(199)]
    filas.append(_fila(fecha=46265, nro_doc="AGO"))  # 2026-08-31, 0002
    filas.append(_fila(tipo="0001 - MOTOCICLETA", fecha=_SERIAL_2026_08_15, nro_doc="X"))
    agosto = CargaFilaStaging(
        carga_id=CARGA_ID, fila=201, lote=1, sucursal_id=SUCURSAL_ID,
        referencia_id=REFERENCIA_ID,
        payload={"anio": 2026, "mes": 8, "origen": "MOSTRADOR", "cantidad": "1"})
    excluida = CargaFilaStaging(
        carga_id=CARGA_ID, fila=202, lote=1, sucursal_id=SUCURSAL_ID,
        referencia_id=REFERENCIA_ID,
        payload={"anio": 2026, "mes": 8, "origen": "MOSTRADOR", "cantidad": "1",
                 "solo_detalle": True})

    carga, sesion = await _dry_run(monkeypatch, filas, extra_queue=[[agosto, excluida]])

    assert carga.log["periodo_veredicto"] == periodo_mod.TipoVeredictoPeriodo.ADVERTENCIA.value
    errores = sesion.added_of_type(CargaError)
    assert [e.fila for e in errores] == [201]


async def test_fila_0003_otros_cuenta_en_venta_mensual_con_el_default(monkeypatch):
    filas = [
        _fila(tipo="0002 - REPUESTOS", modulo="MOSTRADOR", nro_doc="M-1"),
        _fila(tipo="0003 - OTROS", modulo="MOSTRADOR", nro_doc="O-1", cantidad=4),
    ]

    carga, sesion = await _dry_run(monkeypatch, filas)  # default nuevo

    staged = sesion.added_of_type(CargaFilaStaging)
    assert not any(f.payload.get("solo_detalle") for f in staged)
    assert ventas.agregar_unidades(staged) == {
        (SUCURSAL_ID, REFERENCIA_ID, 2026, 9, "MOSTRADOR"): Decimal("14"),
    }
    assert carga.filas_validas == 2
    assert "filas_solo_detalle" not in carga.log
