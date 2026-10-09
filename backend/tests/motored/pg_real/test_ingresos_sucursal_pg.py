"""
INGRESOS_FACTURAS C.O. -> `sucursal_id` against a real Postgres (opt-in).

A file with the optional "C.O." column runs the real dry-run and
`Aplicar`: a known C.O. (any case, with spaces) fills the row's
`sucursal_id`; an unknown or empty C.O. leaves it NULL with no row error.
A second load of the same document with another C.O. updates the store
(ON CONFLICT DO UPDATE).

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

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.proveedor import Proveedor
from app.motored.models.sucursal import Sucursal
from app.motored.services.ingesta import ingresos, orquestador

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


def _codigo_co_libre(usados):
    while True:
        codigo = random.choice(string.ascii_uppercase) + (
            f"{random.randint(0, 99):02d}")
        if codigo not in usados:
            return codigo


async def _tiendas(db):
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
    return tienda_a, tienda_b


def _xlsx(filas):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(ingresos.COLUMNAS_ESPERADAS) + ["C.O."])
    for fila in filas:
        hoja.append(list(fila))
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _fila(numero_rh, co):
    return ("16-1", datetime.date(2026, 9, 15), "Facturado",
            f"RH{numero_rh}", 1000, co)


async def _cargar(db, monkeypatch, filas):
    contenido = _xlsx(filas)
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="INGRESOS_FACTURAS", origen="EXCEL",
        estado="PROCESANDO", nombre_archivo="i.xlsx",
        hash_sha256=uuid.uuid4().hex * 2, ruta_objeto="r",
        bytes=len(contenido))
    db.add(carga)
    await db.flush()
    await orquestador._dry_run(db, carga)
    await db.flush()
    assert carga.estado == "VALIDADO", carga.log
    await orquestador.ejecutar_aplicar(db, carga)
    await db.flush()
    return carga


async def _sucursal_de(db, numero_rh):
    return (await db.execute(
        select(IngresoFactura.sucursal_id).where(
            IngresoFactura.prefijo_rh == "RH",
            IngresoFactura.numero_rh == numero_rh)
    )).scalar_one()


async def test_el_co_llena_la_sucursal_y_el_desconocido_queda_nulo(
        sesion, monkeypatch):
    tienda_a, _ = await _tiendas(sesion)
    base = random.randint(10_000_000, 90_000_000)
    filas = [
        _fila(base, f" {tienda_a.codigo_co.lower()} "),
        _fila(base + 1, "Q!"),
        _fila(base + 2, None),
    ]

    carga = await _cargar(sesion, monkeypatch, filas)

    assert await _sucursal_de(sesion, base) == tienda_a.id
    assert await _sucursal_de(sesion, base + 1) is None
    assert await _sucursal_de(sesion, base + 2) is None
    errores = (await sesion.execute(
        select(CargaError).where(CargaError.carga_id == carga.id)
    )).scalars().all()
    assert errores == []


async def test_recargar_el_documento_actualiza_la_sucursal(
        sesion, monkeypatch):
    tienda_a, tienda_b = await _tiendas(sesion)
    numero = random.randint(10_000_000, 90_000_000)

    await _cargar(sesion, monkeypatch, [_fila(numero, tienda_a.codigo_co)])
    await _cargar(sesion, monkeypatch, [_fila(numero, tienda_b.codigo_co)])

    assert await _sucursal_de(sesion, numero) == tienda_b.id
