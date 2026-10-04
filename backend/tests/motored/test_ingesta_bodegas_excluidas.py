"""
`bodegas_excluidas` (GRUPO_OPERACION): bodegas que no son tiendas (99999
BODEGA MOTORED, PYM01 SOACHA MT ELEC PRODUCTO TERMINADO). Las filas de
VENTAS e INVENTARIO de esas bodegas se ignoran sin `carga_error`, sin
staging y sin tocar `venta_detalle` / `inventario_detalle`; se cuentan en
`carga.log["filas_bodega_excluida"]`. Una bodega que NO esta en la lista y
no resuelve sigue dando SUCURSAL_NO_ENCONTRADA.
"""
import io
import uuid
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros_claves as pc
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import inventario, orquestador, ventas
from app.motored.services.ingesta import resolucion
from app.motored.services.ingesta.resolucion import CacheResolucion

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()
SUCURSAL_ID = uuid.uuid4()
REFERENCIA_ID = uuid.uuid4()
EXCLUIDAS = frozenset({"99999", "PYM01"})
SERIAL_2026_09_15 = 46280
CLAVE = pc.CLAVE_BODEGAS_EXCLUIDAS

_MAPA_VENTAS = {n: i for i, n in enumerate(ventas.COLUMNAS_ESPERADAS)}
_MAPA_INVENTARIO = {n: i for i, n in enumerate(inventario.COLUMNAS_ESPERADAS)}


def _cache():
    return CacheResolucion(
        sucursal_por_texto={"CALI NORTE": SUCURSAL_ID, "BA061": SUCURSAL_ID},
        referencia_por_codigo={"REF1": (REFERENCIA_ID, PROVEEDOR_ID)},
    )


def _fila_venta(bodega="BA061", desc="CALI NORTE", tipo="REPUESTOS",
                cantidad=10, doc="FV-1", estado="Aprobada"):
    return (estado, "MOSTRADOR", SERIAL_2026_09_15, cantidad, tipo, desc,
            bodega, "REF1", "Ana Pérez", 1000, 0, "Taller", doc)


def _fila_inventario(bodega="BA061", desc="CALI NORTE", existencia=10,
                     referencia="REF1"):
    return (referencia, bodega, desc, existencia, 1500)


def _procesar_venta(fila, excluidas=EXCLUIDAS, tipos=("REPUESTOS",)):
    return ventas.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=_MAPA_VENTAS,
        cache=_cache(), carga_id=CARGA_ID, proveedor_id=PROVEEDOR_ID,
        tipos_inventario_incluidos=list(tipos), bodegas_excluidas=excluidas)


def _procesar_inventario(fila, excluidas=EXCLUIDAS):
    return inventario.procesar_fila(
        fila, numero_fila=2, lote=1, mapa_columnas=_MAPA_INVENTARIO,
        cache=_cache(), carga_id=CARGA_ID, proveedor_id=PROVEEDOR_ID,
        bodegas_excluidas=excluidas)


# --- registro ---------------------------------------------------------------


def test_la_clave_esta_en_operacion_global_y_fuera_del_snapshot():
    espec = pc.REGISTRO[CLAVE]
    assert espec.default == ["99999", "PYM01"]
    assert espec.grupo == pc.GRUPO_OPERACION
    assert espec.ambito == pc.AMBITO_GLOBAL
    assert pc.es_snapshotted(CLAVE) is False
    assert CLAVE not in pc.claves_motor()
    assert pc.ficha(espec)["seccion"] == "cargas"


@pytest.mark.parametrize("valor", [
    ["99999"], ["99999", "PYM01"], ["BA066"],
])
def test_acepta_listas_de_codigos_normalizados_y_unicos(valor):
    pc.validar_escritura(CLAVE, valor)


@pytest.mark.parametrize("valor", [
    [], ["pym01"], [" PYM01"], ["PYM01 "], [""], ["  "], ["99999", "99999"],
    ["A", 5], "99999", None, {"a": 1},
])
def test_rechaza_vacios_sin_normalizar_repetidos_o_de_otro_tipo(valor):
    with pytest.raises(pc.ErrorParametro):
        pc.validar_escritura(CLAVE, valor)


def test_no_admite_sucursal_en_una_clave_global():
    with pytest.raises(pc.ErrorParametro):
        pc.validar_escritura(CLAVE, ["99999"], sucursal_id=uuid.uuid4())


# --- normalizacion ----------------------------------------------------------


@pytest.mark.parametrize("crudo,esperado", [
    ("99999", "99999"), (" pym01 ", "PYM01"), (99999, "99999"),
    (99999.0, "99999"), (None, ""), ("   ", ""),
])
def test_normalizar_codigo_bodega(crudo, esperado):
    assert resolucion.normalizar_codigo_bodega(crudo) == esperado


