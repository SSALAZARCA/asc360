"""
Motored Pedidos F3 "Motor", S5b (sdd/motored-pedidos-motor, ADR-6): el
cargador contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transacción que se revierte al final.
"""
import datetime
import os
import time
import uuid
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.corridas import cargador as cg
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import MesEnCurso, ParametrosMotor

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2026, 9, 21)
CORTE_INVENTARIO = datetime.date(2026, 9, 19)
CORTE_BACKORDER = datetime.date(2026, 9, 18)
PONDERADO = MesEnCurso("PONDERADO", 14, 30, Fraction(3))


def _dia(mes, dia, anio=2026):
    return datetime.date(anio, mes, dia)


def _carga(tipo, estado="APLICADO", origen="EXCEL"):
    archivo = {}
    if origen == "EXCEL":
        archivo = dict(
            nombre_archivo="f.xlsx", hash_sha256="h" * 64,
            ruta_objeto="r", bytes=1)
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen=origen, estado=estado, **archivo)


def _referencia(codigo, proveedor, **campos):
    return Referencia(
        id=uuid.uuid4(), codigo=codigo, proveedor_id=proveedor.id,
        unidad_empaque=1, precio_normal=Decimal("100"), **campos)


def _venta(sucursal, ref, mes, origen, unidades, carga, anio=2026):
    return VentaMensual(
        id=uuid.uuid4(), sucursal_id=sucursal.id, referencia_id=ref.id,
        anio=anio, mes=mes, origen=origen, unidades=Decimal(unidades),
        carga_id=carga.id)


def _perdida(sucursal, ref, fecha, cantidad, carga, origen="EXCEL"):
    return DemandaPerdida(
        id=uuid.uuid4(), fecha=fecha, sucursal_id=sucursal.id,
        referencia_id=ref.id, cantidad_solicitada=Decimal(cantidad),
        origen=origen, carga_id=carga.id)


def _inventario(fecha, sucursal, ref, existencias, carga):
    return InventarioSnapshot(
        id=uuid.uuid4(), fecha_corte=fecha, sucursal_id=sucursal.id,
        referencia_id=ref.id, existencias=Decimal(existencias),
        carga_id=carga.id)


def _backorder(fecha, sucursal, ref, pedido, cantidad, carga):
    return BackorderLinea(
        id=uuid.uuid4(), fecha_corte=fecha, sucursal_id=sucursal.id,
        referencia_id=ref.id, numero_pedido=pedido, estado="BACKORDER",
        cantidad_pendiente=Decimal(cantidad), carga_id=carga.id)


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _guardar(db, *objetos):
    db.add_all(objetos)
    await db.flush()


async def _sembrar(db):
    """Un escenario chico con todas las trampas del cargador."""
    hmcl = Proveedor(
        id=uuid.uuid4(), codigo=f"HMCL-{uuid.uuid4().hex[:6]}",
        nombre="HMCL", es_principal=True, dias_empaque_default=4,
        dias_transito_default=5, dias_seguridad_default=Decimal("3"))
    otro = Proveedor(
        id=uuid.uuid4(), codigo=f"OTRO-{uuid.uuid4().hex[:6]}",
        nombre="Otro", es_principal=False)
    suc = Sucursal(
        id=uuid.uuid4(), nombre=f"S {uuid.uuid4().hex[:6]}  ", sic="SIC-1",
        dias_empaque=3, dias_transito=2)
    otra = Sucursal(
        id=uuid.uuid4(), nombre=f"T {uuid.uuid4().hex[:6]}", sic="SIC-2")
    await _guardar(db, hmcl, otro, suc, otra)
    a = _referencia("A-1", hmcl)
    b = _referencia("B-1", hmcl)
    d = _referencia("D-1", hmcl)
    x = _referencia("X-1", otro)
    await _guardar(db, a, b, d, x)
    c = _referencia("C-1", hmcl, activa=False, sustituida_por=b.id)
    await _guardar(db, c)
    cargas = SimpleNamespace(
        ventas=_carga("VENTAS"), ventas_anulada=_carga("VENTAS", "ANULADO"),
        inventario=_carga("INVENTARIO"),
        inventario_anulado=_carga("INVENTARIO", "ANULADO"),
        backorder=_carga("BACKORDER"),
        perdida=_carga("DEMANDA_PERDIDA"),
        perdida_anulada=_carga("DEMANDA_PERDIDA", "ANULADO"),
        perdida_bot=_carga("DEMANDA_PERDIDA", "ANULADO", origen="BOT"))
    await _guardar(db, *vars(cargas).values())
    await _sembrar_movimientos(db, SimpleNamespace(
        suc=suc, otra=otra, a=a, b=b, c=c, d=d, x=x), cargas)
    return SimpleNamespace(
        hmcl=hmcl, suc=suc, otra=otra, a=a, b=b, c=c, d=d, cargas=cargas)


