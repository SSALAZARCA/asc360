"""
VENTAS take the line from the referencia master (real Postgres, opt-in).

End to end through the real dry-run, the report/assignment endpoints and the
real `Aplicar`:
- the ERP type denylist discards rows (counted, never a carga_error);
- a master line outside `tipos_inventario_incluidos` is `fuera_de_linea`;
- an empty master line is `sin_linea` and BLOCKS the apply (409, nothing is
  written) until a user assigns a line; "NO COMERCIAL" takes the ref out of
  the sales without blocking again;
- the consumers of `venta_mensual` (pedido demand, corrida preflight, KPI
  refresh) keep working.

Runs only with `MOTORED_TEST_PG_URL`; each test is rolled back.
"""
import datetime
import io
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api import cargas as cargas_api
from app.motored.models.bodega import Bodega
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual
from app.motored.schemas.ingesta import (
    AsignacionLineaItem,
    AsignarLineaRequest,
)
from app.motored.services import maestros
from app.motored.services.corridas import cargador, vigencia
from app.motored.services.ingesta import orquestador, ventas

from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

SERIAL_2026_09_15 = 46280
ENCABEZADO = list(ventas.COLUMNAS_ESPERADAS)


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


@pytest.fixture(autouse=True)
def _sin_memoria():
    for memoria in (orquestador._memoria_bodegas_excluidas,
                    orquestador._memoria_tipos_excluidos):
        memoria.clear()
    yield
    for memoria in (orquestador._memoria_bodegas_excluidas,
                    orquestador._memoria_tipos_excluidos):
        memoria.clear()


@pytest.fixture
def espias(monkeypatch):
    llamadas = {"refrescar": [], "sucio": 0}

    async def refrescar(session, claves):
        llamadas["refrescar"].append(set(claves))
        return False

    async def sucio(session):
        llamadas["sucio"] += 1
        return False

    monkeypatch.setattr(ventas.kpi_resumen, "refrescar_si_construido", refrescar)
    monkeypatch.setattr(maestros.kpi_resumen, "marcar_sucio_si_construido", sucio)
    return llamadas


def _ref(proveedor, linea, nombre):
    return Referencia(
        id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:8]}",
        proveedor_id=proveedor.id, unidad_empaque=1, nombre=nombre,
        precio_normal=Decimal("100"), linea_comercial=linea)


async def _mundo(db):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    tienda = Sucursal(id=uuid.uuid4(), codigo_co=codigo_co_unico(),
                      nombre=f"TIENDA {uuid.uuid4().hex[:6]}")
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"c-{uuid.uuid4().hex[:6]}@x.co", hashed_password="x")
    db.add_all([proveedor, tienda, usuario])
    await db.flush()
    bodega = Bodega(id=uuid.uuid4(), codigo=f"BX{uuid.uuid4().hex[:5]}",
                    sucursal_id=tienda.id)
    con_linea = _ref(proveedor, "Repuestos", "Con linea")
    sin_linea = _ref(proveedor, None, "Sin linea")
    sin_linea_2 = _ref(proveedor, "  ", "Sin linea dos")
    de_motos = _ref(proveedor, "MOTOS", "Motos")
    db.add_all([bodega, con_linea, sin_linea, sin_linea_2, de_motos])
    await db.flush()
    return SimpleNamespace(
        tienda=tienda, bodega=bodega, usuario=usuario,
        con_linea=con_linea, sin_linea=sin_linea, sin_linea_2=sin_linea_2,
        de_motos=de_motos)