def test_un_codigo_vacio_nunca_esta_excluido():
    assert resolucion.es_bodega_excluida(None, EXCLUIDAS) is False
    assert resolucion.es_bodega_excluida("", frozenset({""})) is False


# --- VENTAS: procesador -----------------------------------------------------


@pytest.mark.parametrize("bodega", ["99999", "PYM01", " pym01 ", 99999.0])
def test_venta_de_bodega_excluida_no_genera_staging_ni_error(bodega):
    resultado = _procesar_venta(_fila_venta(bodega=bodega, desc="OTRA"))

    assert resultado is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_venta_excluida_de_un_tipo_solo_detalle_tampoco_va_a_detalle():
    # "MOTOCICLETA" no cuenta en venta_mensual pero si en venta_detalle
    # cuando la bodega resuelve: de una bodega excluida no va a ninguna.
    fila = _fila_venta(bodega="99999", desc="CALI NORTE", tipo="MOTOCICLETA")

    assert _procesar_venta(fila) is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_venta_excluida_aunque_la_bodega_si_resuelva_a_una_tienda():
    cache = CacheResolucion(
        sucursal_por_texto={"99999": SUCURSAL_ID},
        referencia_por_codigo={"REF1": (REFERENCIA_ID, PROVEEDOR_ID)})
    resultado = ventas.procesar_fila(
        _fila_venta(bodega="99999"), numero_fila=2, lote=1,
        mapa_columnas=_MAPA_VENTAS, cache=cache, carga_id=CARGA_ID,
        proveedor_id=PROVEEDOR_ID, tipos_inventario_incluidos=["REPUESTOS"],
        bodegas_excluidas=EXCLUIDAS)

    assert resultado is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_venta_excluida_no_valida_fecha_ni_cantidad():
    fila = list(_fila_venta(bodega="PYM01"))
    fila[2] = "no es fecha"
    fila[3] = "no es numero"

    assert _procesar_venta(tuple(fila)) is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_venta_de_bodega_no_excluida_sin_resolver_sigue_dando_error():
    staging, errores = _procesar_venta(
        _fila_venta(bodega="ZZ999", desc="BODEGA RARA"))

    assert staging.sucursal_id is None
    assert [e.codigo_error for e in errores] == [
        errores_mod.CODIGO_SUCURSAL_NO_ENCONTRADA]


def test_venta_sin_lista_se_procesa_como_antes():
    staging, errores = _procesar_venta(
        _fila_venta(bodega="99999", desc="CALI NORTE"),
        excluidas=frozenset())

    assert errores == []
    assert staging.sucursal_id == SUCURSAL_ID


def test_venta_no_aprobada_de_bodega_excluida_se_descarta_como_siempre():
    resultado = _procesar_venta(
        _fila_venta(bodega="99999", estado="Anulada"))

    assert resultado == (None, [])
    assert resultado is not resolucion.MarcaFila.BODEGA_EXCLUIDA


# --- INVENTARIO: procesador -------------------------------------------------


@pytest.mark.parametrize("bodega", ["99999", "PYM01", "pym01", 99999.0])
def test_inventario_de_bodega_excluida_no_genera_staging_ni_error(bodega):
    resultado = _procesar_inventario(
        _fila_inventario(bodega=bodega, desc="PRODUCTO TERMINADO"))

    assert resultado is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_inventario_excluido_no_valida_la_existencia():
    resultado = _procesar_inventario(
        _fila_inventario(bodega="PYM01", existencia="#N/A"))

    assert resultado is resolucion.MarcaFila.BODEGA_EXCLUIDA


def test_inventario_de_bodega_no_excluida_sin_resolver_sigue_dando_error():
    staging, errores = _procesar_inventario(
        _fila_inventario(bodega="ZZ999", desc="BODEGA RARA"))

    assert staging.sucursal_id is None
    assert [e.codigo_error for e in errores] == [
        errores_mod.CODIGO_SUCURSAL_NO_ENCONTRADA]


def test_inventario_relleno_sin_referencia_no_cuenta_como_excluido():
    resultado = _procesar_inventario(
        _fila_inventario(bodega="99999", referencia=None))

    assert resultado == (None, [])
    assert resultado is not resolucion.MarcaFila.BODEGA_EXCLUIDA


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


def _carga(tipo, **extra):
    base = dict(
        id=uuid.uuid4(), tipo=tipo, nombre_archivo="a.xlsx",
        hash_sha256="a" * 64, ruta_objeto=f"{tipo}/x.xlsx", bytes=100,
        estado="PROCESANDO", filas_leidas=0, filas_validas=0,
        filas_rechazadas=0, lotes_staged=0, ultimo_lote_aplicado=0,
        subido_por=uuid.uuid4(), log=None)
    base.update(extra)
    return CargaArchivo(**base)


