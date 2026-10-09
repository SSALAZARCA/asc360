"""
Inventory counts, stage 1 tables against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`; odd/motored-conteos-inventario, WU2 + WU3).

Two parts:

- the migrations: each test creates its own throwaway database on the
  same server (needs `CREATE DATABASE`), runs upgrade / downgrade 2 /
  upgrade, and checks the models match the DDL;
- the constraints: on the already migrated database, every CHECK, the
  partial uniques (one open TOTAL count per store, one live reconteo per
  code), the client-id idempotency of readings and the cascades. Each
  test rolls back; a refused row runs inside a SAVEPOINT.
"""
import asyncio
import datetime
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.motored.database import MotoredBase
from app.motored.models.bodega import Bodega
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_acceso_intento import ConteoAccesoIntento
from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.conteo_resultado import ConteoResultado
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.models.conteo_snapshot_linea import ConteoSnapshotLinea
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.models.usuario import MotoredRole, Usuario
from tests.motored.pg_real.codigos_co import codigo_co_unico

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

_RAIZ = Path(__file__).resolve().parents[3]
PREVIA, BASE, LECTURAS = "b4f9c2e6a813", "c3e7a1f50d24", "d58b2c9e4a17"
TABLAS = (
    "conteo", "conteo_snapshot_linea", "ubicacion_inventario",
    "conteo_sesion", "conteo_integrante", "conteo_reconteo",
    "conteo_lectura", "conteo_acceso_intento", "conteo_resultado",
)
AHORA = datetime.datetime(2026, 10, 9, 18, 0, tzinfo=datetime.timezone.utc)
HOY = datetime.date(2026, 10, 9)


# --- migrations on a throwaway database -------------------------------------


def _correr(corrutina):
    return asyncio.run(corrutina)


async def _admin(sentencia):
    motor = create_async_engine(
        URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conexion:
        await conexion.execute(text(sentencia))
    await motor.dispose()


async def _consultar(url, sentencia):
    motor = create_async_engine(url, poolclass=NullPool)
    try:
        async with motor.connect() as conexion:
            return (await conexion.execute(text(sentencia))).all()
    finally:
        await motor.dispose()


def _alembic(accion, destino):
    config = Config()
    config.set_main_option(
        "script_location", str(_RAIZ / "alembic_motored"))
    getattr(command, accion)(config, destino)


def _tablas_conteo(url):
    filas = _correr(_consultar(
        url, "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'"))
    return {f[0] for f in filas} & set(TABLAS)


def _version(url):
    return _correr(_consultar(
        url, "SELECT version_num FROM alembic_version_motored"))[0][0]


@pytest.fixture
def base_vacia(monkeypatch):
    nombre = f"mig_conteo_{uuid.uuid4().hex[:10]}"
    _correr(_admin(f'CREATE DATABASE "{nombre}"'))
    url = make_url(URL).set(database=nombre).render_as_string(
        hide_password=False)
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", url)
    yield url
    _correr(_admin(f'DROP DATABASE "{nombre}" WITH (FORCE)'))


def test_upgrade_downgrade_upgrade_of_both_revisions(base_vacia):
    _alembic("upgrade", "head")
    assert _tablas_conteo(base_vacia) == set(TABLAS)
    assert _version(base_vacia) == LECTURAS

    _alembic("downgrade", BASE)
    assert _tablas_conteo(base_vacia) == {
        "conteo", "conteo_snapshot_linea", "ubicacion_inventario"}

    _alembic("downgrade", PREVIA)
    assert _tablas_conteo(base_vacia) == set()
    assert _version(base_vacia) == PREVIA

    _alembic("upgrade", "head")
    assert _tablas_conteo(base_vacia) == set(TABLAS)


async def _diferencias(url):
    motor = create_async_engine(url, poolclass=NullPool)

    def _comparar(conexion):
        contexto = MigrationContext.configure(
            conexion, opts={"compare_type": True})
        return compare_metadata(contexto, MotoredBase.metadata)

    try:
        async with motor.connect() as conexion:
            return await conexion.run_sync(_comparar)
    finally:
        await motor.dispose()


def test_the_models_match_the_ddl(base_vacia):
    _alembic("upgrade", "head")

    diferencias = _correr(_diferencias(base_vacia))

    propias = [
        d for d in diferencias if any(t in str(d) for t in TABLAS)]
    assert propias == []


# --- constraints on the migrated database -----------------------------------


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(
        motor, expire_on_commit=False, autoflush=False)
    async with fabrica() as db:
        yield db
        await db.rollback()
    await motor.dispose()


@pytest.fixture
async def mundo(sesion):
    """A store with a principal bodega, a referencia and a leader."""
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"P-{uuid.uuid4().hex[:8]}", nombre="P",
        es_principal=True)
    sucursal = Sucursal(
        id=uuid.uuid4(), nombre=f"S {uuid.uuid4().hex[:8]}",
        codigo_co=codigo_co_unico(), bodega_principal="BX001")
    lider = Usuario(
        id=uuid.uuid4(), nombre="Lider",
        email=f"l-{uuid.uuid4().hex[:8]}@x.com", hashed_password="h",
        role=MotoredRole.LIDER_INVENTARIOS, activo=True, status="approved")
    sesion.add_all([proveedor, sucursal, lider])
    await sesion.flush()
    referencia = Referencia(
        id=uuid.uuid4(), codigo=f"R-{uuid.uuid4().hex[:10]}",
        proveedor_id=proveedor.id, unidad_empaque=1)
    bodega = Bodega(
        id=uuid.uuid4(), codigo=f"B-{uuid.uuid4().hex[:8]}",
        sucursal_id=sucursal.id)
    sesion.add_all([referencia, bodega])
    await sesion.flush()
    return {
        "sucursal": sucursal, "lider": lider, "referencia": referencia,
        "bodega": bodega,
    }


