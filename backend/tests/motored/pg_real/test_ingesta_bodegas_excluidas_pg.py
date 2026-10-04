"""
`bodegas_excluidas` contra un Postgres real (opt-in): un archivo mixto
(filas de las bodegas 99999 / PYM01 mas filas normales) recorre el dry-run y
`Aplicar` reales y deja EXACTAMENTE lo mismo que el archivo con solo las filas
normales: mismas filas de `venta_mensual` / `inventario_snapshot`, ningun
`carga_error`, nada de las excluidas en `venta_detalle` /
`inventario_detalle`, y el conteo en `carga.log`.

Corre sólo con `MOTORED_TEST_PG_URL`; cada test se revierte al final.
"""
import datetime
import io
import os
import uuid
from decimal import Decimal

import openpyxl
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.ingesta import inventario, orquestador, ventas

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2099, 6, 30)
SERIAL_2026_09_15 = 46280
EXCLUIDAS = (("99999", "BODEGA MOTORED"),
             ("PYM01", "SOACHA MT ELEC PRODUCTO TERMINADO"))


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
    orquestador._memoria_bodegas_excluidas.clear()
    yield
    orquestador._memoria_bodegas_excluidas.clear()


async def _mundo(db):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    tienda = Sucursal(
        id=uuid.uuid4(), nombre=f"TIENDA {uuid.uuid4().hex[:6]}", sic="SIC-1")
    db.add_all([proveedor, tienda])
    await db.flush()
    referencia = Referencia(
        id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:6]}",
        proveedor_id=proveedor.id, unidad_empaque=1,
        precio_normal=Decimal("100"))
    db.add(referencia)
    await db.flush()
    return tienda, referencia


def _xlsx(encabezado, filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(encabezado))
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


async def _cargar(db, monkeypatch, tipo, encabezado, filas, desde, hasta):
    """Sube, valida (`_dry_run`) y aplica (`ejecutar_aplicar`) un archivo."""
    contenido = _xlsx(encabezado, filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo=tipo, origen="EXCEL", estado="PROCESANDO",
        nombre_archivo="a.xlsx", hash_sha256="h" * 64, ruta_objeto="r",
        bytes=len(contenido), periodo_desde=desde, periodo_hasta=hasta)
    db.add(carga)
    await db.flush()
    await orquestador._dry_run(db, carga)
    await db.flush()
    assert carga.estado == "VALIDADO", carga.log
    await orquestador.ejecutar_aplicar(db, carga)
    await db.flush()
    return carga


async def _errores(db, carga):
    return (await db.execute(
        select(CargaError).where(CargaError.carga_id == carga.id)
    )).scalars().all()


def _fila_venta(tienda, referencia, bodega, desc, cantidad, doc):
    return ("Aprobada", "MOSTRADOR", SERIAL_2026_09_15, cantidad,
            "REPUESTOS", desc, bodega, referencia.codigo, "Ana Pérez", 1000,
            0, "Taller", doc)


async def _ventas(db, monkeypatch, tienda, referencia, con_excluidas):
    filas = [
        _fila_venta(tienda, referencia, "BA061", tienda.nombre, 4, "FV-1"),
        _fila_venta(tienda, referencia, "BA061", tienda.nombre, 6, "FV-2"),
    ]
    if con_excluidas:
        filas += [
            _fila_venta(tienda, referencia, codigo, desc, 500, f"FX-{codigo}")
            for codigo, desc in EXCLUIDAS]
    carga = await _cargar(
        db, monkeypatch, "VENTAS", ventas.COLUMNAS_ESPERADAS, filas,
        datetime.date(2026, 9, 1), datetime.date(2026, 9, 30))
    mensual = (await db.execute(
        select(VentaMensual).where(VentaMensual.sucursal_id == tienda.id)
    )).scalars().all()
    detalle = (await db.execute(
        select(VentaDetalle).where(VentaDetalle.sucursal_id == tienda.id)
    )).scalars().all()
    return carga, mensual, detalle


async def test_un_archivo_mixto_de_ventas_deja_lo_mismo_que_las_normales(
        sesion, monkeypatch):
    tienda, referencia = await _mundo(sesion)

    _, base, base_detalle = await _ventas(
        sesion, monkeypatch, tienda, referencia, con_excluidas=False)
    esperado = {(m.referencia_id, m.anio, m.mes, m.origen, m.unidades)
                for m in base}
    esperado_docs = sorted(d.nro_documento for d in base_detalle)

    carga, mixto, mixto_detalle = await _ventas(
        sesion, monkeypatch, tienda, referencia, con_excluidas=True)

    assert esperado == {(referencia.id, 2026, 9, "MOSTRADOR", Decimal("10"))}
    assert {(m.referencia_id, m.anio, m.mes, m.origen, m.unidades)
            for m in mixto} == esperado
    assert sorted(d.nro_documento for d in mixto_detalle) == esperado_docs
    assert await _errores(sesion, carga) == []
    assert carga.log["filas_bodega_excluida"] == 2
    assert carga.log["filas_con_error"] == 0


async def _inventario(db, monkeypatch, tienda, referencia, con_excluidas):
    filas = [(referencia.codigo, "BA061", tienda.nombre, 4, 1500),
             (referencia.codigo, "BA066", tienda.nombre, 6, 1500)]
    if con_excluidas:
        filas += [(referencia.codigo, codigo, desc, 900, 10)
                  for codigo, desc in EXCLUIDAS]
    carga = await _cargar(
        db, monkeypatch, "INVENTARIO", inventario.COLUMNAS_ESPERADAS, filas,
        CORTE, CORTE)
    snapshot = (await db.execute(
        select(InventarioSnapshot).where(
            InventarioSnapshot.carga_id == carga.id)
    )).scalars().all()
    detalle = (await db.execute(
        select(InventarioDetalle).where(
            InventarioDetalle.carga_id == carga.id)
    )).scalars().all()
    return carga, snapshot, detalle


async def test_un_archivo_mixto_de_inventario_deja_lo_mismo_que_las_normales(
        sesion, monkeypatch):
    tienda, referencia = await _mundo(sesion)

    _, base, base_detalle = await _inventario(
        sesion, monkeypatch, tienda, referencia, con_excluidas=False)
    esperado = {(s.referencia_id, s.existencias) for s in base}

    carga, mixto, mixto_detalle = await _inventario(
        sesion, monkeypatch, tienda, referencia, con_excluidas=True)

    assert esperado == {(referencia.id, Decimal("10"))}
    assert {(s.referencia_id, s.existencias) for s in mixto} == esperado
    assert sorted(d.bodega for d in mixto_detalle) == ["BA061", "BA066"]
    assert sorted(d.bodega for d in base_detalle) == ["BA061", "BA066"]
    assert await _errores(sesion, carga) == []
    assert carga.log["filas_bodega_excluida"] == 2
