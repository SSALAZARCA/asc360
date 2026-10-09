"""
Inventory counts, schedule and Iniciar against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`; odd/motored-conteos-inventario, WU5; design §4.10,
§5.1, ADR-1, ADR-2, ADR-9).

Each test seeds its own stores, cargas and inventory rows and rolls back,
except the concurrency test, which needs two committed sessions and
deletes what it created.
"""
import asyncio
import datetime
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_sesion import ConteoSesion
from app.motored.models.conteo_snapshot_linea import ConteoSnapshotLinea
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services.conteos import (
    acceso, consultas, errores, snapshot,
)
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

UTC = datetime.timezone.utc
AHORA = datetime.datetime.now(UTC).replace(microsecond=0)
HOY = AHORA.date()
AYER = HOY - datetime.timedelta(days=1)
HACE_UNA_HORA = AHORA - datetime.timedelta(hours=1)


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    yield async_sessionmaker(motor, expire_on_commit=False, autoflush=False)
    await motor.dispose()


@pytest.fixture
async def db(fabrica):
    async with fabrica() as sesion:
        yield sesion
        await sesion.rollback()


class Mundo:
    """Seeds of one test: stores, users, referencias and cargas."""

    def __init__(self, db):
        self.db = db
        self.proveedor = None
        self.admin = None
        self.lider = None

    async def base(self):
        self.proveedor = Proveedor(
            id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:8]}",
            nombre="P", es_principal=True)
        self.admin = self._usuario(MotoredRole.ADMIN)
        self.lider = self._usuario(MotoredRole.LIDER_INVENTARIOS)
        self.db.add_all([self.proveedor, self.admin, self.lider])
        await self.db.flush()
        return self

    def _usuario(self, rol, activo=True):
        return Usuario(
            id=uuid.uuid4(), nombre=rol.value,
            email=f"u-{uuid.uuid4().hex[:10]}@x.com", hashed_password="h",
            role=rol, activo=activo, status="approved")

    async def usuario(self, rol, activo=True):
        usuario = self._usuario(rol, activo)
        self.db.add(usuario)
        await self.db.flush()
        return usuario

    async def tienda(self, activa=True):
        sucursal = Sucursal(
            id=uuid.uuid4(), nombre=f"S {uuid.uuid4().hex[:8]}",
            codigo_co=codigo_co_unico(), bodega_principal="B01",
            activa=activa)
        self.db.add(sucursal)
        await self.db.flush()
        return sucursal

    async def referencia(self, precio=None):
        referencia = Referencia(
            id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:10]}",
            proveedor_id=self.proveedor.id, unidad_empaque=1,
            precio_normal=precio)
        self.db.add(referencia)
        await self.db.flush()
        return referencia

    async def carga(self, fecha, filas, aplicado_en=HACE_UNA_HORA,
                    estado="APLICADO"):
        """`filas`: (sucursal, referencia, bodega, existencia, costo)."""
        carga = CargaArchivo(
            id=uuid.uuid4(), tipo="INVENTARIO", estado=estado,
            aplicado_en=aplicado_en, periodo_desde=fecha,
            periodo_hasta=fecha, nombre_archivo="inv.xlsx",
            hash_sha256=uuid.uuid4().hex * 2, ruta_objeto="x/inv.xlsx",
            bytes=1)
        self.db.add(carga)
        await self.db.flush()
        self.db.add_all([
            InventarioDetalle(
                id=uuid.uuid4(), carga_id=carga.id, fecha_corte=fecha,
                sucursal_id=s.id, referencia_id=r.id, bodega=b,
                existencia=Decimal(str(e)),
                costo_unitario=None if c is None else Decimal(str(c)))
            for s, r, b, e, c in filas])
        await self.db.flush()
        return carga

    async def recargar(self, fecha, filas, **extra):
        """A same-date reload: Maestros deletes the date's rows of each
        store in the new carga, then inserts the new ones."""
        tiendas = {f[0].id for f in filas}
        await self.db.execute(delete(InventarioDetalle).where(
            InventarioDetalle.fecha_corte == fecha,
            InventarioDetalle.sucursal_id.in_(tiendas)))
        return await self.carga(fecha, filas, **extra)

    async def programado(self, sucursal):
        return await snapshot.programar_conteo(
            self.db, sucursal.id, self.lider.id, HOY, self.admin.id)


@pytest.fixture
async def mundo(db):
    return await Mundo(db).base()


async def _iniciar(mundo, conteo, **extra):
    return await snapshot.iniciar_conteo(
        mundo.db, conteo.id, mundo.lider.id, ahora=AHORA, **extra)


