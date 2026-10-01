"""
INVENTARIO per-bodega detail (`inventario_detalle`) contra un Postgres real
(opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transacción que se revierte al final (los
`commit()` del código bajo prueba se degradan a `flush()`).

Cubre lo que los dobles no pueden: que `Aplicar` escribe snapshot y detalle
desde las mismas filas, una fila por bodega con su costo; que re-subir
reemplaza por (fecha_corte, sucursal); que anular NO borra el detalle; que
una fila con costo en blanco igual llega al snapshot; y que la purga de
retención borra detalle y snapshot de los cortes viejos juntos.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.api import cargas as cargas_api
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.models.sucursal import Sucursal
from app.motored.services import retencion
from app.motored.services.ingesta import orquestador

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CORTE = datetime.date(2099, 6, 30)
CORTE_VIEJO = datetime.date(2098, 1, 15)


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        # El codigo bajo prueba hace commit: se degrada a flush para que el
        # rollback de la fixture siga aislando el test.
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


def _carga(corte=CORTE, estado="VALIDADO"):
    return CargaArchivo(
        id=uuid.uuid4(), tipo="INVENTARIO", origen="EXCEL", estado=estado,
        nombre_archivo="i.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1,
        periodo_desde=corte, periodo_hasta=corte, lotes_staged=1)


def _staging(carga, sucursal, referencia, bodega, existencia, costo, fila=1):
    return CargaFilaStaging(
        carga_id=carga.id, fila=fila, lote=1, sucursal_id=sucursal.id,
        referencia_id=referencia.id,
        payload={"existencia": existencia, "bodega": bodega, "costo": costo})


async def _mundo(db):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:6]}", nombre="P",
        es_principal=True, dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=Decimal("3"))
    sucursales = [
        Sucursal(id=uuid.uuid4(), nombre=f"S{i} {uuid.uuid4().hex[:6]}", sic=f"SIC-{i}")
        for i in range(2)]
    db.add_all([proveedor, *sucursales])
    await db.flush()
    referencias = [
        Referencia(
            id=uuid.uuid4(), codigo=f"R-{i}", proveedor_id=proveedor.id,
            unidad_empaque=1, precio_normal=Decimal("100"))
        for i in range(2)]
    db.add_all(referencias)
    await db.flush()
    return sucursales, referencias


async def _aplicar(db, carga, filas):
    db.add_all([carga, *filas])
    await db.flush()
    await orquestador.ejecutar_aplicar(db, carga)
    await db.flush()


async def _detalle(db, **filtros):
    consulta = select(InventarioDetalle)
    for campo, valor in filtros.items():
        consulta = consulta.where(getattr(InventarioDetalle, campo) == valor)
    return (await db.execute(consulta)).scalars().all()


async def _snapshot(db):
    return (await db.execute(select(InventarioSnapshot))).scalars().all()


async def test_aplicar_escribe_una_fila_de_detalle_por_bodega_con_su_costo(sesion):
    (a, _), (r1, _) = await _mundo(sesion)
    carga = _carga()
    filas = [
        _staging(carga, a, r1, "BA061", "12", "1500.50", fila=1),
        _staging(carga, a, r1, "BA066", "30", "-20", fila=2),
        _staging(carga, a, r1, "BA070", "5", None, fila=3),
    ]

    await _aplicar(sesion, carga, filas)

    detalle = {d.bodega: d for d in await _detalle(sesion, sucursal_id=a.id)}
    assert set(detalle) == {"BA061", "BA066", "BA070"}
    assert detalle["BA061"].costo_unitario == Decimal("1500.50")
    assert detalle["BA061"].existencia == Decimal("12")
    assert detalle["BA066"].costo_unitario == Decimal("-20")  # tal cual; el lector lo excluye
    assert detalle["BA070"].costo_unitario is None
    assert all(d.carga_id == carga.id and d.fecha_corte == CORTE for d in detalle.values())
    snapshot = await _snapshot(sesion)
    assert [(s.existencias, s.fecha_corte) for s in snapshot] == [(Decimal("47"), CORTE)]


async def test_costo_en_blanco_igual_llega_al_snapshot_con_su_existencia(sesion):
    (a, _), (r1, r2) = await _mundo(sesion)
    carga = _carga()
    filas = [
        _staging(carga, a, r1, "BA061", "9", None, fila=1),
        _staging(carga, a, r2, "BA061", "4", "1000", fila=2),
    ]

    await _aplicar(sesion, carga, filas)

    por_ref = {s.referencia_id: s.existencias for s in await _snapshot(sesion)}
    assert por_ref == {r1.id: Decimal("9"), r2.id: Decimal("4")}


async def test_resubir_reemplaza_solo_el_corte_y_sucursal_presentes(sesion):
    (a, b), (r1, _) = await _mundo(sesion)
    c1, c2 = _carga(), _carga()
    await _aplicar(sesion, c1, [
        _staging(c1, a, r1, "BA061", "10", "100", fila=1),
        _staging(c1, a, r1, "BA066", "10", "100", fila=2),
        _staging(c1, b, r1, "BB001", "10", "100", fila=3),
    ])
    c_viejo = _carga(CORTE_VIEJO)
    await _aplicar(sesion, c_viejo, [_staging(c_viejo, a, r1, "BA061", "1", "1", fila=1)])

    await _aplicar(sesion, c2, [_staging(c2, a, r1, "BA061", "99", "200", fila=1)])

    por_bodega = {(d.sucursal_id, d.bodega, d.fecha_corte): d.carga_id
                  for d in await _detalle(sesion)}
    assert por_bodega == {
        (a.id, "BA061", CORTE): c2.id,         # reemplazo de (CORTE, a): BA066 desaparece
        (b.id, "BB001", CORTE): c1.id,         # otra sucursal, mismo corte: intacta
        (a.id, "BA061", CORTE_VIEJO): c_viejo.id,  # otro corte: intacto
    }


async def test_anular_la_carga_no_borra_el_detalle(sesion):
    (a, _), (r1, _) = await _mundo(sesion)
    carga = _carga()
    await _aplicar(sesion, carga, [_staging(carga, a, r1, "BA061", "10", "100")])
    assert carga.estado == "APLICADO"

    await cargas_api.anular_carga(carga.id, db=sesion, user=None)

    assert carga.estado == "ANULADO"
    filas = (await sesion.execute(
        select(func.count()).select_from(InventarioDetalle)
        .where(InventarioDetalle.carga_id == carga.id)
    )).scalar_one()
    assert filas == 1


async def test_la_purga_de_retencion_borra_detalle_y_snapshot_de_los_cortes_viejos(sesion):
    (a, _), (r1, _) = await _mundo(sesion)
    viejo, nuevo = _carga(CORTE_VIEJO), _carga(CORTE)
    await _aplicar(sesion, viejo, [
        _staging(viejo, a, r1, "BA061", "1", "10", fila=1),
        _staging(viejo, a, r1, "BA066", "2", "10", fila=2),
    ])
    await _aplicar(sesion, nuevo, [_staging(nuevo, a, r1, "BA061", "5", "10")])

    ejecucion = await retencion.ejecutar_purga_inventario(sesion, chunk_size=1)

    assert [d.fecha_corte for d in await _detalle(sesion)] == [CORTE]
    assert [s.fecha_corte for s in await _snapshot(sesion)] == [CORTE]
    assert ejecucion.tabla == retencion.TABLA_INVENTARIO_SNAPSHOT
    assert ejecucion.filas_eliminadas == 1
    ledger = {
        e.tabla: e.filas_eliminadas
        for e in (await sesion.execute(select(RetencionEjecucion))).scalars().all()
    }
    assert ledger[retencion.TABLA_INVENTARIO_DETALLE] == 2
    assert ledger[retencion.TABLA_INVENTARIO_SNAPSHOT] == 1