def _xlsx(filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(ENCABEZADO)
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _fila(mundo, ref, cantidad, doc, tipo="REPUE", bruto=1000, modulo="MOSTRADOR"):
    return ("Aprobada", modulo, SERIAL_2026_09_15, cantidad, tipo,
            "SIN NOMBRE", mundo.bodega.codigo, ref.codigo, "Ana Pérez",
            bruto, 0, "Taller", doc)


async def _dry_run(db, monkeypatch, filas, log=None):
    contenido = _xlsx(filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="PROCESANDO",
        nombre_archivo="a.xlsx", hash_sha256="h" * 64, ruta_objeto="r",
        bytes=len(contenido), periodo_desde=datetime.date(2026, 9, 1),
        periodo_hasta=datetime.date(2026, 9, 30), log=log)
    db.add(carga)
    await db.flush()
    await orquestador._dry_run(db, carga)
    await db.flush()
    return carga


def _usuario(mundo):
    return SimpleNamespace(
        user_id=str(mundo.usuario.id), role="COMPRAS", sucursal_ids=[])


async def _asignar(db, mundo, carga, ref, linea):
    return await cargas_api.asignar_linea(
        carga.id, ref.id, AsignarLineaRequest(linea_comercial=linea),
        db=db, user=_usuario(mundo))


async def _informe(db, carga):
    return await cargas_api.listar_referencias_sin_linea(
        carga.id, db=db, user=SimpleNamespace(role="ADMIN", sucursal_ids=[]))


async def _aplicar(db, carga):
    await orquestador.ejecutar_aplicar(db, carga)
    await db.flush()


async def _tablas(db, mundo):
    mensual = {
        (m.referencia_id, m.origen): m.unidades for m in (await db.execute(
            select(VentaMensual).where(
                VentaMensual.sucursal_id == mundo.tienda.id))).scalars()}
    detalle = {
        d.nro_documento for d in (await db.execute(
            select(VentaDetalle).where(
                VentaDetalle.sucursal_id == mundo.tienda.id))).scalars()}
    return mensual, detalle


def _archivo_crudo(m):
    """Lo que el ERP entrega sin tocar: codigos de tipo, no lineas."""
    return [
        _fila(m, m.con_linea, 10, "OK-1", tipo="REPUE"),
        _fila(m, m.con_linea, 5, "OK-2", tipo="LUB19", modulo="TALLER"),
        _fila(m, m.sin_linea, 3, "SL-1", tipo="REPUE", bruto=3000),
        _fila(m, m.sin_linea, 2, "SL-2", tipo="REPUE", bruto=2000),
        _fila(m, m.sin_linea_2, 1, "SL-3", tipo="LUB19", bruto=9000),
        _fila(m, m.de_motos, 4, "MO-1", tipo="REPUE"),
        _fila(m, m.con_linea, 7, "EX-1", tipo="IM1901"),
        _fila(m, m.con_linea, 8, "EX-2", tipo="ST003"),
        _fila(m, m.con_linea, 9, "EX-3", tipo="im19xx "),
    ]


async def test_el_dry_run_descarta_por_codigo_cuenta_y_no_da_errores(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)

    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    assert carga.estado == "VALIDADO"
    assert carga.log["filas_tipo_excluido"] == 3
    assert carga.log["filas_fuera_de_linea"] == 1
    assert carga.log["filas_sin_linea"] == 3
    assert carga.filas_validas == 2
    errores = (await sesion.execute(
        select(CargaError).where(CargaError.carga_id == carga.id))).scalars().all()
    assert errores == []


async def test_el_informe_vivo_ordena_por_valor_y_ofrece_las_lineas(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    informe = await _informe(sesion, carga)

    sin = informe["sin_linea"]
    assert [r["referencia_id"] for r in sin] == [m.sin_linea_2.id, m.sin_linea.id]
    assert sin[1]["filas"] == 2 and sin[1]["unidades"] == 5.0
    assert sin[1]["valor"] == 5000.0 and sin[1]["nombre"] == "Sin linea"
    assert informe["fuera_de_linea"] == [{"linea": "MOTOS", "filas": 1}]
    assert informe["no_encontradas"] == []
    opciones = informe["opciones_linea"]
    assert {"valor": "LUBRICANTES", "etiqueta": "Lubricantes"} in opciones
    assert opciones[-1] == {
        "valor": "NO COMERCIAL", "etiqueta": "No es de repuestos (descartar)"}


async def test_aplicar_se_bloquea_con_referencias_sin_linea_y_no_escribe(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    with pytest.raises(orquestador.EstadoInvalidoParaAplicarError) as error:
        await _aplicar(sesion, carga)

    assert str(error.value) == (
        "Hay 2 referencias sin línea: asígnelas antes de aplicar.")
    assert carga.estado == "VALIDADO"
    assert await _tablas(sesion, m) == ({}, set())
    assert espias["refrescar"] == []


async def test_el_endpoint_de_aplicar_responde_409_con_el_mensaje(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    with pytest.raises(HTTPException) as error:
        await cargas_api.aplicar_carga(
            carga.id, db=sesion, user=_usuario(m))

    assert error.value.status_code == 409
    assert error.value.detail == (
        "Hay 2 referencias sin línea: asígnelas antes de aplicar.")


async def test_asignadas_las_lineas_el_apply_carga_venta_mensual_y_detalle(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))
    await _asignar(sesion, m, carga, m.sin_linea, "repuestos")
    informe = await _asignar(sesion, m, carga, m.sin_linea_2, "Lubricantes")
    assert informe["sin_linea"] == []
    assert espias["sucio"] == 2  # cada cambio de linea marca los KPI sucios

    await _aplicar(sesion, carga)

    assert carga.estado == "APLICADO"
    mensual, detalle = await _tablas(sesion, m)
    assert mensual == {
        (m.con_linea.id, "MOSTRADOR"): Decimal("10"),
        (m.con_linea.id, "TALLER"): Decimal("5"),
        (m.sin_linea.id, "MOSTRADOR"): Decimal("5"),
        (m.sin_linea_2.id, "MOSTRADOR"): Decimal("1"),
    }
    # El detalle sigue a la venta: ni la moto ni los tipos excluidos entran.
    assert detalle == {"OK-1", "OK-2", "SL-1", "SL-2", "SL-3"}
    assert len(espias["refrescar"]) == 1
    assert {k[0] for k in espias["refrescar"][0]} == {m.tienda.id}
    refs = {r.id: r.linea_comercial for r in (
        m.sin_linea, m.sin_linea_2)}
    assert refs == {m.sin_linea.id: "REPUESTOS",
                    m.sin_linea_2.id: "LUBRICANTES"}


async def test_no_comercial_saca_la_referencia_del_reparto_y_no_bloquea(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))
    await _asignar(sesion, m, carga, m.sin_linea, "no comercial")
    informe = await _asignar(sesion, m, carga, m.sin_linea_2, "NO COMERCIAL")

    assert informe["sin_linea"] == []
    assert {"linea": "NO COMERCIAL", "filas": 3} in informe["fuera_de_linea"]
    await _aplicar(sesion, carga)

    mensual, detalle = await _tablas(sesion, m)
    assert set(k[0] for k in mensual) == {m.con_linea.id}
    assert detalle == {"OK-1", "OK-2"}
    assert m.sin_linea.linea_comercial == "NO COMERCIAL"


async def test_la_asignacion_deja_asiento_en_el_log_de_la_carga(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    await _asignar(sesion, m, carga, m.sin_linea, "GPS")

    (asiento,) = carga.log["asignaciones_linea"]
    assert asiento["referencia_id"] == str(m.sin_linea.id)
    assert asiento["codigo"] == m.sin_linea.codigo
    assert asiento["linea"] == "GPS"
    assert asiento["usuario_id"] == str(m.usuario.id)
    assert asiento["en"]


async def test_el_put_rechaza_lo_que_no_es_de_la_lista_ni_una_linea_valida(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    with pytest.raises(HTTPException) as fuera_de_lista:
        await _asignar(sesion, m, carga, m.con_linea, "GPS")
    with pytest.raises(HTTPException) as invalida:
        await _asignar(sesion, m, carga, m.sin_linea, "MOTOS")

    assert fuera_de_lista.value.status_code == 409
    assert invalida.value.status_code == 422
    assert isinstance(invalida.value.detail, str)
    assert m.sin_linea.linea_comercial is None
    assert "asignaciones_linea" not in carga.log


async def test_el_put_masivo_es_todo_o_nada(sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))

    with pytest.raises(HTTPException) as error:
        await cargas_api.asignar_lineas(
            carga.id, [
                AsignacionLineaItem(
                    referencia_id=m.sin_linea.id, linea_comercial="GPS"),
                AsignacionLineaItem(
                    referencia_id=m.sin_linea_2.id, linea_comercial="XYZ")],
            db=sesion, user=_usuario(m))

    assert error.value.status_code == 422
    assert m.sin_linea.linea_comercial is None
    assert m.sin_linea_2.linea_comercial == "  "
    assert "asignaciones_linea" not in carga.log
    assert espias["sucio"] == 0

    informe = await cargas_api.asignar_lineas(
        carga.id, [
            AsignacionLineaItem(
                referencia_id=m.sin_linea.id, linea_comercial="GPS"),
            AsignacionLineaItem(
                referencia_id=m.sin_linea_2.id, linea_comercial="NO COMERCIAL")],
        db=sesion, user=_usuario(m))

    assert informe["sin_linea"] == []
    assert len(carga.log["asignaciones_linea"]) == 2


async def test_el_put_no_aplica_a_una_carga_aplicada(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "OK-1")])
    await _aplicar(sesion, carga)

    with pytest.raises(HTTPException) as error:
        await _asignar(sesion, m, carga, m.sin_linea, "GPS")

    assert error.value.status_code == 409


async def test_la_linea_se_evalua_contra_el_maestro_de_hoy_al_aplicar(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "OK-1"),
        _fila(m, m.de_motos, 4, "MO-1")])
    # Despues del dry-run el maestro cambia: la moto pasa a repuestos y la
    # otra referencia sale del reparto.
    m.de_motos.linea_comercial = "Repuestos"
    m.con_linea.linea_comercial = "MOTOS"
    await sesion.flush()

    await _aplicar(sesion, carga)

    mensual, detalle = await _tablas(sesion, m)
    assert mensual == {(m.de_motos.id, "MOSTRADOR"): Decimal("4")}
    assert detalle == {"MO-1"}