async def _sembrar_movimientos(db, e, c):
    await _guardar(
        db,
        _venta(e.suc, e.a, 3, "MOSTRADOR", 10, c.ventas),
        _venta(e.suc, e.a, 3, "TALLER", 2, c.ventas),
        _venta(e.suc, e.a, 8, "MOSTRADOR", 5, c.ventas),
        _venta(e.suc, e.a, 8, "TALLER", 1, c.ventas),
        _venta(e.suc, e.a, 9, "MOSTRADOR", 7, c.ventas),
        _venta(e.suc, e.a, 9, "TALLER", 3, c.ventas),
        _venta(e.suc, e.a, 2, "MOSTRADOR", 1000, c.ventas),
        _venta(e.suc, e.a, 10, "MOSTRADOR", 1000, c.ventas),
        _venta(e.otra, e.a, 3, "MOSTRADOR", 500, c.ventas),
        _venta(e.suc, e.x, 3, "MOSTRADOR", 50, c.ventas),
        _venta(e.suc, e.b, 3, "MOSTRADOR", 99, c.ventas_anulada),
        _venta(e.suc, e.d, 7, "MOSTRADOR", 3, c.ventas),
        _perdida(e.suc, e.a, _dia(3, 5), 4, c.perdida),
        _perdida(e.suc, e.a, _dia(3, 20), 1, c.perdida_bot, "BOT"),
        _perdida(e.suc, e.a, _dia(4, 10), 9, c.perdida_anulada),
        _perdida(e.suc, e.a, _dia(5, 10), 2, c.perdida_bot, "BOT"),
        _perdida(e.suc, e.a, _dia(2, 28), 100, c.perdida),
        _perdida(e.suc, e.a, _dia(9, 10), 6, c.perdida),
        _perdida(e.suc, e.a, _dia(9, 25), 8, c.perdida),
        _inventario(CORTE_INVENTARIO, e.suc, e.a, 27, c.inventario),
        _inventario(CORTE_INVENTARIO, e.otra, e.a, 4, c.inventario),
        _inventario(CORTE_INVENTARIO, e.suc, e.d, 2, c.inventario),
        _inventario(CORTE_INVENTARIO, e.suc, e.x, 8, c.inventario),
        _inventario(CORTE_INVENTARIO, e.suc, e.c, 11, c.inventario),
        _inventario(CORTE_INVENTARIO, e.suc, e.b, 40, c.inventario_anulado),
        _inventario(_dia(9, 12), e.suc, e.a, 99, c.inventario),
        _inventario(_dia(9, 28), e.suc, e.a, 55, c.inventario),
        _backorder(CORTE_BACKORDER, e.suc, e.a, "P1", 6, c.backorder),
        _backorder(CORTE_BACKORDER, e.suc, e.a, "P2", 4, c.backorder),
        _backorder(_dia(9, 11), e.suc, e.a, "P3", 77, c.backorder),
    )


def _contexto(datos, **cambios):
    base = dict(
        proveedor=cg.FilaProveedor(datos.hmcl.id, 4, 5, Decimal("3")),
        fecha_corte=CORTE, corte_inventario=CORTE_INVENTARIO,
        corte_backorder=CORTE_BACKORDER,
        transito={datos.suc.id: {datos.a.id: Decimal(70)}},
        dias_entre_pedidos={datos.suc.id: 30})
    return cg.ContextoCarga(**{**base, **cambios})


def _por_codigo(cargadas):
    return {e.codigo: e for e in cargadas.entradas}


def _dec(*valores):
    return tuple(Decimal(v) for v in valores)


async def test_the_five_queries_assemble_the_inputs_on_a_real_postgres(sesion):
    datos = await _sembrar(sesion)

    cargadas = await cg.cargar_entradas(
        sesion, datos.suc.id, _contexto(datos))

    assert sorted(_por_codigo(cargadas)) == ["A-1", "D-1"]
    a = _por_codigo(cargadas)["A-1"]
    assert a.ventas == _dec(12, 0, 0, 0, 0, 6)
    assert a.perdidas == _dec(5, 0, 2, 0, 0, 0)
    assert (a.inventario, a.transito, a.backorder) == _dec(27, 70, 10)
    assert (a.venta_m0, a.perdida_m0) == (None, None)
    assert (a.precio, a.unidad_empaque) == (Decimal("100.00"), 1)
    d = _por_codigo(cargadas)["D-1"]
    assert d.ventas == _dec(0, 0, 0, 0, 3, 0) and d.inventario == 2


