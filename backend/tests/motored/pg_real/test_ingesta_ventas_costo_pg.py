"""
VENTAS "Costo promedio total" against a real Postgres (opt-in): the real
dry-run stages the cost and `Aplicar` stores it on `venta_detalle.costo`
(included and solo_detalle rows, negatives kept, blank/unparsable -> NULL
without a row error); an old 13-column file stores NULL and an unchanged log.

Runs only with `MOTORED_TEST_PG_URL`; each test is rolled back.
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

from app.motored.models.bodega import Bodega
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services.ingesta import orquestador, ventas
from tests.motored.pg_real.test_ingesta_ventas_co_pg import _codigo_co_libre

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

SERIAL_2026_09_15 = 46280


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
    usados = set((await db.execute(
        select(Sucursal.codigo_co).where(Sucursal.codigo_co.isnot(None))
    )).scalars().all())
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    tienda = Sucursal(id=uuid.uuid4(), codigo_co=_codigo_co_libre(usados),
                      nombre=f"TIENDA {uuid.uuid4().hex[:6]}")
    db.add_all([proveedor, tienda])
    await db.flush()
    bodega = Bodega(id=uuid.uuid4(), codigo=f"BX{uuid.uuid4().hex[:5]}",
                    sucursal_id=tienda.id)
    referencia = Referencia(
        id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:6]}",
        proveedor_id=proveedor.id, unidad_empaque=1,
        precio_normal=Decimal("100"), linea_comercial="REPUESTOS")
    db.add_all([bodega, referencia])
    await db.flush()
    return tienda, bodega, referencia


def _xlsx(encabezado, filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(encabezado))
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _fila(bodega, referencia, cantidad, doc, costo=None, con_costo=True,
          tipo="REPUESTOS"):
    base = ("Aprobada", "MOSTRADOR", SERIAL_2026_09_15, cantidad, tipo,
            "SIN NOMBRE", bodega.codigo, referencia.codigo,
            "Ana Pérez", 1000, 0, "Taller", doc)
    return base + ((costo,) if con_costo else ())


async def _cargar(db, monkeypatch, encabezado, filas):
    contenido = _xlsx(encabezado, filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="PROCESANDO",
        nombre_archivo="a.xlsx", hash_sha256="h" * 64, ruta_objeto="r",
        bytes=len(contenido), periodo_desde=datetime.date(2026, 9, 1),
        periodo_hasta=datetime.date(2026, 9, 30))
    db.add(carga)
    await db.flush()
    await orquestador._dry_run(db, carga)
    await db.flush()
    assert carga.estado == "VALIDADO", carga.log
    await orquestador.ejecutar_aplicar(db, carga)
    await db.flush()
    return carga


async def _costos(db, tienda):
    filas = (await db.execute(
        select(VentaDetalle).where(VentaDetalle.sucursal_id == tienda.id)
    )).scalars().all()
    return {d.nro_documento: d.costo for d in filas}


async def test_apply_guarda_el_costo_y_deja_null_lo_vacio_o_invalido(
        sesion, monkeypatch):
    tienda, bodega, referencia = await _mundo(sesion)
    filas = [
        _fila(bodega, referencia, 2, "FV-OK", "14.697,50"),
        _fila(bodega, referencia, -1, "FV-NEG", -5000),
        _fila(bodega, referencia, 3, "FV-CERO", 0),
        _fila(bodega, referencia, 4, "FV-VACIO", None),
        _fila(bodega, referencia, 5, "FV-MALO", "basura"),
        _fila(bodega, referencia, 1, "FV-MOTO", 99000.5, tipo="MOTOCICLETA"),
    ]

    carga = await _cargar(
        sesion, monkeypatch, ventas.COLUMNAS_ESPERADAS + (ventas.COLUMNA_COSTO,),
        filas)

    assert await _costos(sesion, tienda) == {
        "FV-OK": Decimal("14697.50"), "FV-NEG": Decimal("-5000.00"),
        "FV-CERO": Decimal("0.00"), "FV-VACIO": None, "FV-MALO": None,
        "FV-MOTO": Decimal("99000.50")}
    assert carga.log["filas_costo_invalido"] == 1
    errores = (await sesion.execute(
        select(CargaError).where(CargaError.carga_id == carga.id)
    )).scalars().all()
    assert errores == []


async def test_archivo_viejo_de_13_columnas_guarda_costo_null(
        sesion, monkeypatch):
    tienda, bodega, referencia = await _mundo(sesion)
    filas = [_fila(bodega, referencia, 2, "FV-1", con_costo=False)]

    carga = await _cargar(
        sesion, monkeypatch, ventas.COLUMNAS_ESPERADAS, filas)

    assert await _costos(sesion, tienda) == {"FV-1": None}
    assert "filas_costo_invalido" not in carga.log
