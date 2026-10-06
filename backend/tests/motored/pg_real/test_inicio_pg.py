"""
Motored "Inicio" against a real Postgres (opt-in).

Runs only with `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) pointing
at a database migrated with `alembic -c alembic_motored.ini upgrade head`.
One connection inside a transaction rolled back at the end
(`join_transaction_mode="create_savepoint"`), so the database stays clean.

Covers what the fakes cannot: the KPI's real SQL behind the Repuestos
sales (lines, months, annulled loads), the store and vendedor counts, and
that each figure runs on its own savepoint (a failed one does not poison
the next). Sales are dated 2097 so they cannot meet other data.
"""
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import inicio
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis
from app.motored.services.tablero_asesores import HMCL_INCLUIR
from app.motored.services.ingesta.ventas import normalizar_vendedor

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = Decimal
HOY = datetime.date(2097, 10, 6)


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        yield async_sessionmaker(
            bind=conexion, class_=AsyncSession, expire_on_commit=False,
            autoflush=False, join_transaction_mode="create_savepoint")
        await transaccion.rollback()
    await motor.dispose()


def _carga(estado):
    return CargaArchivo(
        id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado=estado,
        nombre_archivo="x.xlsx", hash_sha256="h" * 64, ruta_objeto="r",
        bytes=1)


async def _sembrar_tiendas(db, sfx):
    """An active principal, an active store associated to it and an
    inactive principal: only the first one is a punto de venta."""
    principal = Sucursal(
        id=uuid.uuid4(), nombre=f"Cali {sfx}", sic=f"S1-{sfx}")
    inactiva = Sucursal(
        id=uuid.uuid4(), nombre=f"Pasto {sfx}", sic=f"S3-{sfx}",
        activa=False)
    db.add_all([principal, inactiva])
    await db.flush()
    asociada = Sucursal(
        id=uuid.uuid4(), nombre=f"Cali Sur {sfx}", sic=f"S2-{sfx}",
        principal_id=principal.id)
    db.add(asociada)
    await db.flush()
    return principal, asociada


async def _sembrar_vendedores(db, sfx):
    """Two active vendedores and an inactive one."""
    def persona(nombre, activo=True):
        return Vendedor(
            id=uuid.uuid4(), nombre=f"{nombre} {sfx}",
            nombre_norm=normalizar_vendedor(f"{nombre} {sfx}"),
            cargo="ASESOR DE REPUESTOS", activo=activo)

    db.add_all([persona("Ana"), persona("Luis"),
                persona("Dora", activo=False)])
    await db.flush()


async def _referencias(db, sfx):
    prov = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{sfx}", nombre="P", es_principal=True,
        dias_empaque_default=4, dias_transito_default=5,
        dias_seguridad_default=D("3"))
    db.add(prov)
    await db.flush()
    refs = {
        clave: Referencia(
            id=uuid.uuid4(), codigo=f"{clave}-{sfx}", proveedor_id=prov.id,
            unidad_empaque=1, precio_normal=None, linea_comercial=linea)
        for clave, linea in (
            ("R", " repuestos "), ("A", "ACCESORIOS"), ("N", None))}
    db.add_all(refs.values())
    await db.flush()
    return refs


async def _sembrar_ventas(db, sfx, principal, asociada):
    """September 2097: Repuestos 900 + 300 (the associated store is sold
    from too); August 200 and October 50; the rest must not count."""
    refs = await _referencias(db, sfx)
    viva, anulada = _carga("APLICADO"), _carga("ANULADO")
    db.add_all([viva, anulada])
    await db.flush()

    def venta(ref, fecha, bruto, desc=0, carga=viva, tienda=principal):
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=fecha,
            anio=fecha.year, mes=fecha.month, sucursal_id=tienda.id,
            referencia_id=refs[ref].id, origen="MOSTRADOR",
            cantidad=D(1), vendedor="X", vendedor_norm="X",
            valor_bruto=D(bruto), valor_descuentos=D(desc),
            cliente_factura="Taller", nro_documento=f"F-{uuid.uuid4()}"))

    dia = datetime.date
    venta("R", dia(2097, 9, 1), 1000, 100)
    venta("R", dia(2097, 9, 30), 300, tienda=asociada)
    venta("A", dia(2097, 9, 15), 5000)  # another line
    venta("N", dia(2097, 9, 15), 4000)  # no line at all
    venta("R", dia(2097, 9, 15), 99999, carga=anulada)  # annulled
    venta("R", dia(2097, 8, 31), 200)
    venta("R", dia(2097, 10, 3), 50)
    venta("R", dia(2096, 12, 31), 7000)  # last year
    await db.flush()


async def _venta_del_tablero(db, meses):
    """What the KPI Ventas tab shows for Repuestos in `meses`."""
    filtro = await q.cargar_filtro(db, meses, HMCL_INCLUIR, None)
    ventas = await tablero_kpis.calcular_kpis_ventas(db, filtro)
    return ventas["total"]["venta"]["por_linea"]["REPUESTOS"]


async def _contar(db):
    respuesta = await inicio.construir_inicio(db, HOY)
    return (respuesta["puntos_venta"]["cantidad"],
            respuesta["asesores"]["cantidad"])


async def test_the_four_figures_from_a_seeded_database(fabrica):
    sfx = uuid.uuid4().hex[:8].upper()
    async with fabrica() as db:
        tiendas_antes, asesores_antes = await _contar(db)
        principal, asociada = await _sembrar_tiendas(db, sfx)
        await _sembrar_vendedores(db, sfx)
        await _sembrar_ventas(db, sfx, principal, asociada)

        respuesta = await inicio.construir_inicio(db, HOY)
        tablero_mes = await _venta_del_tablero(db, ["2097-09"])
        tablero_anio = await _venta_del_tablero(
            db, [f"2097-{m:02d}" for m in range(1, 11)])

    assert respuesta["hoy"] == "2097-10-06"
    assert respuesta["ventas_mes"]["valor"] == tablero_mes
    assert respuesta["ventas_anio"]["valor"] == tablero_anio
    assert respuesta["ventas_mes"] == {
        "disponible": True, "valor": 1200.0, "mes": "2097-09"}
    assert respuesta["ventas_anio"] == {
        "disponible": True, "valor": 1450.0, "desde": "2097-01-01",
        "hasta": "2097-10-06"}
    assert respuesta["puntos_venta"] == {
        "disponible": True, "cantidad": tiendas_antes + 1}
    assert respuesta["asesores"] == {
        "disponible": True, "cantidad": asesores_antes + 2}


async def test_a_failed_query_does_not_poison_the_next_figure(
        fabrica, monkeypatch):
    async def _rota(ctx):
        await ctx.db.execute(
            Corrida.__table__.select().where(
                Corrida.__table__.c.codigo.op("~")("(")))
        return {}

    monkeypatch.setitem(inicio.CONSTRUCTORES, "ventas_mes", _rota)
    async with fabrica() as db:
        respuesta = await inicio.construir_inicio(db, HOY)

    assert respuesta["ventas_mes"] == {"disponible": False}
    for nombre in ("ventas_anio", "puntos_venta", "asesores"):
        assert respuesta[nombre]["disponible"] is True