async def test_archivo_viejo_con_lineas_en_tipo_inventario_carga_como_antes(
        sesion, monkeypatch, espias):
    """Archivo armado a mano ("Tipo inventario" = nombre de linea): con las
    referencias ya con linea carga exactamente las mismas filas; las que no
    la tenian deben asignarse y entonces cargan igual."""
    m = await _mundo(sesion)
    filas = [
        _fila(m, m.con_linea, 10, "V-1", tipo="REPUESTOS"),
        _fila(m, m.con_linea, 5, "V-2", tipo="LUBRICANTES", modulo="TALLER"),
        _fila(m, m.sin_linea, 3, "V-3", tipo="REPUESTOS"),
    ]
    carga = await _dry_run(sesion, monkeypatch, filas)

    with pytest.raises(orquestador.EstadoInvalidoParaAplicarError):
        await _aplicar(sesion, carga)
    await _asignar(sesion, m, carga, m.sin_linea, "REPUESTOS")
    await _aplicar(sesion, carga)

    mensual, detalle = await _tablas(sesion, m)
    assert mensual == {
        (m.con_linea.id, "MOSTRADOR"): Decimal("10"),
        (m.con_linea.id, "TALLER"): Decimal("5"),
        (m.sin_linea.id, "MOSTRADOR"): Decimal("3"),
    }
    assert detalle == {"V-1", "V-2", "V-3"}