async def test_m0_and_its_lost_demand_load_only_up_to_the_corte(sesion):
    datos = await _sembrar(sesion)

    cargadas = await cg.cargar_entradas(
        sesion, datos.suc.id, _contexto(datos, mes_en_curso=PONDERADO))

    a = _por_codigo(cargadas)["A-1"]
    assert a.ventas == _dec(12, 0, 0, 0, 0, 6)
    assert (a.venta_m0, a.perdida_m0) == _dec(10, 6)
    assert _por_codigo(cargadas)["D-1"].venta_m0 == 0


async def test_the_annulled_filter_spares_only_the_bot_lost_demand(sesion):
    datos = await _sembrar(sesion)

    cargadas = await cg.cargar_entradas(
        sesion, datos.suc.id, _contexto(datos))

    a = _por_codigo(cargadas)["A-1"]
    assert a.perdidas[1] == 0 and a.perdidas[2] == 2
    assert "B-1" not in _por_codigo(cargadas)


async def test_consolidation_loads_the_old_reference_and_its_final(sesion):
    datos = await _sembrar(sesion)
    maestro = await cg.cargar_maestro(sesion, datos.hmcl.id)
    contexto = _contexto(
        datos, consolidar=True, resoluciones=resolver_cadenas(maestro))

    cargadas = await cg.cargar_entradas(sesion, datos.suc.id, contexto)

    por_codigo = _por_codigo(cargadas)
    assert sorted(por_codigo) == ["A-1", "B-1", "C-1", "D-1"]
    assert por_codigo["C-1"].inventario == 11
    assert por_codigo["B-1"].ventas == _dec(0, 0, 0, 0, 0, 0)
    assert por_codigo["B-1"].inventario == 0
    calculo = calcular_sucursal(
        cargadas.entradas, (await cg.cargar_sucursal(
            sesion, datos.suc.id, contexto)).atributos,
        ParametrosMotor(consolidar_sustituidas=True), contexto.resoluciones)
    assert [x.entrada.codigo for x in calculo.excluidas] == ["C-1"]


async def test_the_principal_supplier_master_and_sucursal_rows(sesion):
    datos = await _sembrar(sesion)
    proveedor = await cg.cargar_proveedor_principal(sesion)

    assert proveedor.id == datos.hmcl.id
    maestro = await cg.cargar_maestro(sesion, datos.hmcl.id)
    assert maestro[datos.c.id].sustituida_por == datos.b.id
    assert datos.a.id not in maestro
    datos_suc = await cg.cargar_sucursal(
        sesion, datos.suc.id, _contexto(datos))
    assert datos_suc.atributos.nombre == datos.suc.nombre.strip()
    assert (datos_suc.atributos.dias_empaque,
            datos_suc.atributos.dias_transito) == _dec(3, 2)


async def test_cargar_sucursal_runs_six_queries_at_any_volume(sesion):
    datos = await _sembrar(sesion)
    await sesion.execute(text(
        "insert into referencia(id, codigo, proveedor_id, unidad_empaque,"
        " unidad_empaque_advertencia, activa) select gen_random_uuid(),"
        " 'V-' || n, :prov, 1, false, true"
        " from generate_series(1, 12000) as n"), {"prov": datos.hmcl.id})
    await sesion.execute(text(
        "insert into venta_mensual(id, sucursal_id, referencia_id, anio,"
        " mes, origen, unidades, es_mes_parcial, carga_id)"
        " select gen_random_uuid(), :suc, id, 2026, 5, 'MOSTRADOR', 3,"
        " false, :carga from referencia where codigo like 'V-%'"),
        {"suc": datos.suc.id, "carga": datos.cargas.ventas.id})
    sentencias = []
    motor = sesion.bind.sync_engine

    def contar(*args):
        sentencias.append(args[2])

    event.listen(motor, "before_cursor_execute", contar)
    inicio = time.monotonic()
    try:
        cargadas = await cg.cargar_sucursal(
            sesion, datos.suc.id, _contexto(datos))
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    duracion = time.monotonic() - inicio

    assert len(cargadas.entradas) == 12002
    assert len(sentencias) == 6
    assert duracion < 15