def _cola(extra):
    """cache (4) + proveedor + lo que lee cada tipo, en su orden."""
    return [
        [(SUCURSAL_ID, "CALI NORTE", None)], [], [],
        [("REF1", PROVEEDOR_ID, REFERENCIA_ID)], [PROVEEDOR_ID],
    ] + extra


def _fila_param(valor):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=CLAVE, valor=valor, sucursal_id=None,
        vigente_desde=date(2026, 1, 1))


async def _dry_run_ventas(monkeypatch, filas, bodegas=None):
    carga = _carga("VENTAS", periodo_desde=date(2026, 9, 1),
                   periodo_hasta=date(2026, 9, 30))
    contenido = _xlsx(ventas.COLUMNAS_ESPERADAS, filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    # tipos_inventario_incluidos, bodegas_excluidas, periodo_tolerancia_pct
    cola = _cola([[], [] if bodegas is None else [bodegas], []])
    session = FakeAsyncSession(execute_queue=cola + [[]])
    await orquestador._dry_run(session, carga)
    return carga, session


async def _dry_run_inventario(monkeypatch, filas, bodegas=None):
    carga = _carga("INVENTARIO", periodo_desde=date(2026, 9, 15),
                   periodo_hasta=date(2026, 9, 15))
    contenido = _xlsx(inventario.COLUMNAS_ESPERADAS, filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    cola = _cola([[] if bodegas is None else [bodegas]])
    session = FakeAsyncSession(execute_queue=cola)
    await orquestador._dry_run(session, carga)
    return carga, session


def _documentos(session):
    return sorted(
        f.payload["nro_documento"]
        for f in session.added_of_type(CargaFilaStaging))


@pytest.fixture(autouse=True)
def _sin_memoria():
    orquestador._memoria_bodegas_excluidas.clear()
    yield
    orquestador._memoria_bodegas_excluidas.clear()


async def test_dry_run_ventas_ignora_las_excluidas_y_las_cuenta(monkeypatch):
    normales = [_fila_venta(doc=f"FV-{i}") for i in range(3)]
    mezcla = normales + [
        _fila_venta(bodega="99999", desc="BODEGA MOTORED", doc="FV-8"),
        _fila_venta(bodega="PYM01", desc="SOACHA MT ELEC PRODUCTO TERMINADO",
                    tipo="MOTOCICLETA", doc="FV-9"),
    ]

    carga, session = await _dry_run_ventas(monkeypatch, mezcla)

    assert carga.estado == "VALIDADO"
    assert session.added_of_type(CargaError) == []
    assert len(session.added_of_type(CargaFilaStaging)) == 3
    assert carga.log["filas_bodega_excluida"] == 2
    assert carga.log["filas_con_error"] == 0
    assert carga.filas_leidas == 5
    assert carga.filas_validas == 3


async def test_dry_run_ventas_sin_excluidas_no_escribe_el_contador(
        monkeypatch):
    carga, _ = await _dry_run_ventas(monkeypatch, [_fila_venta()])

    assert "filas_bodega_excluida" not in carga.log


async def test_mezcla_de_ventas_agrega_igual_que_solo_las_normales(
        monkeypatch):
    normales = [_fila_venta(doc=f"FV-{i}", cantidad=i + 1) for i in range(4)]
    mezcla = normales + [
        _fila_venta(bodega="99999", desc="BODEGA MOTORED", cantidad=500),
        _fila_venta(bodega="PYM01", desc="PRODUCTO TERMINADO", cantidad=70),
    ]

    _, solo = await _dry_run_ventas(monkeypatch, normales)
    _, junto = await _dry_run_ventas(monkeypatch, mezcla)

    agregado_solo = ventas.agregar_unidades(
        solo.added_of_type(CargaFilaStaging))
    agregado_junto = ventas.agregar_unidades(
        junto.added_of_type(CargaFilaStaging))
    assert agregado_junto == agregado_solo
    assert sum(agregado_junto.values()) == Decimal("10")
    assert _documentos(junto) == _documentos(solo)


async def test_dry_run_ventas_usa_la_lista_guardada(monkeypatch):
    filas = [_fila_venta(),
             _fila_venta(bodega="BA061", desc="CALI NORTE", doc="FV-2")]

    carga, session = await _dry_run_ventas(
        monkeypatch, filas, bodegas=_fila_param(["BA061"]))

    assert carga.log["filas_bodega_excluida"] == 2
    assert session.added_of_type(CargaFilaStaging) == []


async def test_dry_run_ventas_con_lista_guardada_ya_no_excluye_el_default(
        monkeypatch):
    filas = [_fila_venta(bodega="99999", desc="BODEGA MOTORED")]

    carga, session = await _dry_run_ventas(
        monkeypatch, filas, bodegas=_fila_param(["BA066"]))

    assert "filas_bodega_excluida" not in carga.log
    errores = session.added_of_type(CargaError)
    assert [e.codigo_error for e in errores] == [
        errores_mod.CODIGO_SUCURSAL_NO_ENCONTRADA]


async def test_dry_run_ventas_una_bodega_no_listada_sigue_dando_error(
        monkeypatch):
    filas = [_fila_venta(), _fila_venta(bodega="ZZ999", desc="RARA",
                                        doc="FV-2")]

    carga, session = await _dry_run_ventas(monkeypatch, filas)

    errores = session.added_of_type(CargaError)
    assert [e.codigo_error for e in errores] == [
        errores_mod.CODIGO_SUCURSAL_NO_ENCONTRADA]
    assert carga.log["filas_con_error"] == 1
    assert "filas_bodega_excluida" not in carga.log


async def test_dry_run_inventario_ignora_las_excluidas_y_las_cuenta(
        monkeypatch):
    filas = [
        _fila_inventario(),
        _fila_inventario(bodega="99999", desc="BODEGA MOTORED"),
        _fila_inventario(bodega="PYM01", desc="PRODUCTO TERMINADO",
                         existencia=300),
    ]

    carga, session = await _dry_run_inventario(monkeypatch, filas)

    assert carga.estado == "VALIDADO"
    assert session.added_of_type(CargaError) == []
    assert len(session.added_of_type(CargaFilaStaging)) == 1
    assert carga.log["filas_bodega_excluida"] == 2


async def test_mezcla_de_inventario_consolida_igual_que_solo_las_normales(
        monkeypatch):
    normales = [_fila_inventario(existencia=e) for e in (4, 6)]
    mezcla = normales + [
        _fila_inventario(bodega="99999", desc="BODEGA MOTORED",
                         existencia=999),
        _fila_inventario(bodega="PYM01", desc="PRODUCTO TERMINADO",
                         existencia=77),
    ]

    _, solo = await _dry_run_inventario(monkeypatch, normales)
    _, junto = await _dry_run_inventario(monkeypatch, mezcla)

    consolidado_solo = inventario.consolidar_existencias(
        solo.added_of_type(CargaFilaStaging))
    consolidado_junto = inventario.consolidar_existencias(
        junto.added_of_type(CargaFilaStaging))
    assert consolidado_junto == consolidado_solo
    assert consolidado_junto == {(SUCURSAL_ID, REFERENCIA_ID): Decimal("10")}


async def test_dry_run_inventario_bodega_no_listada_sigue_dando_error(
        monkeypatch):
    filas = [_fila_inventario(), _fila_inventario(bodega="ZZ999",
                                                  desc="RARA")]

    carga, session = await _dry_run_inventario(monkeypatch, filas)

    errores = session.added_of_type(CargaError)
    assert [e.codigo_error for e in errores] == [
        errores_mod.CODIGO_SUCURSAL_NO_ENCONTRADA]
    assert "filas_bodega_excluida" not in carga.log


async def test_la_lectura_falla_y_se_usa_el_default_del_registro():
    class SesionRota:
        async def execute(self, *_a, **_k):
            raise RuntimeError("base caida")

    excluidas = await orquestador._leer_bodegas_excluidas(SesionRota())

    assert excluidas == EXCLUIDAS


# --- la marca es explicita --------------------------------------------------


def _contar(resultados):
    estado = orquestador._EstadoLoteDryRun()
    it = iter(resultados)
    estado.procesar_fila = lambda fila, numero, lote: next(it)
    session = FakeAsyncSession()
    orquestador._procesar_filas_del_lote(
        estado, [("x",)] * len(resultados), 1, session)
    return estado


@pytest.mark.parametrize("silencioso", [(None, ()), (None, [])])
def test_un_descarte_silencioso_no_cuenta_como_bodega_excluida(silencioso):
    estado = _contar([silencioso])

    assert estado.filas_bodega_excluida == 0
    assert estado.filas_leidas == 1


def test_solo_la_marca_explicita_cuenta_como_bodega_excluida():
    marca = resolucion.MarcaFila.BODEGA_EXCLUIDA

    estado = _contar([marca, (None, ()), marca])

    assert estado.filas_bodega_excluida == 2
    assert estado.filas_validas == 0
    assert estado.filas_rechazadas == 0
    assert estado.filas_con_error == 0