async def test_archivo_viejo_con_todas_sus_referencias_con_linea_carga_directo(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "V-1", tipo="REPUESTOS"),
        _fila(m, m.con_linea, 2, "V-2", tipo="REPUESTOS")])

    await _aplicar(sesion, carga)

    mensual, detalle = await _tablas(sesion, m)
    assert mensual == {(m.con_linea.id, "MOSTRADOR"): Decimal("12")}
    assert detalle == {"V-1", "V-2"}
    assert "filas_sin_linea" not in carga.log


async def test_los_consumidores_de_venta_mensual_ven_la_carga(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, _archivo_crudo(m))
    await _asignar(sesion, m, carga, m.sin_linea, "REPUESTOS")
    await _asignar(sesion, m, carga, m.sin_linea_2, "REPUESTOS")
    await _aplicar(sesion, carga)

    # Demanda del pedido: `_consulta_ventas` suma las unidades por referencia.
    hmcl = cargador.FilaProveedor(
        id=m.con_linea.proveedor_id, dias_empaque_default=4,
        dias_transito_default=5, dias_seguridad_default=Decimal("3"))
    ctx = cargador.ContextoCarga(
        proveedor=hmcl, fecha_corte=datetime.date(2026, 10, 5),
        corte_inventario=datetime.date(2026, 10, 4),
        corte_backorder=datetime.date(2026, 10, 4))
    filas = (await sesion.execute(
        cargador._consulta_ventas((m.tienda.id,), ctx))).all()
    por_ref = {f[0]: sum(v or 0 for v in f[1:]) for f in filas}
    assert por_ref[m.con_linea.id] == Decimal("15")
    assert por_ref[m.sin_linea.id] == Decimal("5")
    assert por_ref[m.sin_linea_2.id] == Decimal("1")
    assert m.de_motos.id not in por_ref

    # Preflight de la corrida: la carga aplicada cubre su mes.
    hechos = await vigencia.cargar_hechos(sesion, datetime.date(2026, 10, 5))
    vistas = [c for c in hechos.cargas if c.carga_id == carga.id]
    assert len(vistas) == 1
    assert vigencia._meses_sin_cubrir(
        vistas, [datetime.date(2026, 9, 1)]) == []