def _conteo(mundo, **extra):
    datos = {
        "id": uuid.uuid4(), "tipo": "TOTAL", "estado": "PROGRAMADO",
        "origen": "MANUAL", "sucursal_id": mundo["sucursal"].id,
        "lider_id": mundo["lider"].id, "fecha_programada": HOY,
    }
    datos.update(extra)
    return Conteo(**datos)


def _abierto(mundo, estado="EN_CONTEO", **extra):
    datos = {
        "snapshot_tomado_en": AHORA,
        "umbral_reconteo_pesos": Decimal("100000"),
        "umbral_critico_pesos": Decimal("500000"),
    }
    datos.update(extra)
    return _conteo(mundo, estado=estado, **datos)


async def _guardar(sesion, *filas):
    sesion.add_all(filas)
    await sesion.flush()


async def _rechazada(sesion, restriccion, *filas):
    with pytest.raises(IntegrityError, match=restriccion):
        async with sesion.begin_nested():
            sesion.add_all(filas)
            await sesion.flush()


@pytest.mark.parametrize("restriccion, extra", [
    ("ck_conteo_tipo", {"tipo": "OTRO"}),
    ("ck_conteo_estado", {"estado": "PAUSADO"}),
    ("ck_conteo_origen", {"origen": "BOT"}),
    ("ck_conteo_lider_si_total", {"lider_id": None}),
    ("ck_conteo_snapshot_si_iniciado", {"estado": "EN_CONTEO"}),
    ("ck_conteo_slug_solo_total", {
        "tipo": "SELECTIVO", "enlace_slug": "ABCDEFGHJK"}),
])
async def test_conteo_checks_refuse_bad_rows(
        sesion, mundo, restriccion, extra):
    await _rechazada(sesion, restriccion, _conteo(mundo, **extra))


async def test_an_open_conteo_needs_its_frozen_thresholds(sesion, mundo):
    sin_umbral = _abierto(mundo, umbral_critico_pesos=None)
    del_todo = _abierto(mundo)

    await _rechazada(sesion, "ck_conteo_umbrales_si_iniciado", sin_umbral)
    await _guardar(sesion, del_todo)


async def test_a_selective_conteo_may_have_no_leader(sesion, mundo):
    await _guardar(sesion, _conteo(mundo, tipo="SELECTIVO", lider_id=None))


async def test_one_open_total_conteo_per_store(sesion, mundo):
    await _guardar(
        sesion, _abierto(mundo), _conteo(mundo),
        _conteo(mundo, estado="CERRADO", snapshot_tomado_en=AHORA,
                umbral_reconteo_pesos=1, umbral_critico_pesos=2))

    await _rechazada(
        sesion, "uq_conteo_total_abierto",
        _abierto(mundo, estado="EN_RECONTEO"))


async def test_other_stores_count_at_the_same_time(sesion, mundo):
    otra = Sucursal(
        id=uuid.uuid4(), nombre=f"S {uuid.uuid4().hex[:8]}",
        codigo_co=codigo_co_unico())
    await _guardar(sesion, otra)

    await _guardar(
        sesion, _abierto(mundo), _abierto(mundo, sucursal_id=otra.id))


