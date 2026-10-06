"""
Motored: "no data at this date" declarations against a real Postgres
(odd/tasks/motored-cargas-sin-datos.md, T1). Opt-in with
`MOTORED_TEST_PG_URL` pointing at a database migrated with
`alembic -c alembic_motored.ini upgrade head`; every test rolls back.

End to end: a BACKORDER declaration at D satisfies the real preflight, and
the real corrida reads zero backorder for every store, never falling back
to an older backorder carga.
"""
import datetime
import os
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.corridas import servicio as sv
from app.motored.services.ingesta import sin_datos

from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2026, 9, 21)
DECLARADA = datetime.date(2026, 9, 20)
VIEJA = datetime.date(2026, 9, 18)
UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 9, 20, 15, tzinfo=UTC)


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(
        motor, expire_on_commit=False, autoflush=False)
    async with fabrica() as db:
        yield db
        await db.rollback()
    await motor.dispose()


async def _guardar(db, *objetos):
    db.add_all(objetos)
    await db.flush()


def _carga(tipo, desde=None, hasta=None, aplicado=None, log=None):
    return CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado="APLICADO",
        nombre_archivo="f.xlsx", hash_sha256="h" * 64, ruta_objeto="r",
        bytes=1, periodo_desde=desde, periodo_hasta=hasta,
        aplicado_en=aplicado, log=log)


def _sucursal(nombre):
    return Sucursal(
        id=uuid.uuid4(), nombre=f"{nombre} {uuid.uuid4().hex[:6]}",
        sic=f"SIC-{uuid.uuid4().hex[:6]}", codigo_co=codigo_co_unico(),
        dias_empaque=3, dias_transito=2)


def _ventas(sucursal, ref, carga):
    return [
        VentaMensual(
            id=uuid.uuid4(), sucursal_id=sucursal.id, referencia_id=ref.id,
            anio=2026, mes=mes, origen="MOSTRADOR", unidades=Decimal(10),
            carga_id=carga.id)
        for mes in range(3, 9)
    ]


def _backorder(sucursal, ref, fecha, carga):
    return BackorderLinea(
        id=uuid.uuid4(), fecha_corte=fecha, sucursal_id=sucursal.id,
        referencia_id=ref.id, numero_pedido=f"P-{uuid.uuid4().hex[:6]}",
        estado="BACKORDER", cantidad_pendiente=Decimal(40),
        carga_id=carga.id)


async def _maestros(db):
    hmcl = Proveedor(
        id=uuid.uuid4(), codigo=f"HMCL-{uuid.uuid4().hex[:6]}",
        nombre="HMCL", es_principal=True, dias_empaque_default=4,
        dias_transito_default=5, dias_seguridad_default=Decimal("3"))
    uno, dos = _sucursal("UNO"), _sucursal("DOS")
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Compras", role=MotoredRole.COMPRAS,
        email=f"c-{uuid.uuid4().hex[:6]}@x.co", hashed_password="x")
    await _guardar(db, hmcl, uno, dos, usuario)
    ref = Referencia(
        id=uuid.uuid4(), codigo=f"94109-{uuid.uuid4().hex[:6]}",
        proveedor_id=hmcl.id, unidad_empaque=1,
        precio_normal=Decimal("460.75"))
    await _guardar(db, ref)
    return SimpleNamespace(uno=uno, dos=dos, usuario=usuario, ref=ref)


async def _sembrar(db):
    """Every carga the preflight needs except the BACKORDER one, plus an
    older backorder with rows that the corrida must NOT fall back to."""
    m = await _maestros(db)
    instante = datetime.datetime(2026, 9, 19, 15, tzinfo=UTC)
    ventas = _carga(
        "VENTAS", datetime.date(2026, 3, 1), datetime.date(2026, 9, 14),
        log={"fecha_max_detectada": "2026-09-14"})
    inventario = _carga("INVENTARIO", datetime.date(2026, 9, 19))
    vieja = _carga("BACKORDER", VIEJA, VIEJA)
    await _guardar(
        db, ventas, inventario, vieja,
        _carga("FACTURAS_PEDIDOS", aplicado=instante),
        _carga("INGRESOS_FACTURAS", aplicado=instante),
        _carga("DEMANDA_PERDIDA"))
    await _guardar(
        db,
        *_ventas(m.uno, m.ref, ventas), *_ventas(m.dos, m.ref, ventas),
        InventarioSnapshot(
            id=uuid.uuid4(), fecha_corte=datetime.date(2026, 9, 19),
            sucursal_id=m.uno.id, referencia_id=m.ref.id,
            existencias=Decimal(5), carga_id=inventario.id),
        _backorder(m.uno, m.ref, VIEJA, vieja),
        _backorder(m.dos, m.ref, VIEJA, vieja))
    m.vieja = vieja
    return m


async def _declarar(db, tipo, fecha, usuario):
    carga = await sin_datos.declarar_sin_datos(
        db, tipo, fecha, usuario.id, ahora=AHORA)
    await db.flush()
    return carga


async def _correr(db, datos):
    corrida = await sv.crear_corrida(
        db, fecha_corte=CORTE, hoy=CORTE,
        sucursal_ids=[datos.uno.id, datos.dos.id])
    estado = await sv.calcular_corrida(db, corrida.id)
    lineas = (await db.execute(
        select(CorridaLinea.sucursal_id, CorridaLinea.backorder)
        .where(CorridaLinea.corrida_id == corrida.id))).all()
    assert estado == "BORRADOR"
    assert {fila.sucursal_id for fila in lineas} == {
        datos.uno.id, datos.dos.id}
    return corrida, lineas


async def test_without_a_declaration_the_older_backorder_is_read(sesion):
    """Control: the seed really carries backorder, so the zero below is
    the declaration's doing."""
    datos = await _sembrar(sesion)

    _, lineas = await _correr(sesion, datos)

    assert all(fila.backorder == 40 for fila in lineas)


async def test_a_backorder_declaration_runs_with_zero_backorder(sesion):
    datos = await _sembrar(sesion)
    declarada = await _declarar(
        sesion, "BACKORDER", DECLARADA, datos.usuario)

    corrida, lineas = await _correr(sesion, datos)

    antiguedad = corrida.seleccion_datos["antiguedad"]["backorder"]
    assert antiguedad["carga_id"] == str(declarada.id)
    assert antiguedad["fecha_usada"] == DECLARADA.isoformat()
    assert all(fila.backorder == 0 for fila in lineas)


async def test_live_backorder_rows_at_the_date_block_the_declaration(
        sesion):
    datos = await _sembrar(sesion)

    with pytest.raises(sin_datos.DeclaracionEnConflicto):
        await _declarar(sesion, "BACKORDER", VIEJA, datos.usuario)

    datos.vieja.estado = "ANULADO"
    await sesion.flush()
    declarada = await _declarar(sesion, "BACKORDER", VIEJA, datos.usuario)
    assert declarada.estado == "APLICADO"


async def test_a_second_live_declaration_for_the_same_date_conflicts(
        sesion):
    datos = await _maestros(sesion)
    primera = await _declarar(
        sesion, "INGRESOS_FACTURAS", DECLARADA, datos.usuario)

    with pytest.raises(sin_datos.DeclaracionEnConflicto):
        await _declarar(
            sesion, "INGRESOS_FACTURAS", DECLARADA, datos.usuario)

    primera.estado = "ANULADO"
    await sesion.flush()
    await _declarar(sesion, "INGRESOS_FACTURAS", DECLARADA, datos.usuario)