# --- venta_mensual is rebuilt for the months in the file (V3) ---------------


async def _segunda_tienda(db):
    tienda = Sucursal(id=uuid.uuid4(), codigo_co=codigo_co_unico(),
                      nombre=f"TIENDA OTRA {uuid.uuid4().hex[:6]}")
    db.add(tienda)
    await db.flush()
    bodega = Bodega(id=uuid.uuid4(), codigo=f"BY{uuid.uuid4().hex[:5]}",
                    sucursal_id=tienda.id)
    db.add(bodega)
    await db.flush()
    return tienda, bodega


def _fila_en(bodega, ref, cantidad, doc, serial=SERIAL_2026_09_15):
    return ("Aprobada", "MOSTRADOR", serial, cantidad, "REPUE",
            "SIN NOMBRE", bodega.codigo, ref.codigo, "Ana Pérez",
            1000, 0, "Taller", doc)


async def _mensual_de(db, tienda):
    return {
        (m.referencia_id, m.anio, m.mes, m.origen): m.unidades
        for m in (await db.execute(
            select(VentaMensual).where(
                VentaMensual.sucursal_id == tienda.id))).scalars()}


async def test_el_apply_reconstruye_venta_mensual_de_los_meses_del_archivo(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    otra, bodega_otra = await _segunda_tienda(sesion)
    otro = _ref(SimpleNamespace(id=m.con_linea.proveedor_id), "GPS", "Otro")
    sesion.add(otro)
    await sesion.flush()
    carga_a = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "A-1"),
        _fila(m, otro, 7, "A-2"),
        _fila_en(bodega_otra, m.con_linea, 3, "A-3")])
    await _aplicar(sesion, carga_a)
    # Un agosto de la misma tienda, de la misma carga, que B no toca.
    sesion.add(VentaMensual(
        id=uuid.uuid4(), sucursal_id=m.tienda.id, referencia_id=otro.id,
        anio=2026, mes=8, origen="MOSTRADOR", unidades=Decimal("99"),
        carga_id=carga_a.id))
    await sesion.flush()

    carga_b = await _dry_run(sesion, monkeypatch, [_fila(m, m.con_linea, 4, "B-1")])
    await _aplicar(sesion, carga_b)

    # La referencia que solo traia A ya no suma en septiembre (fantasma).
    assert await _mensual_de(sesion, m.tienda) == {
        (m.con_linea.id, 2026, 9, "MOSTRADOR"): Decimal("4"),
        (otro.id, 2026, 8, "MOSTRADOR"): Decimal("99"),
    }
    # Otra tienda: intacta.
    assert await _mensual_de(sesion, otra) == {
        (m.con_linea.id, 2026, 9, "MOSTRADOR"): Decimal("3")}