async def _lineas(db, conteo):
    """Snapshot lines of a conteo (object or id) by referencia."""
    conteo_id = getattr(conteo, "id", conteo)
    filas = (await db.scalars(select(ConteoSnapshotLinea).where(
        ConteoSnapshotLinea.conteo_id == conteo_id))).all()
    return {f.referencia_id: f for f in filas}


# --- scheduling -------------------------------------------------------------


async def test_schedule_creates_a_programado_total(mundo):
    tienda = await mundo.tienda()

    conteo = await mundo.programado(tienda)

    assert (conteo.tipo, conteo.estado, conteo.origen) == (
        "TOTAL", "PROGRAMADO", "MANUAL")
    assert conteo.lider_id == mundo.lider.id
    assert conteo.creado_por == mundo.admin.id


@pytest.mark.parametrize("rol, activo", [
    (MotoredRole.COMPRAS, True), (MotoredRole.ADMIN, True),
    (MotoredRole.LIDER_INVENTARIOS, False),
])
async def test_the_leader_must_be_an_active_lider_inventarios(
        mundo, rol, activo):
    tienda = await mundo.tienda()
    otro = await mundo.usuario(rol, activo)

    with pytest.raises(errores.LiderInvalido):
        await snapshot.programar_conteo(
            mundo.db, tienda.id, otro.id, HOY, mundo.admin.id)
    with pytest.raises(errores.LiderInvalido):
        await snapshot.programar_conteo(
            mundo.db, tienda.id, uuid.uuid4(), HOY, mundo.admin.id)


async def test_a_coordinator_led_conteo_is_scheduled_and_started(mundo):
    """Owner decision 2026-10-09: COORDINADOR_REPUESTOS leads counts."""
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 4, 10)])
    coordinador = await mundo.usuario(MotoredRole.COORDINADOR_REPUESTOS)

    conteo = await snapshot.programar_conteo(
        mundo.db, tienda.id, coordinador.id, HOY, mundo.admin.id)
    inicio = await snapshot.iniciar_conteo(
        mundo.db, conteo.id, coordinador.id, ahora=AHORA)

    assert (conteo.lider_id, inicio.conteo.estado) == (
        coordinador.id, "EN_CONTEO")
    assert list(await _lineas(mundo.db, conteo)) == [referencia.id]
    opciones = {o.id: o.rol for o in await consultas.lideres_activos(
        mundo.db)}
    assert opciones[coordinador.id] == "COORDINADOR_REPUESTOS"
    assert opciones[mundo.lider.id] == "LIDER_INVENTARIOS"
    assert mundo.admin.id not in opciones


async def test_the_store_must_exist_and_be_active(mundo):
    cerrada = await mundo.tienda(activa=False)

    for sucursal_id in (cerrada.id, uuid.uuid4()):
        with pytest.raises(errores.SucursalInvalida):
            await snapshot.programar_conteo(
                mundo.db, sucursal_id, mundo.lider.id, HOY, mundo.admin.id)


async def test_reschedule_changes_date_and_leader_only_while_programado(
        mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 1, 10)])
    conteo = await mundo.programado(tienda)
    nuevo = await mundo.usuario(MotoredRole.LIDER_INVENTARIOS)
    manana = HOY + datetime.timedelta(days=1)

    await snapshot.reprogramar_conteo(mundo.db, conteo.id, manana, nuevo.id)
    assert (conteo.fecha_programada, conteo.lider_id) == (manana, nuevo.id)

    await _iniciar(mundo, conteo)
    with pytest.raises(errores.EstadoInvalido):
        await snapshot.reprogramar_conteo(mundo.db, conteo.id, HOY)


async def test_annul_needs_a_reason_and_closes_access(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 1, 10)])
    conteo = await mundo.programado(tienda)
    await _iniciar(mundo, conteo)
    sesion = ConteoSesion(
        id=uuid.uuid4(), conteo_id=conteo.id, token_hash="t" * 64,
        dispositivo="ESCRITORIO")
    mundo.db.add(sesion)
    await mundo.db.flush()

    with pytest.raises(errores.MotivoRequerido):
        await snapshot.anular_conteo(mundo.db, conteo.id, mundo.admin.id, "")
    await snapshot.anular_conteo(
        mundo.db, conteo.id, mundo.admin.id, " tienda inundada ", AHORA)

    assert conteo.estado == "ANULADO"
    assert conteo.motivo_anulacion == "tienda inundada"
    assert (conteo.anulado_por, conteo.anulado_en) == (mundo.admin.id, AHORA)
    assert conteo.codigo_hash is None
    await mundo.db.refresh(sesion)
    assert sesion.estado == "CERRADA"
    with pytest.raises(errores.EstadoInvalido):
        await snapshot.anular_conteo(
            mundo.db, conteo.id, mundo.admin.id, "otra vez")


