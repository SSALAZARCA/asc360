"""
Motored "Inicio" against a real Postgres (opt-in).

Runs only with `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) pointing
at a database migrated with `alembic -c alembic_motored.ini upgrade head`.
One connection inside a transaction rolled back at the end
(`join_transaction_mode="create_savepoint"`), so the database stays clean.

Covers what the fakes cannot: Inicio equals the KPI tabs on the real SQL
(the Ventas total of the month and of "Año corrido" across lines, months
and annulled loads; the Asesores "con venta" by cedula and cargo), the
store count, and that each figure runs on its own savepoint (a failed one
does not poison the next). Sales are dated 2097 so they cannot meet other
data.
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
    """`{alias: vendedor_norm}`. Ana is in the master twice (one cedula),
    Dora is inactive (the company's rest), Carla is a comercial (a group,
    not a person)."""
    asesor, comercial = (
        "ASESOR DE REPUESTOS", "ASESOR COMERCIAL DE SERVICIO POSVENTA")
    filas = {
        "ana": ("Ana", asesor, "C1", True),
        "ana2": ("Ana Maria", asesor, "C1", True),
        "luis": ("Luis", asesor, "C2", True),
        "sofia": ("Sofia", asesor, "C3", True),
        "mario": ("Mario", asesor, "C4", True),
        "dora": ("Dora", asesor, "C5", False),
        "carla": ("Carla", comercial, "C6", True),
    }
    normas = {}
    for alias, (nombre, cargo, cedula, activo) in filas.items():
        completo = f"{nombre} {sfx}"
        normas[alias] = normalizar_vendedor(completo)
        db.add(Vendedor(
            id=uuid.uuid4(), nombre=completo, nombre_norm=normas[alias],
            cargo=cargo, cedula=f"{cedula}-{sfx}", activo=activo))
    await db.flush()
    return normas


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


async def _sembrar_ventas(db, sfx, principal, asociada, normas):
    """September 2097: Ana 900 + 300 (with her second name, at the
    associated store), Sofia 5000 in Accesorios, Dora 700 and Carla 600;
    Mario sells only without a line and Luis only in an annulled load.
    August 200 and October 50 (Luis); last year 7000."""
    refs = await _referencias(db, sfx)
    viva, anulada = _carga("APLICADO"), _carga("ANULADO")
    db.add_all([viva, anulada])
    await db.flush()

    def venta(quien, ref, fecha, bruto, desc=0, carga=viva,
              tienda=principal):
        db.add(VentaDetalle(
            id=uuid.uuid4(), carga_id=carga.id, fecha=fecha,
            anio=fecha.year, mes=fecha.month, sucursal_id=tienda.id,
            referencia_id=refs[ref].id, origen="MOSTRADOR",
            cantidad=D(1), vendedor=normas[quien],
            vendedor_norm=normas[quien], valor_bruto=D(bruto),
            valor_descuentos=D(desc), cliente_factura="Taller",
            nro_documento=f"F-{uuid.uuid4()}"))

    dia = datetime.date
    venta("ana", "R", dia(2097, 9, 1), 1000, 100)
    venta("ana2", "R", dia(2097, 9, 30), 300, tienda=asociada)
    venta("sofia", "A", dia(2097, 9, 15), 5000)
    venta("mario", "N", dia(2097, 9, 15), 4000)  # no line at all
    venta("luis", "R", dia(2097, 9, 15), 99999, carga=anulada)
    venta("dora", "R", dia(2097, 9, 20), 700)
    venta("carla", "A", dia(2097, 9, 21), 600)
    venta("luis", "R", dia(2097, 8, 31), 200)
    venta("luis", "R", dia(2097, 10, 3), 50)
    venta("luis", "R", dia(2096, 12, 31), 7000)  # last year
    await db.flush()


async def _kpi_ventas(db, meses):
    """The KPI Ventas tab's headline "Venta N meses" for `meses`."""
    filtro = await q.cargar_filtro(db, meses, HMCL_INCLUIR, None)
    ventas = await tablero_kpis.calcular_kpis_ventas(db, filtro)
    return ventas["total"]["venta"]["total"]


async def _kpi_asesores(db, meses):
    """The KPI Asesores tab's "Asesores con venta" for `meses`."""
    filtro = await q.cargar_filtro(db, meses, HMCL_INCLUIR, None)
    tablero = await tablero_kpis.calcular_kpis_asesores(db, filtro)
    return sum(1 for f in tablero["filas"]
               if f["tipo"] == "PERSONA" and f["venta"]["total"] > 0)


async def _sembrar(db, sfx):
    principal, asociada = await _sembrar_tiendas(db, sfx)
    normas = await _sembrar_vendedores(db, sfx)
    await _sembrar_ventas(db, sfx, principal, asociada, normas)


async def test_the_four_figures_equal_the_kpi_tabs(fabrica):
    sfx = uuid.uuid4().hex[:8].upper()
    corrido = [f"2097-{m:02d}" for m in range(1, 11)]
    async with fabrica() as db:
        tiendas_antes = (await inicio.construir_inicio(db, HOY))[
            "puntos_venta"]["cantidad"]
        await _sembrar(db, sfx)

        respuesta = await inicio.construir_inicio(db, HOY)
        kpi_mes = await _kpi_ventas(db, ["2097-09"])
        kpi_anio = await _kpi_ventas(db, corrido)
        kpi_asesores = await _kpi_asesores(db, ["2097-09"])

    assert respuesta["hoy"] == "2097-10-06"
    assert respuesta["ventas_mes"] == {
        "disponible": True, "valor": kpi_mes, "mes": "2097-09"}
    assert kpi_mes == 7500.0
    # The KPI's "Año corrido" ends at the last month with sales (October).
    assert respuesta["ventas_anio"] == {
        "disponible": True, "valor": kpi_anio, "desde": "2097-01",
        "hasta": "2097-10"}
    assert kpi_anio == 7750.0
    assert respuesta["puntos_venta"] == {
        "disponible": True, "cantidad": tiendas_antes + 1}
    # Ana (two names, one cedula) and Sofia.
    assert respuesta["asesores"] == {
        "disponible": True, "cantidad": kpi_asesores, "mes": "2097-09"}
    assert kpi_asesores == 2


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
