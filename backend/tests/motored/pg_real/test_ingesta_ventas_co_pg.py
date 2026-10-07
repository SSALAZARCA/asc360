"""
VENTAS by C.O. against a real Postgres (opt-in): a small file with a
cross row (bodega of store A, C.O. of store B), a blank-C.O. row and an
unknown C.O. runs the real dry-run and `Aplicar`. The cross row lands in
store B's `venta_mensual` / `venta_detalle`; the blank row falls back to
the bodega (store A); the unknown C.O. is a `CO_NO_ENCONTRADO` row error.

Runs only with `MOTORED_TEST_PG_URL`; each test is rolled back.
"""
import datetime
import io
import os
import random
import string
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
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.ingesta import orquestador, ventas

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


def _codigo_co_libre(usados):
    while True:
        codigo = random.choice(string.ascii_uppercase) + (
            f"{random.randint(0, 99):02d}")
        if codigo not in usados:
            return codigo


async def _mundo(db):
    usados = set((await db.execute(
        select(Sucursal.codigo_co).where(Sucursal.codigo_co.isnot(None))
    )).scalars().all())
    co_a = _codigo_co_libre(usados)
    co_b = _codigo_co_libre(usados | {co_a})
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    tienda_a = Sucursal(id=uuid.uuid4(), codigo_co=co_a,
                        nombre=f"TIENDA A {uuid.uuid4().hex[:6]}")
    tienda_b = Sucursal(id=uuid.uuid4(), codigo_co=co_b,
                        nombre=f"TIENDA B {uuid.uuid4().hex[:6]}")
    db.add_all([proveedor, tienda_a, tienda_b])
    await db.flush()
    bodega = Bodega(id=uuid.uuid4(), codigo=f"BX{uuid.uuid4().hex[:5]}",
                    sucursal_id=tienda_a.id)
    referencia = Referencia(
        id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:6]}",
        proveedor_id=proveedor.id, unidad_empaque=1,
        precio_normal=Decimal("100"), linea_comercial="REPUESTOS")
    db.add_all([bodega, referencia])
    await db.flush()
    return tienda_a, tienda_b, bodega, referencia


def _xlsx(encabezado, filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(encabezado))
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _fila(bodega, referencia, cantidad, doc, co):
    return ("Aprobada", "MOSTRADOR", SERIAL_2026_09_15, cantidad,
            "REPUESTOS", "SIN NOMBRE", bodega.codigo, referencia.codigo,
            "Ana Pérez", 1000, 0, "Taller", doc, co)


async def _cargar(db, monkeypatch, filas):
    contenido = _xlsx(ventas.COLUMNAS_ESPERADAS + ("C.O.",), filas)
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


async def _unidades(db, sucursal):
    filas = (await db.execute(
        select(VentaMensual).where(VentaMensual.sucursal_id == sucursal.id)
    )).scalars().all()
    return sum((m.unidades for m in filas), Decimal("0"))


async def _documentos(db, sucursal):
    filas = (await db.execute(
        select(VentaDetalle).where(VentaDetalle.sucursal_id == sucursal.id)
    )).scalars().all()
    return sorted(d.nro_documento for d in filas)


async def test_una_fila_cruzada_queda_en_la_sucursal_de_su_co(
        sesion, monkeypatch):
    tienda_a, tienda_b, bodega, referencia = await _mundo(sesion)
    co_con_espacio = f"{tienda_b.codigo_co.lower()} "
    filas = [
        _fila(bodega, referencia, 4, "FV-CRUZ", co_con_espacio),
        _fila(bodega, referencia, 6, "FV-VACIO", None),
        _fila(bodega, referencia, 9, "FV-MR", "MR "),
    ]

    carga = await _cargar(sesion, monkeypatch, filas)

    assert await _unidades(sesion, tienda_b) == Decimal("4")
    assert await _unidades(sesion, tienda_a) == Decimal("6")
    assert await _documentos(sesion, tienda_b) == ["FV-CRUZ"]
    assert await _documentos(sesion, tienda_a) == ["FV-VACIO"]
    errores = (await sesion.execute(
        select(CargaError).where(CargaError.carga_id == carga.id)
    )).scalars().all()
    assert [(e.codigo_error, e.valor) for e in errores] == [
        (ventas.CODIGO_CO_NO_ENCONTRADO, "MR")]
    assert carga.log["filas_co_vacio"] == 1
    assert carga.log["filas_con_error"] == 1