async def test_one_automatic_selective_conteo_per_store_and_week(
        sesion, mundo):
    def semanal():
        return _conteo(
            mundo, tipo="SELECTIVO", origen="AUTOMATICO",
            semana_iso="2026-W41")

    await _guardar(sesion, semanal())
    await _rechazada(sesion, "uq_conteo_selectivo_semana", semanal())


async def test_the_link_slug_is_unique(sesion, mundo):
    otra = Sucursal(
        id=uuid.uuid4(), nombre=f"S {uuid.uuid4().hex[:8]}",
        codigo_co=codigo_co_unico())
    await _guardar(sesion, otra, _abierto(mundo, enlace_slug="SLUG123456"))

    await _rechazada(
        sesion, "uq_conteo_enlace_slug",
        _abierto(mundo, sucursal_id=otra.id, enlace_slug="SLUG123456"))


# --- snapshot and locations -------------------------------------------------


def _linea(conteo, mundo, **extra):
    datos = {
        "conteo_id": conteo.id, "referencia_id": mundo["referencia"].id,
        "existencia": Decimal("5"), "costo_unitario": Decimal("1000"),
        "costo_fuente": "BODEGA",
    }
    datos.update(extra)
    return ConteoSnapshotLinea(**datos)


async def test_one_snapshot_line_per_referencia(sesion, mundo):
    conteo = _abierto(mundo)
    await _guardar(sesion, conteo, _linea(
        conteo, mundo, existencia_por_bodega={"BX001": 3, "BX002": 2}))

    await _rechazada(
        sesion, "uq_conteo_snapshot_linea_referencia", _linea(conteo, mundo))
    await _rechazada(
        sesion, "ck_conteo_snapshot_linea_costo_fuente",
        _linea(conteo, mundo, costo_fuente="OTRO"))


def _ubicacion(mundo, codigo="A3", **extra):
    return UbicacionInventario(
        id=uuid.uuid4(), sucursal_id=mundo["sucursal"].id, codigo=codigo,
        nombre=f"Estante {codigo}", origen=extra.pop("origen", "LIDER"),
        **extra)


@pytest.mark.parametrize("codigo", ["a3", " A3", ""])
async def test_a_location_code_is_stored_normalized(sesion, mundo, codigo):
    await _rechazada(
        sesion, "ck_ubicacion_inventario_codigo_normalizado",
        _ubicacion(mundo, codigo))


async def test_a_location_code_is_unique_per_store(sesion, mundo):
    await _guardar(sesion, _ubicacion(mundo))

    await _rechazada(
        sesion, "uq_ubicacion_inventario_codigo", _ubicacion(mundo))
    await _rechazada(
        sesion, "ck_ubicacion_inventario_origen",
        _ubicacion(mundo, "B1", origen="OTRO"))


# --- sessions and people ----------------------------------------------------


def _sesion(conteo, **extra):
    datos = {
        "id": uuid.uuid4(), "conteo_id": conteo.id, "tipo": "PAREJA",
        "token_hash": uuid.uuid4().hex + uuid.uuid4().hex,
        "estado": "CONECTADA", "dispositivo": "ESCRITORIO",
    }
    datos.update(extra)
    return ConteoSesion(**datos)


@pytest.mark.parametrize("restriccion, extra", [
    ("ck_conteo_sesion_tipo", {"tipo": "OTRO", "usuario_id": True}),
    ("ck_conteo_sesion_estado", {"estado": "PERDIDA"}),
    ("ck_conteo_sesion_dispositivo", {"dispositivo": "TV"}),
    ("ck_conteo_sesion_asesor_usuario", {"tipo": "ASESOR"}),
])
async def test_session_checks_refuse_bad_rows(
        sesion, mundo, restriccion, extra):
    conteo = _abierto(mundo)
    await _guardar(sesion, conteo)
    if extra.get("usuario_id"):
        extra = {**extra, "usuario_id": mundo["lider"].id}

    await _rechazada(sesion, restriccion, _sesion(conteo, **extra))


async def test_members_are_ordered_one_to_three(sesion, mundo):
    conteo = _abierto(mundo)
    dispositivo = _sesion(conteo)
    await _guardar(sesion, conteo, dispositivo)

    def miembro(orden):
        return ConteoIntegrante(
            sesion_id=dispositivo.id, orden=orden, nombre="Ana",
            cedula="1020304050")

    await _guardar(sesion, miembro(1), miembro(2))
    await _rechazada(sesion, "uq_conteo_integrante_orden", miembro(2))
    await _rechazada(sesion, "ck_conteo_integrante_orden", miembro(4))