async def test_an_unknown_conteo_is_not_found(mundo):
    with pytest.raises(errores.ConteoNoEncontrado):
        await snapshot.iniciar_conteo(mundo.db, uuid.uuid4(), mundo.lider.id)


# --- Iniciar: which carga ---------------------------------------------------


async def test_iniciar_takes_the_store_latest_carga_skipping_annulled(mundo):
    tienda, otra = await mundo.tienda(), await mundo.tienda()
    referencia = await mundo.referencia()
    vieja = await mundo.carga(
        AYER - datetime.timedelta(days=1),
        [(tienda, referencia, "B01", 1, 10)])
    buena = await mundo.carga(AYER, [(tienda, referencia, "B01", 2, 10)])
    await mundo.carga(
        HOY, [(tienda, referencia, "B01", 9, 10)], estado="ANULADO")
    await mundo.carga(
        HOY + datetime.timedelta(days=1), [(otra, referencia, "B01", 5, 10)])
    conteo = await mundo.programado(tienda)

    inicio = await _iniciar(mundo, conteo, confirmar_inventario_viejo=True)

    assert vieja.id != buena.id
    assert inicio.fuente.carga_id == buena.id
    assert conteo.snapshot_carga_id == buena.id
    assert conteo.snapshot_fecha_corte == AYER
    assert conteo.snapshot_aplicado_en == HACE_UNA_HORA
    lineas = await _lineas(mundo.db, conteo)
    assert lineas[referencia.id].existencia == Decimal("2")


async def test_a_store_without_inventory_cannot_start(mundo):
    tienda = await mundo.tienda()
    conteo = await mundo.programado(tienda)

    with pytest.raises(errores.SinInventario):
        await _iniciar(mundo, conteo)
    assert conteo.estado == "PROGRAMADO"


async def test_iniciar_freezes_thresholds_slug_and_a_hashed_code(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 3, 10)])
    conteo = await mundo.programado(tienda)

    inicio = await _iniciar(mundo, conteo)

    assert conteo.estado == "EN_CONTEO"
    assert (conteo.iniciado_por, conteo.iniciado_en) == (
        mundo.lider.id, AHORA)
    assert conteo.snapshot_tomado_en == AHORA
    assert conteo.umbral_reconteo_pesos == Decimal("100000")
    assert conteo.umbral_critico_pesos == Decimal("500000")
    assert len(conteo.enlace_slug) == acceso.LARGO_SLUG
    assert inicio.codigo not in conteo.codigo_hash
    assert acceso.verificar_codigo(
        conteo.id, inicio.codigo, conteo.codigo_hash)
    assert inicio.fuente.lineas == 1
    assert inicio.advertencia is None


async def test_rotating_the_code_invalidates_the_old_one(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 3, 10)])
    conteo = await mundo.programado(tienda)
    viejo = (await _iniciar(mundo, conteo)).codigo

    nuevo = await acceso.rotar_codigo(mundo.db, conteo.id, AHORA)

    assert acceso.verificar_codigo(conteo.id, nuevo, conteo.codigo_hash)
    if nuevo != viejo:
        assert not acceso.verificar_codigo(
            conteo.id, viejo, conteo.codigo_hash)
    assert conteo.codigo_rotado_en == AHORA


async def test_rotating_needs_an_open_conteo(mundo):
    tienda = await mundo.tienda()
    conteo = await mundo.programado(tienda)

    with pytest.raises(errores.EstadoInvalido):
        await acceso.rotar_codigo(mundo.db, conteo.id)


# --- Iniciar: staleness -----------------------------------------------------


