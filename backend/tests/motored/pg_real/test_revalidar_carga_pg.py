"""
"Volver a validar" on real Postgres (opt-in, `MOTORED_TEST_PG_URL`).

A FACTURAS_PEDIDOS carga with an unknown code: the real dry-run leaves its
rows in error; "Crear referencia" (línea read from the real Configuración)
and a revalidation wipe the staging and the errors and process the same
file again, so every row enters. Ignored rows stay out, a second click is
refused, and an applied carga cannot be revalidated. Each test is rolled
back.
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.carga_resolucion import (
    AccionResolucion,
    ResolverAccionesRequest,
)
from app.motored.services.ingesta import facturas, orquestador
from app.motored.services.trabajos.runner import JobRunner

from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        deshacer = db.rollback
        monkeypatch.setattr(db, "commit", db.flush)
        monkeypatch.setattr(db, "rollback", db.flush)
        yield db
        await deshacer()
    await motor.dispose()


class _RunnerEnLaMismaSesion(JobRunner):
    """Runs the real dry-run inline on the test's session (the production
    handler opens its own session, which would not see the rolled-back
    test data)."""

    def __init__(self, db):
        self.db = db
        self.encoladas = 0

    async def enqueue(self, carga_id, tipo) -> None:
        self.encoladas += 1
        carga = await self.db.get(CargaArchivo, carga_id)
        await orquestador._dry_run(self.db, carga)
        await self.db.flush()


class _SinDespacho(JobRunner):
    """Leaves the carga queued (`PENDIENTE`), as the supervisor would
    before its next tick."""

    async def enqueue(self, carga_id, tipo) -> None:
        return None


def _xlsx(sic, codigos):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(facturas.COLUMNAS_ESPERADAS))
    for i, codigo in enumerate(codigos):
        hoja.append([sic, "TIENDA", None, f"RH{1000 + i}",
                     datetime.date(2026, 7, 15), codigo, 2,
                     Decimal("1000")])
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


async def _mundo(db, monkeypatch, nueva):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True)
    sic = uuid.uuid4().hex[:8]
    tienda = Sucursal(id=uuid.uuid4(), codigo_co=codigo_co_unico(),
                      nombre=f"TIENDA {uuid.uuid4().hex[:6]}", sic=sic)
    db.add_all([proveedor, tienda])
    await db.flush()
    conocida = Referencia(
        id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:8]}",
        proveedor_id=proveedor.id, unidad_empaque=1)
    db.add(conocida)
    await db.flush()
    contenido = _xlsx(sic, [nueva] * 3 + [conocida.codigo])
    monkeypatch.setattr(
        orquestador.storage, "descargar_archivo", lambda ruta: contenido)
    carga = CargaArchivo(
        id=uuid.uuid4(), tipo="FACTURAS_PEDIDOS", origen="EXCEL",
        estado="PROCESANDO", nombre_archivo="f.xlsx", hash_sha256="h" * 64,
        ruta_objeto="r", bytes=len(contenido))
    db.add(carga)
    await db.flush()
    await orquestador._dry_run(db, carga)
    await db.flush()
    return SimpleNamespace(proveedor=proveedor, carga=carga)


def _usuario():
    return SimpleNamespace(
        user_id=str(uuid.uuid4()), role="COMPRAS", sucursal_ids=[])


async def _contar(db, modelo, carga):
    return (await db.execute(select(func.count()).select_from(modelo).where(
        modelo.carga_id == carga.id))).scalar_one()


async def _resolver(db, carga, accion):
    return await cargas_api.resolver_errores(
        carga.id, ResolverAccionesRequest(acciones=[accion]),
        db=db, user=_usuario())


async def _revalidar(db, carga):
    runner = _RunnerEnLaMismaSesion(db)
    await cargas_api.revalidar_carga(
        carga.id, db=db, user=_usuario(), job_runner=runner)
    return runner


async def test_crear_la_referencia_y_revalidar_carga_todas_las_filas(
        sesion, monkeypatch):
    nueva = f"BTX-{uuid.uuid4().hex[:6]}"
    mundo = await _mundo(sesion, monkeypatch, nueva)
    carga = mundo.carga
    assert carga.estado == "VALIDADO"
    assert await _contar(sesion, CargaError, carga) == 3

    resultado = await _resolver(sesion, carga, AccionResolucion(
        codigo_error="REFERENCIA_NO_ENCONTRADA", valor=nueva,
        accion="crear_referencia", linea_comercial="repuestos"))
    assert resultado.acciones_aplicadas == 1
    creada = (await sesion.execute(select(Referencia).where(
        Referencia.codigo == nueva))).scalar_one()
    assert creada.proveedor_id == mundo.proveedor.id
    assert creada.linea_comercial.upper() == "REPUESTOS"

    runner = await _revalidar(sesion, carga)

    assert runner.encoladas == 1
    await sesion.refresh(carga)
    assert carga.estado == "VALIDADO"
    assert await _contar(sesion, CargaError, carga) == 0
    filas = (await sesion.execute(select(CargaFilaStaging).where(
        CargaFilaStaging.carga_id == carga.id))).scalars().all()
    assert len(filas) == 4
    assert all(f.referencia_id is not None for f in filas)
    assert carga.filas_validas == 4
    assert carga.log["filas_con_error"] == 0
    assert len(carga.log["revalidaciones"]) == 1


async def test_las_filas_ignoradas_quedan_fuera_y_el_doble_clic_es_409(
        sesion, monkeypatch):
    nueva = f"IGN-{uuid.uuid4().hex[:6]}"
    carga = (await _mundo(sesion, monkeypatch, nueva)).carga
    await _resolver(sesion, carga, AccionResolucion(
        codigo_error="REFERENCIA_NO_ENCONTRADA", valor=nueva,
        accion="ignorar"))

    await cargas_api.revalidar_carga(
        carga.id, db=sesion, user=_usuario(),
        job_runner=_SinDespacho())
    await sesion.refresh(carga)
    assert carga.estado == "PENDIENTE"
    assert await _contar(sesion, CargaError, carga) == 0
    assert await _contar(sesion, CargaFilaStaging, carga) == 0
    with pytest.raises(HTTPException) as exc:
        await _revalidar(sesion, carga)
    assert exc.value.status_code == 409

    await _RunnerEnLaMismaSesion(sesion).enqueue(carga.id, carga.tipo)
    await sesion.refresh(carga)
    assert carga.estado == "VALIDADO"
    assert await _contar(sesion, CargaError, carga) == 0
    assert await _contar(sesion, CargaFilaStaging, carga) == 1
    assert carga.log["filas_ignoradas"] == 3


async def test_una_carga_aplicada_no_se_revalida(sesion, monkeypatch):
    carga = (await _mundo(sesion, monkeypatch, "X-APL")).carga
    carga.estado = "APLICADO"
    await sesion.flush()

    with pytest.raises(HTTPException) as exc:
        await _revalidar(sesion, carga)

    assert exc.value.status_code == 409
    assert carga.estado == "APLICADO"