async def test_a_device_token_hash_is_unique(sesion, mundo):
    conteo = _abierto(mundo)
    primera = _sesion(conteo)
    await _guardar(sesion, conteo, primera)

    await _rechazada(
        sesion, "uq_conteo_sesion_token_hash",
        _sesion(conteo, token_hash=primera.token_hash))


# --- readings and reconteo --------------------------------------------------


async def _en_conteo(sesion, mundo):
    conteo = _abierto(mundo)
    ubicacion = _ubicacion(mundo, f"U{uuid.uuid4().hex[:6].upper()}")
    dispositivo = _sesion(conteo)
    await _guardar(sesion, conteo, ubicacion, dispositivo)
    return conteo, ubicacion, dispositivo


def _lectura(contexto, mundo, **extra):
    conteo, ubicacion, dispositivo = contexto
    datos = {
        "id": uuid.uuid4(), "conteo_id": conteo.id,
        "sesion_id": dispositivo.id, "ubicacion_id": ubicacion.id,
        "referencia_id": mundo["referencia"].id,
        "codigo_leido": mundo["referencia"].codigo,
        "cantidad": Decimal("1"), "ronda": 1, "metodo": "ESCANER",
        "leida_en": AHORA,
    }
    datos.update(extra)
    return datos


def _reconteo(conteo, **extra):
    datos = {
        "id": uuid.uuid4(), "conteo_id": conteo.id, "codigo": "R-1",
        "estado": "PENDIENTE", "origen": "UMBRAL",
    }
    datos.update(extra)
    return ConteoReconteo(**datos)


@pytest.mark.parametrize("restriccion, extra", [
    ("ck_conteo_lectura_cantidad", {"cantidad": Decimal("0")}),
    ("ck_conteo_lectura_cantidad", {"cantidad": Decimal("100000")}),
    ("ck_conteo_lectura_metodo", {"metodo": "VOZ"}),
    ("ck_conteo_lectura_ronda_reconteo", {"ronda": 2}),
    ("ck_conteo_lectura_ronda_reconteo", {"ronda": 3}),
])
async def test_reading_checks_refuse_bad_rows(
        sesion, mundo, restriccion, extra):
    contexto = await _en_conteo(sesion, mundo)

    await _rechazada(
        sesion, restriccion,
        ConteoLectura(**_lectura(contexto, mundo, **extra)))


async def test_a_round_one_reading_never_carries_a_reconteo(
        sesion, mundo):
    contexto = await _en_conteo(sesion, mundo)
    reconteo = _reconteo(contexto[0])
    await _guardar(sesion, reconteo)

    await _rechazada(
        sesion, "ck_conteo_lectura_ronda_reconteo",
        ConteoLectura(**_lectura(contexto, mundo, reconteo_id=reconteo.id)))
    await _guardar(sesion, ConteoLectura(**_lectura(
        contexto, mundo, ronda=2, reconteo_id=reconteo.id)))


async def test_a_retried_reading_is_stored_once(sesion, mundo):
    contexto = await _en_conteo(sesion, mundo)
    lote = [_lectura(contexto, mundo), _lectura(contexto, mundo)]
    sentencia = insert(ConteoLectura).on_conflict_do_nothing(
        index_elements=["id"])

    await sesion.execute(sentencia, lote)
    await sesion.execute(sentencia, lote)

    seqs = (await sesion.execute(
        select(ConteoLectura.seq)
        .where(ConteoLectura.conteo_id == contexto[0].id)
        .order_by(ConteoLectura.seq))).scalars().all()
    assert len(seqs) == 2
    assert seqs[0] < seqs[1]


async def test_the_reading_seq_is_server_only(sesion, mundo):
    contexto = await _en_conteo(sesion, mundo)

    with pytest.raises(ProgrammingError, match='column "seq"'):
        async with sesion.begin_nested():
            await sesion.execute(
                insert(ConteoLectura),
                [{**_lectura(contexto, mundo), "seq": 1}])


async def test_one_live_reconteo_per_code(sesion, mundo):
    conteo = _abierto(mundo)
    await _guardar(
        sesion, conteo, _reconteo(conteo, estado="CANCELADO"),
        _reconteo(conteo))

    await _rechazada(
        sesion, "uq_conteo_reconteo_codigo_activo", _reconteo(conteo))