async def test_a_stale_inventory_is_refused_and_leaves_nothing(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    viejo = AHORA - datetime.timedelta(hours=30)
    carga = await mundo.carga(
        AYER, [(tienda, referencia, "B01", 3, 10)], aplicado_en=viejo)
    conteo = await mundo.programado(tienda)

    with pytest.raises(errores.InventarioAntiguo) as error:
        await _iniciar(mundo, conteo)

    assert error.value.datos["fecha_corte"] == AYER.isoformat()
    assert error.value.datos["carga_id"] == str(carga.id)
    assert error.value.datos["antiguedad_horas"] == "30.0"
    assert await _lineas(mundo.db, conteo) == {}
    assert conteo.estado == "PROGRAMADO"


async def test_a_confirmed_stale_inventory_starts_and_is_recorded(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(
        AYER, [(tienda, referencia, "B01", 3, 10)],
        aplicado_en=AHORA - datetime.timedelta(hours=30))
    conteo = await mundo.programado(tienda)

    await _iniciar(mundo, conteo, confirmar_inventario_viejo=True)

    assert conteo.estado == "EN_CONTEO"
    assert conteo.snapshot_advertencias == {
        "antiguedad_horas": "30.0", "vigencia_horas": 6,
        "confirmada_por": str(mundo.lider.id)}


# --- Iniciar: the frozen copy ----------------------------------------------


async def test_a_same_date_reload_leaves_a_taken_snapshot_intact(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    primera = await mundo.carga(HOY, [(tienda, referencia, "B01", 4, 10)])
    conteo = await mundo.programado(tienda)
    await _iniciar(mundo, conteo)

    await mundo.recargar(HOY, [(tienda, referencia, "B01", 99, 50)])

    linea = (await _lineas(mundo.db, conteo))[referencia.id]
    assert (linea.existencia, linea.costo_unitario) == (
        Decimal("4"), Decimal("10"))
    assert conteo.snapshot_carga_id == primera.id


async def test_two_stores_started_at_different_times_differ(mundo):
    tienda_a, tienda_b = await mundo.tienda(), await mundo.tienda()
    referencia = await mundo.referencia()
    x = await mundo.carga(HOY, [
        (tienda_a, referencia, "B01", 1, 10),
        (tienda_b, referencia, "B01", 1, 10)])
    conteo_a = await mundo.programado(tienda_a)
    conteo_b = await mundo.programado(tienda_b)
    await _iniciar(mundo, conteo_a)

    y = await mundo.recargar(HOY, [
        (tienda_a, referencia, "B01", 7, 20),
        (tienda_b, referencia, "B01", 8, 20)])
    await _iniciar(mundo, conteo_b)

    assert (conteo_a.snapshot_carga_id, conteo_b.snapshot_carga_id) == (
        x.id, y.id)
    a = (await _lineas(mundo.db, conteo_a))[referencia.id]
    b = (await _lineas(mundo.db, conteo_b))[referencia.id]
    assert (a.existencia, b.existencia) == (Decimal("1"), Decimal("8"))


async def test_lines_sum_the_store_bodegas_per_referencia(mundo):
    tienda, otra = await mundo.tienda(), await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [
        (tienda, referencia, "B01", 3, 100),
        (tienda, referencia, "B01S", 2, 200),
        (tienda, referencia, "B01S", 1, 200),
        (otra, referencia, "B09", 50, 1)])
    conteo = await mundo.programado(tienda)

    await _iniciar(mundo, conteo)

    lineas = await _lineas(mundo.db, conteo)
    linea = lineas[referencia.id]
    assert len(lineas) == 1
    assert linea.existencia == Decimal("6")
    assert {k: Decimal(str(v)) for k, v in
            linea.existencia_por_bodega.items()} == {
        "B01": Decimal("3"), "B01S": Decimal("3")}
    # (3 x 100 + 3 x 200) / 6
    assert (linea.costo_unitario, linea.costo_fuente) == (
        Decimal("150.00"), "BODEGA")


# --- Iniciar: the cost fallback ---------------------------------------------


async def test_cost_fallback_takes_each_source_in_order(mundo):
    tienda, otra, tercera = (
        await mundo.tienda(), await mundo.tienda(), await mundo.tienda())
    sin_peso = await mundo.referencia()
    ajena = await mundo.referencia()
    mediana = await mundo.referencia()
    precio = await mundo.referencia(precio=Decimal("77"))
    nada = await mundo.referencia()
    await mundo.carga(HOY, [
        (tienda, sin_peso, "B01", 0, 100), (tienda, sin_peso, "B01S", -1, 200),
        (tienda, ajena, "B01", 2, None),
        (otra, ajena, "B02", 4, 50), (tercera, ajena, "B03", 1, 100),
        (tienda, mediana, "B01", 2, 0),
        (otra, mediana, "B02", 0, 10), (otra, mediana, "B02S", 0, 90),
        (tercera, mediana, "B03", -2, 20),
        (tienda, precio, "B01", 1, None),
        (tienda, nada, "B01", 1, -5)])
    conteo = await mundo.programado(tienda)

    await _iniciar(mundo, conteo)

    lineas = await _lineas(mundo.db, conteo)
    costos = {
        r.id: (lineas[r.id].costo_unitario, lineas[r.id].costo_fuente)
        for r in (sin_peso, ajena, mediana, precio, nada)}
    assert costos == {
        sin_peso.id: (Decimal("150.00"), "BODEGA"),
        ajena.id: (Decimal("60.00"), "REFERENCIA"),
        mediana.id: (Decimal("20.00"), "MEDIANA"),
        precio.id: (Decimal("77.00"), "PRECIO"),
        nada.id: (None, "SIN_COSTO"),
    }


# --- Iniciar: one running TOTAL per store, double Iniciar --------------------


async def test_a_second_running_total_in_a_store_is_refused(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 1, 10)])
    primero = await mundo.programado(tienda)
    segundo = await mundo.programado(tienda)
    await _iniciar(mundo, primero)

    with pytest.raises(errores.ConteoTotalAbierto):
        await _iniciar(mundo, segundo)
    assert await _lineas(mundo.db, segundo) == {}


