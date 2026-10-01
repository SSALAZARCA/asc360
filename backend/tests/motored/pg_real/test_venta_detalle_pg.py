"""
VENTAS per-line detail (`venta_detalle`) contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. Cada
test trabaja dentro de una transacción que se revierte al final.

Cubre lo que los dobles no pueden: que `Aplicar` escribe el detalle junto con
`venta_mensual` (misma transacción, mismas filas), que re-subir reemplaza solo
los (sucursal, anio, mes) presentes en la carga nueva y que anular una carga
NO borra el detalle.
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
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.ingesta import ventas

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


def _carga():
    return CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="VALIDADO",
        nombre_archivo="v.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)


def _staging(carga, sucursal, referencia, mes, dia, nro, vendedor="Ana  Pérez", bruto="1000"):
    return CargaFilaStaging(
        carga_id=carga.id, fila=dia, lote=1, sucursal_id=sucursal.id,
        referencia_id=referencia.id,
        payload={
            "anio": 2026, "mes": mes, "dia": dia, "origen": "MOSTRADOR",
            "cantidad": "2", "vendedor": vendedor, "valor_bruto": bruto,
            "valor_descuentos": "100", "cliente_factura": "Taller El Rayo",
            "nro_documento": nro,
        })


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
    referencia = Referencia(
        id=uuid.uuid4(), codigo="R-1", proveedor_id=proveedor.id,
        unidad_empaque=1, precio_normal=Decimal("100"))
    cargas = [_carga(), _carga(), _carga()]
    db.add_all([referencia, *cargas])
    await db.flush()
    return sucursales, referencia, cargas


async def _aplicar(db, carga, filas, desde, hasta):
    veredicto = await ventas.aplicar_con_periodo(db, filas, desde, hasta, carga.id)
    await db.flush()
    return veredicto


async def _detalle(db, sucursal=None):
    consulta = select(VentaDetalle)
    if sucursal is not None:
        consulta = consulta.where(VentaDetalle.sucursal_id == sucursal.id)
    return (await db.execute(consulta)).scalars().all()


SEP = (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30))
AGO_SEP = (datetime.date(2026, 8, 1), datetime.date(2026, 9, 30))


async def test_aplicar_escribe_el_detalle_junto_con_venta_mensual(sesion):
    (a, _), ref, (c1, *_) = await _mundo(sesion)
    filas = [
        _staging(c1, a, ref, 9, 1, "FV-1"),
        _staging(c1, a, ref, 9, 2, "FV-2", vendedor="José Núñez", bruto="-500"),
    ]

    await _aplicar(sesion, c1, filas, *SEP)

    detalle = sorted(await _detalle(sesion, a), key=lambda d: d.nro_documento)
    assert [d.nro_documento for d in detalle] == ["FV-1", "FV-2"]
    primero = detalle[0]
    assert primero.fecha == datetime.date(2026, 9, 1)
    assert primero.carga_id == c1.id and primero.referencia_id == ref.id
    assert primero.vendedor == "Ana  Pérez"  # el crudo se conserva tal cual
    assert primero.vendedor_norm == "ANA PEREZ"
    assert (primero.valor_bruto, primero.valor_descuentos) == (Decimal("1000"), Decimal("100"))
    assert primero.cliente_factura == "Taller El Rayo"
    assert detalle[1].valor_bruto == Decimal("-500")
    mensual = (await sesion.execute(
        select(VentaMensual.unidades).where(VentaMensual.sucursal_id == a.id))).scalar_one()
    assert mensual == Decimal("4")  # dos lineas de 2: el agregado no cambia


async def test_resubir_reemplaza_solo_los_sucursal_anio_mes_presentes(sesion):
    (a, b), ref, (c1, c2, _) = await _mundo(sesion)
    await _aplicar(sesion, c1, [
        _staging(c1, a, ref, 8, 5, "AGO-A"),
        _staging(c1, a, ref, 9, 1, "SEP-A1"),
        _staging(c1, a, ref, 9, 2, "SEP-A2"),
        _staging(c1, b, ref, 9, 3, "SEP-B"),
    ], *AGO_SEP)

    await _aplicar(sesion, c2, [_staging(c2, a, ref, 9, 4, "SEP-A3")], *SEP)

    por_nro = {d.nro_documento: d.carga_id for d in await _detalle(sesion)}
    assert por_nro == {
        "AGO-A": c1.id,   # otro mes de la misma sucursal: intacto
        "SEP-B": c1.id,   # otra sucursal, mismo mes: intacta
        "SEP-A3": c2.id,  # reemplazo de (a, 2026, 9)
    }


async def test_anular_la_carga_no_borra_el_detalle(sesion, monkeypatch):
    # `anular_carga` hace commit: se degrada a flush para que el rollback de la
    # fixture siga aislando el test.
    monkeypatch.setattr(sesion, "commit", sesion.flush)
    (a, _), ref, (c1, *_) = await _mundo(sesion)
    await _aplicar(sesion, c1, [_staging(c1, a, ref, 9, 1, "FV-1")], *SEP)
    c1.estado = "APLICADO"
    await sesion.flush()

    await cargas_api.anular_carga(c1.id, db=sesion, user=None)

    assert c1.estado == "ANULADO"
    filas = (await sesion.execute(
        select(func.count()).select_from(VentaDetalle).where(VentaDetalle.carga_id == c1.id)
    )).scalar_one()
    assert filas == 1


async def test_carga_rechazada_por_periodo_no_escribe_detalle(sesion):
    (a, _), ref, (c1, *_) = await _mundo(sesion)
    filas = [_staging(c1, a, ref, 8, 5, "AGO-A")]  # declarado septiembre, todo agosto

    veredicto = await _aplicar(sesion, c1, filas, *SEP)

    assert veredicto.tipo.value == "RECHAZO"
    assert await _detalle(sesion) == []


# --- TALLER y detalle independiente del tipo --------------------------------

_SERIAL_2026_09_15 = 46280


def _fila_excel(tipo, modulo, nro, cantidad=2, ref="R-1"):
    return ("Aprobada", modulo, _SERIAL_2026_09_15, cantidad, tipo, "BODEGA UNO",
            "BA061", ref, "Ana  Pérez", 1000, 100, "Taller El Rayo", nro)


async def test_aplicar_archivo_mixto_taller_en_mensual_y_todo_en_detalle(sesion):
    from app.motored.services.ingesta.resolucion import CacheResolucion

    (a, _), ref, (c1, *_) = await _mundo(sesion)
    cache = CacheResolucion(
        sucursal_por_texto={"BODEGA UNO": a.id},
        referencia_por_codigo_proveedor={("R-1", ref.proveedor_id): ref.id})
    mapa = {n: i for i, n in enumerate(ventas.COLUMNAS_ESPERADAS)}
    filas_excel = [
        _fila_excel("0002 - REPUESTOS", "MOSTRADOR", "M-1", 3),
        _fila_excel("IRPTOSYACC", "TALLER", "T-1", 4),
        _fila_excel("IVNLUBGR", "TALLER", "T-2", 5),
        _fila_excel("0003 - OTROS", "MOSTRADOR", "O-1", 7),
        _fila_excel("0003 - OTROS", "MOSTRADOR", "O-2", 1, ref="NOEXISTE"),
    ]
    staged = []
    for n, fila in enumerate(filas_excel, start=2):
        staging, _ = ventas.procesar_fila(
            fila, numero_fila=n, lote=1, mapa_columnas=mapa, cache=cache,
            carga_id=c1.id, proveedor_id=ref.proveedor_id,
            tipos_inventario_incluidos=["0002 - REPUESTOS", "IRPTOSYACC", "IVNLUBGR"])
        if staging is not None:
            staged.append(staging)

    await _aplicar(sesion, c1, staged, *SEP)

    mensual = {
        m.origen: m.unidades for m in (await sesion.execute(
            select(VentaMensual).where(VentaMensual.sucursal_id == a.id))).scalars()}
    assert mensual == {"MOSTRADOR": Decimal("3"), "TALLER": Decimal("9")}
    detalle = {d.nro_documento: d.origen for d in await _detalle(sesion, a)}
    assert detalle == {"M-1": "MOSTRADOR", "T-1": "TALLER", "T-2": "TALLER",
                       "O-1": "MOSTRADOR"}  # O-2 no resuelve referencia: no se guarda