@pytest.mark.parametrize("restriccion, extra", [
    ("ck_conteo_reconteo_estado", {"estado": "LISTO"}),
    ("ck_conteo_reconteo_origen", {"origen": "BOT"}),
    ("ck_conteo_reconteo_sesion_si_asignado", {"estado": "ASIGNADO"}),
    ("ck_conteo_reconteo_sesion_si_asignado", {"estado": "TERMINADO"}),
    ("ck_conteo_reconteo_motivo_si_autorizada", {
        "misma_pareja_autorizada": True}),
])
async def test_reconteo_checks_refuse_bad_rows(
        sesion, mundo, restriccion, extra):
    conteo = _abierto(mundo)
    await _guardar(sesion, conteo)

    await _rechazada(sesion, restriccion, _reconteo(conteo, **extra))


# --- results, access attempts and cascades ----------------------------------


def _resultado(conteo, mundo, **extra):
    datos = {
        "conteo_id": conteo.id, "sucursal_id": mundo["sucursal"].id,
        "referencia_id": mundo["referencia"].id, "codigo": "R-1",
        "bodega_ajuste_id": mundo["bodega"].id,
        "existencia_sistema": Decimal("5"),
        "cantidad_contada": Decimal("3"), "diferencia": Decimal("-2"),
        "costo_unitario": Decimal("1000"), "costo_fuente": "BODEGA",
        "valor_diferencia": Decimal("-2000"), "con_reconteo": False,
        "critico": False, "cerrado_en": AHORA,
    }
    datos.update(extra)
    return ConteoResultado(**datos)


async def test_result_lines_are_consistent_and_unique(sesion, mundo):
    conteo = _abierto(mundo, estado="EN_RECONTEO")
    await _guardar(sesion, conteo, _resultado(conteo, mundo))

    await _rechazada(
        sesion, "uq_conteo_resultado_codigo", _resultado(conteo, mundo))
    await _rechazada(
        sesion, "ck_conteo_resultado_diferencia",
        _resultado(conteo, mundo, codigo="R-2", diferencia=Decimal("2")))
    await _rechazada(
        sesion, "ck_conteo_resultado_costo_fuente",
        _resultado(conteo, mundo, codigo="R-3", costo_fuente="X"))
    await _rechazada(
        sesion, "bodega_ajuste_id",
        _resultado(conteo, mundo, codigo="R-4", bodega_ajuste_id=None))


async def _cuenta(sesion, modelo, conteo_id):
    return (await sesion.execute(
        select(func.count()).select_from(modelo)
        .where(modelo.conteo_id == conteo_id))).scalar_one()


async def test_deleting_a_conteo_cascades_to_its_rows(sesion, mundo):
    contexto = await _en_conteo(sesion, mundo)
    conteo, ubicacion, dispositivo = contexto
    reconteo = _reconteo(conteo, estado="ASIGNADO", sesion_id=dispositivo.id)
    await _guardar(sesion, reconteo)
    await _guardar(
        sesion, _linea(conteo, mundo),
        ConteoIntegrante(
            sesion_id=dispositivo.id, orden=1, nombre="Ana", cedula="1"),
        ConteoLectura(**_lectura(contexto, mundo)),
        ConteoLectura(**_lectura(
            contexto, mundo, ronda=2, reconteo_id=reconteo.id)),
        ConteoAccesoIntento(
            conteo_id=conteo.id, cliente="c" * 64, fallidos=1,
            ventana_inicio=AHORA),
        _resultado(conteo, mundo))

    await sesion.execute(
        text("DELETE FROM conteo WHERE id = :id"), {"id": conteo.id})

    for modelo in (
            ConteoSnapshotLinea, ConteoSesion, ConteoLectura,
            ConteoReconteo, ConteoAccesoIntento, ConteoResultado):
        assert await _cuenta(sesion, modelo, conteo.id) == 0, modelo
    integrantes = (await sesion.execute(text(
        "SELECT count(*) FROM conteo_integrante WHERE sesion_id = :s"),
        {"s": dispositivo.id})).scalar_one()
    assert integrantes == 0
    ubicaciones = (await sesion.execute(text(
        "SELECT count(*) FROM ubicacion_inventario WHERE id = :u"),
        {"u": ubicacion.id})).scalar_one()
    assert ubicaciones == 1