async def test_reaplicar_el_mismo_contenido_es_idempotente(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    filas = [_fila(m, m.con_linea, 10, "A-1"), _fila(m, m.con_linea, 2, "A-2")]
    primera = await _dry_run(sesion, monkeypatch, filas)
    await _aplicar(sesion, primera)
    antes = await _mensual_de(sesion, m.tienda)

    segunda = await _dry_run(sesion, monkeypatch, filas)
    await _aplicar(sesion, segunda)

    assert await _mensual_de(sesion, m.tienda) == antes
    assert antes == {(m.con_linea.id, 2026, 9, "MOSTRADOR"): Decimal("12")}


async def test_tras_la_purga_las_filas_de_la_tienda_y_mes_son_de_la_carga_vigente(
        sesion, monkeypatch, espias):
    """`anular_carga` no borra `venta_mensual`: los lectores unen con
    `carga_archivo` y excluyen las ANULADAS; tras la purga, las filas de la
    tienda y el mes pertenecen todas a la carga vigente."""
    m = await _mundo(sesion)
    otro = _ref(SimpleNamespace(id=m.con_linea.proveedor_id), "GPS", "Otro")
    sesion.add(otro)
    await sesion.flush()
    carga_a = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "A-1"), _fila(m, otro, 7, "A-2")])
    await _aplicar(sesion, carga_a)
    carga_b = await _dry_run(sesion, monkeypatch, [_fila(m, m.con_linea, 4, "B-1")])
    await _aplicar(sesion, carga_b)

    duenos = {
        row.carga_id for row in (await sesion.execute(
            select(VentaMensual).where(
                VentaMensual.sucursal_id == m.tienda.id))).scalars()}

    assert duenos == {carga_b.id}


# --- full-month replace for the network (V4) --------------------------------

REEMPLAZA = {"reemplaza_mes_completo": True}


async def _red_con_dos_tiendas(db, monkeypatch):
    """Carga A aplicada en dos tiendas (septiembre); devuelve lo necesario
    para una carga B que solo trae la primera."""
    m = await _mundo(db)
    otra, bodega_otra = await _segunda_tienda(db)
    carga_a = await _dry_run(db, monkeypatch, [
        _fila(m, m.con_linea, 10, "A-1"),
        _fila_en(bodega_otra, m.con_linea, 3, "A-2")])
    await _aplicar(db, carga_a)
    return m, otra, carga_a


async def test_con_el_flag_el_apply_vacia_las_tiendas_que_el_archivo_no_trae(
        sesion, monkeypatch, espias):
    m, otra, carga_a = await _red_con_dos_tiendas(sesion, monkeypatch)
    carga_b = await _dry_run(
        sesion, monkeypatch, [_fila(m, m.con_linea, 4, "B-1")], log=REEMPLAZA)
    assert carga_b.log["reemplaza_mes_completo"] is True  # survives the dry-run
    espias["refrescar"].clear()

    await _aplicar(sesion, carga_b)

    assert await _mensual_de(sesion, m.tienda) == {
        (m.con_linea.id, 2026, 9, "MOSTRADOR"): Decimal("4")}
    assert await _mensual_de(sesion, otra) == {}
    detalle_otra = (await sesion.execute(
        select(VentaDetalle).where(VentaDetalle.sucursal_id == otra.id))).all()
    assert detalle_otra == []
    # KPI refresh for the store of the file and for the purged one.
    refrescadas = set().union(*espias["refrescar"])
    assert refrescadas == {(m.tienda.id, 2026, 9), (otra.id, 2026, 9)}
    # The corrida preflight still counts the month as covered.
    hechos = await vigencia.cargar_hechos(sesion, datetime.date(2026, 10, 5))
    vistas = [c for c in hechos.cargas if c.carga_id == carga_b.id]
    assert vigencia._meses_sin_cubrir(vistas, [datetime.date(2026, 9, 1)]) == []


async def test_sin_el_flag_el_apply_no_toca_las_otras_tiendas(
        sesion, monkeypatch, espias):
    m, otra, carga_a = await _red_con_dos_tiendas(sesion, monkeypatch)
    carga_b = await _dry_run(sesion, monkeypatch, [_fila(m, m.con_linea, 4, "B-1")])

    await _aplicar(sesion, carga_b)

    assert await _mensual_de(sesion, otra) == {
        (m.con_linea.id, 2026, 9, "MOSTRADOR"): Decimal("3")}
    assert await cargas_api.obtener_vaciado_previsto(
        carga_b.id, db=sesion, user=_usuario(m)) == []