async def test_the_partial_unique_maps_to_the_same_domain_error(
        mundo, monkeypatch):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 1, 10)])
    primero = await mundo.programado(tienda)
    segundo = await mundo.programado(tienda)
    segundo_id = segundo.id
    await _iniciar(mundo, primero)

    async def sin_revision(_db, _conteo):
        return None

    monkeypatch.setattr(snapshot, "_exigir_sin_total_abierto", sin_revision)
    with pytest.raises(errores.ConteoTotalAbierto):
        await _iniciar(mundo, segundo)
    # The refused SAVEPOINT expired `segundo`; query by its id.
    assert await _lineas(mundo.db, segundo_id) == {}


async def test_a_second_iniciar_on_the_same_conteo_is_refused(mundo):
    tienda = await mundo.tienda()
    referencia = await mundo.referencia()
    await mundo.carga(HOY, [(tienda, referencia, "B01", 1, 10)])
    conteo = await mundo.programado(tienda)
    await _iniciar(mundo, conteo)

    with pytest.raises(errores.EstadoInvalido):
        await _iniciar(mundo, conteo)
    assert len(await _lineas(mundo.db, conteo)) == 1


async def _sembrar_comprometido(fabrica):
    async with fabrica() as db:
        mundo = await Mundo(db).base()
        tienda = await mundo.tienda()
        referencia = await mundo.referencia()
        carga = await mundo.carga(HOY, [(tienda, referencia, "B01", 1, 10)])
        conteo = await mundo.programado(tienda)
        await db.commit()
        return {
            "conteo": conteo.id, "carga": carga.id, "tienda": tienda.id,
            "referencia": referencia.id, "proveedor": mundo.proveedor.id,
            "usuarios": [mundo.admin.id, mundo.lider.id],
            "lider": mundo.lider.id}


async def _borrar_comprometido(fabrica, ids):
    async with fabrica() as db:
        for modelo, columna, valores in (
                (Conteo, Conteo.id, [ids["conteo"]]),
                (InventarioDetalle, InventarioDetalle.carga_id,
                 [ids["carga"]]),
                (CargaArchivo, CargaArchivo.id, [ids["carga"]]),
                (Referencia, Referencia.id, [ids["referencia"]]),
                (Sucursal, Sucursal.id, [ids["tienda"]]),
                (Usuario, Usuario.id, ids["usuarios"]),
                (Proveedor, Proveedor.id, [ids["proveedor"]])):
            await db.execute(delete(modelo).where(columna.in_(valores)))
        await db.commit()


async def _iniciar_en_sesion(fabrica, ids):
    async with fabrica() as db:
        try:
            await snapshot.iniciar_conteo(
                db, ids["conteo"], ids["lider"], ahora=AHORA)
            await asyncio.sleep(0.2)
            await db.commit()
            return "ok"
        except errores.EstadoInvalido:
            await db.rollback()
            return "rechazado"


async def test_two_concurrent_iniciar_start_the_conteo_once(fabrica):
    ids = await _sembrar_comprometido(fabrica)
    try:
        resultados = await asyncio.gather(
            _iniciar_en_sesion(fabrica, ids),
            _iniciar_en_sesion(fabrica, ids))
        async with fabrica() as db:
            lineas = await db.scalar(
                select(func.count()).select_from(ConteoSnapshotLinea)
                .where(ConteoSnapshotLinea.conteo_id == ids["conteo"]))
    finally:
        await _borrar_comprometido(fabrica, ids)

    assert sorted(resultados) == ["ok", "rechazado"]
    assert lineas == 1