async def test_el_vaciado_previsto_lista_en_vivo_las_tiendas_ausentes(
        sesion, monkeypatch, espias):
    m, otra, carga_a = await _red_con_dos_tiendas(sesion, monkeypatch)
    carga_b = await _dry_run(
        sesion, monkeypatch, [_fila(m, m.con_linea, 4, "B-1")], log=REEMPLAZA)

    previsto = await cargas_api.obtener_vaciado_previsto(
        carga_b.id, db=sesion, user=_usuario(m))

    assert previsto == [{
        "sucursal_id": otra.id, "nombre": otra.nombre, "mes": "2026-09",
        "filas_actuales": 1}]
    # Live: once the other store is covered by the file it no longer shows up.
    carga_c = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 4, "C-1"),
        _fila_en(await _bodega_de(sesion, otra), m.con_linea, 1, "C-2")],
        log=REEMPLAZA)
    assert await cargas_api.obtener_vaciado_previsto(
        carga_c.id, db=sesion, user=_usuario(m)) == []


async def _bodega_de(db, tienda):
    return (await db.execute(
        select(Bodega).where(Bodega.sucursal_id == tienda.id))).scalars().first()


# --- the line rule follows `lineas_comerciales`, not the old codes (V5) -----


async def _guardar_parametro(db, clave, valor):
    from app.motored.models.parametro_metodologia import ParametroMetodologia

    db.add(ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, sucursal_id=None,
        vigente_desde=datetime.date(2026, 1, 1)))
    await db.flush()


async def test_tipos_inventario_incluidos_con_codigos_viejos_no_cambia_el_resultado(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    await _guardar_parametro(
        sesion, "tipos_inventario_incluidos",
        ["0002 - REPUESTOS", "IRPTOSYACC", "IVNLUBGR"])
    carga = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "OK-1"), _fila(m, m.de_motos, 4, "MO-1")])

    await _aplicar(sesion, carga)

    mensual, detalle = await _tablas(sesion, m)
    assert mensual == {(m.con_linea.id, "MOSTRADOR"): Decimal("10")}
    assert detalle == {"OK-1"}


async def test_las_lineas_que_cuentan_son_las_lineas_comerciales_vigentes(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    await _guardar_parametro(sesion, "lineas_comerciales", ["REPUESTOS", "MOTOS"])
    carga = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.con_linea, 10, "OK-1"), _fila(m, m.de_motos, 4, "MO-1")])

    await _aplicar(sesion, carga)

    mensual, detalle = await _tablas(sesion, m)
    assert {k[0] for k in mensual} == {m.con_linea.id, m.de_motos.id}
    assert detalle == {"OK-1", "MO-1"}


async def test_el_dry_run_marca_la_carga_si_ninguna_fila_queda_en_las_lineas(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)

    carga = await _dry_run(sesion, monkeypatch, [_fila(m, m.de_motos, 4, "MO-1")])

    assert carga.estado == "CON_ERRORES"
    errores = (await sesion.execute(
        select(CargaError).where(CargaError.carga_id == carga.id))).scalars().all()
    assert [(e.fila, e.codigo_error) for e in errores] == [(0, "E-CARGA-051")]


async def test_si_las_asignaciones_dejan_cero_filas_el_apply_responde_409(
        sesion, monkeypatch, espias):
    m = await _mundo(sesion)
    carga = await _dry_run(sesion, monkeypatch, [
        _fila(m, m.sin_linea, 3, "SL-1"), _fila(m, m.sin_linea_2, 2, "SL-2")])
    assert carga.estado == "VALIDADO"  # esperan asignacion, no estan perdidas
    await _asignar(sesion, m, carga, m.sin_linea, "NO COMERCIAL")
    await _asignar(sesion, m, carga, m.sin_linea_2, "NO COMERCIAL")

    with pytest.raises(HTTPException) as error:
        await cargas_api.aplicar_carga(carga.id, db=sesion, user=_usuario(m))

    assert error.value.status_code == 409
    assert error.value.detail == (
        "Ninguna fila quedó en las líneas incluidas: revise la configuración "
        "de líneas comerciales.")
    assert await _tablas(sesion, m) == ({}, set())
    assert carga.estado == "VALIDADO"
