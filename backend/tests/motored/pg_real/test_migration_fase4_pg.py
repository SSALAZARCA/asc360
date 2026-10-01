"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B1, ADR-2): la
migración M1 `a3f7c1d9e642` contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`). A
diferencia del resto de `pg_real`, estas pruebas NO usan la base ya migrada:
cada una crea su propia base descartable en el mismo servidor, la migra con
la API de Alembic (en la versión anterior, M0 = `d9a2b6e04f71`, o hasta
`head`) y la borra al terminar. Hace falta el permiso `CREATE DATABASE`.

Cubre el upgrade, el backfill de F3 (sólo la columna nueva y los eventos
`migrado_f3`), los CHECK y el UNIQUE de F4-13, el downgrade y que los
modelos coinciden con el DDL (`alembic check` acotado a lo de M1).
"""
import asyncio
import datetime
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.motored.database import MotoredBase
import app.motored.models  # noqa: F401  (registra los modelos)

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

_RAIZ = Path(__file__).resolve().parents[3]
M0, M1 = "d9a2b6e04f71", "a3f7c1d9e642"
_TABLAS_M1 = ("corrida_linea_historial", "pedido_evento", "corrida_envio")
CORTE = datetime.date(2026, 9, 21)
AHORA = datetime.datetime(2026, 9, 22, 10, 0, tzinfo=datetime.timezone.utc)

P, U = uuid.uuid4(), uuid.uuid4()
S1, S2, S3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
C_BOR, C_CER, C_ESC, C_PEN, C_ANU = (uuid.uuid4() for _ in range(5))


# --- Infraestructura -------------------------------------------------------


def _correr(corrutina):
    return asyncio.run(corrutina)


async def _admin(sentencia):
    motor = create_async_engine(
        URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conexion:
        await conexion.execute(text(sentencia))
    await motor.dispose()


async def _sql(url, sentencia, **params):
    """Ejecuta y confirma; devuelve las filas si la sentencia las produce."""
    motor = create_async_engine(url, poolclass=NullPool)
    try:
        async with motor.begin() as conexion:
            resultado = await conexion.execute(text(sentencia), params)
            return resultado.all() if resultado.returns_rows else []
    finally:
        await motor.dispose()


def _filas(url, sentencia, **params):
    return _correr(_sql(url, sentencia, **params))


def _alembic(accion, destino):
    config = Config()
    config.set_main_option(
        "script_location", str(_RAIZ / "alembic_motored"))
    getattr(command, accion)(config, destino)


@pytest.fixture
def base(monkeypatch):
    nombre = f"mig_f4_{uuid.uuid4().hex[:10]}"
    _correr(_admin(f'CREATE DATABASE "{nombre}"'))
    url = make_url(URL).set(database=nombre).render_as_string(
        hide_password=False)
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", url)
    yield url
    _correr(_admin(f'DROP DATABASE "{nombre}" WITH (FORCE)'))


def _existentes(url, tabla):
    filas = _filas(
        url,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t", t=tabla)
    return {f[0] for f in filas}


def _version(url):
    return _filas(url, "SELECT version_num FROM alembic_version_motored")[0][0]


# --- Datos de F3 (antes de M1, con SQL crudo) -------------------------------


def _sembrar_f3(url):
    _filas(url, "INSERT INTO proveedor(id, codigo, nombre, es_principal, "
           "activa) VALUES (:p, 'HMCL', 'HMCL', true, true)", p=P)
    _filas(url, "INSERT INTO usuario(id, nombre, role, activo, email, "
           "hashed_password) VALUES (:u, 'Ana', 'ADMIN', true, "
           "'ana@x.co', 'x')", u=U)
    for sid, nombre in ((S1, "Uno"), (S2, "Dos"), (S3, "Tres")):
        _filas(url, "INSERT INTO sucursal(id, nombre, dias_seguridad, "
               "activa) VALUES (:s, :n, 1, true)", s=sid, n=nombre)
    corridas = (
        (C_BOR, "PED-1", "BORRADOR", False, (
            (S1, "OK"), (S2, "FALLIDA"), (S3, "OMITIDA"))),
        (C_CER, "PED-2", "CERRADA", False, ((S1, "OK"), (S2, "OK"))),
        (C_ESC, "ESC-1", "BORRADOR", True, ((S1, "OK"),)),
        (C_PEN, "PED-3", "PENDIENTE", False, ((S1, "PENDIENTE"),)),
        (C_ANU, "PED-4", "ANULADA", False, ((S1, "OK"),)),
    )
    for cid, codigo, estado, escenario, tiendas in corridas:
        _filas(url, "INSERT INTO corrida(id, codigo, proveedor_id, "
               "fecha_corte, estado, es_escenario, cerrada_por, cerrada_en) "
               "VALUES (:c, :k, :p, :f, :e, :x, :u, :t)",
               c=cid, k=codigo, p=P, f=CORTE, e=estado, x=escenario,
               u=U if estado == "CERRADA" else None,
               t=AHORA if estado == "CERRADA" else None)
        for orden, (sid, est) in enumerate(tiendas, 1):
            _filas(url, "INSERT INTO corrida_sucursal(corrida_id, "
                   "sucursal_id, orden, estado) VALUES (:c, :s, :o, :e)",
                   c=cid, s=sid, o=orden, e=est)


def _estados_pedido(url):
    filas = _filas(
        url, "SELECT corrida_id, sucursal_id, estado_pedido "
        "FROM corrida_sucursal")
    return {(f[0], f[1]): f[2] for f in filas}


@pytest.fixture
def migrada(base):
    _alembic("upgrade", M0)
    _sembrar_f3(base)
    _alembic("upgrade", M1)
    return base


# --- Upgrade y downgrade ---------------------------------------------------


def test_upgrade_adds_the_column_and_the_three_tables(base):
    _alembic("upgrade", M0)
    assert "estado_pedido" not in _existentes(base, "corrida_sucursal")

    _alembic("upgrade", M1)

    assert "estado_pedido" in _existentes(base, "corrida_sucursal")
    for tabla in _TABLAS_M1:
        assert _existentes(base, tabla), tabla
    assert _version(base) == M1


def test_downgrade_removes_everything_m1_added_and_upgrade_repeats(base):
    _alembic("upgrade", M1)

    _alembic("downgrade", M0)

    assert "estado_pedido" not in _existentes(base, "corrida_sucursal")
    for tabla in _TABLAS_M1:
        assert _existentes(base, tabla) == set(), tabla
    assert _version(base) == M0
    _alembic("upgrade", M1)
    assert "estado_pedido" in _existentes(base, "corrida_sucursal")


def test_downgrade_with_f4_data_drops_it_without_touching_f3_rows(migrada):
    _alembic("downgrade", M0)

    assert len(_filas(migrada, "SELECT 1 FROM corrida")) == 5
    assert len(_filas(migrada, "SELECT 1 FROM corrida_sucursal")) == 8


# --- Backfill ----------------------------------------------------------------


def test_backfill_sets_borrador_on_ok_tiendas_of_real_borrador_corridas(
        migrada):
    estados = _estados_pedido(migrada)

    assert estados[(C_BOR, S1)] == "BORRADOR"


def test_backfill_closes_the_ok_tiendas_of_f3_cerrada_corridas(migrada):
    estados = _estados_pedido(migrada)

    assert estados[(C_CER, S1)] == "CERRADO"
    assert estados[(C_CER, S2)] == "CERRADO"


def test_failed_omitted_scenario_and_uncalculated_tiendas_stay_null(
        migrada):
    estados = _estados_pedido(migrada)

    assert estados[(C_BOR, S2)] is None  # FALLIDA
    assert estados[(C_BOR, S3)] is None  # OMITIDA
    assert estados[(C_ESC, S1)] is None  # escenario
    assert estados[(C_PEN, S1)] is None  # PENDIENTE
    assert estados[(C_ANU, S1)] is None  # ANULADA


def test_backfill_writes_a_migrado_event_per_closed_tienda(migrada):
    eventos = _filas(
        migrada, "SELECT corrida_id, sucursal_id, evento, usuario_id, "
        "detalle ->> 'migrado_f3', detalle ->> 'cerrada_por', creado_en "
        "FROM pedido_evento ORDER BY sucursal_id")

    assert len(eventos) == 2
    for corrida, _, evento, usuario, migrado, cerro, creado in eventos:
        assert corrida == C_CER and evento == "CERRADO"
        assert usuario is None
        assert migrado == "true" and cerro == str(U)
        assert creado == AHORA


def test_backfill_changes_no_existing_value_and_corrida_estado(migrada):
    corridas = dict(_filas(migrada, "SELECT id, estado FROM corrida"))
    tiendas = _filas(
        migrada, "SELECT estado, count(*) FROM corrida_sucursal "
        "GROUP BY estado ORDER BY estado")

    assert corridas[C_CER] == "CERRADA" and corridas[C_BOR] == "BORRADOR"
    assert tiendas == [("FALLIDA", 1), ("OK", 5), ("OMITIDA", 1),
                       ("PENDIENTE", 1)]


def test_the_new_tables_start_empty_except_for_migrado_events(migrada):
    for tabla in ("corrida_linea_historial", "corrida_envio"):
        assert _filas(migrada, f"SELECT 1 FROM {tabla}") == []


# --- CHECK, UNIQUE y FK ----------------------------------------------------


def _fallo(url, sentencia, **params):
    with pytest.raises(IntegrityError) as error:
        _filas(url, sentencia, **params)
    return str(error.value.orig)


def test_estado_pedido_rejects_unknown_values(migrada):
    mensaje = _fallo(
        migrada, "UPDATE corrida_sucursal SET estado_pedido = 'ANULADO' "
        "WHERE corrida_id = :c AND sucursal_id = :s", c=C_BOR, s=S1)

    assert "ck_corrida_sucursal_estado_pedido" in mensaje


def _evento(url, evento, motivo=None):
    return _filas(
        url, "INSERT INTO pedido_evento(corrida_id, sucursal_id, evento, "
        "motivo, usuario_id) VALUES (:c, :s, :e, :m, :u)",
        c=C_BOR, s=S1, e=evento, m=motivo, u=U)


def test_pedido_evento_accepts_the_four_events_and_rejects_others(migrada):
    for evento in ("CERRADO", "ENVIADO", "ENVIO_CORREGIDO"):
        _evento(migrada, evento)
    _evento(migrada, "REABIERTO", "Corrección")

    assert "ck_pedido_evento_evento" in _fallo(
        migrada, "INSERT INTO pedido_evento(corrida_id, sucursal_id, "
        "evento) VALUES (:c, :s, 'ANULADO')", c=C_BOR, s=S1)


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_a_reopen_event_needs_a_non_blank_motivo(migrada, motivo):
    with pytest.raises(IntegrityError) as error:
        _evento(migrada, "REABIERTO", motivo)

    assert "ck_pedido_evento_reabierto_motivo" in str(error.value.orig)


def _envio(url, corrida, numero="12345", sucursal=S1):
    return _filas(
        url, "INSERT INTO corrida_envio(corrida_id, sucursal_id, "
        "proveedor_id, fecha_corte, numero_pedido_proveedor, fecha_envio, "
        "enviada_por) VALUES (:c, :s, :p, :f, :n, :f, :u)",
        c=corrida, s=sucursal, p=P, f=CORTE, n=numero, u=U)


def test_an_envio_cannot_have_a_blank_order_number(migrada):
    with pytest.raises(IntegrityError) as error:
        _envio(migrada, C_BOR, "   ")

    assert "ck_corrida_envio_numero" in str(error.value.orig)


def test_f4_13_one_envio_per_proveedor_corte_and_tienda(migrada):
    _envio(migrada, C_BOR)

    with pytest.raises(IntegrityError) as error:
        _envio(migrada, C_CER)

    assert "uq_corrida_envio_corte_sucursal" in str(error.value.orig)


def test_the_same_tienda_in_other_corte_or_another_tienda_is_allowed(
        migrada):
    _envio(migrada, C_BOR)
    _envio(migrada, C_CER, sucursal=S2)

    assert len(_filas(migrada, "SELECT 1 FROM corrida_envio")) == 2


def test_a_corrida_with_an_envio_cannot_be_deleted(migrada):
    _envio(migrada, C_BOR)

    with pytest.raises(IntegrityError) as error:
        _filas(migrada, "DELETE FROM corrida WHERE id = :c", c=C_BOR)

    assert "corrida_envio" in str(error.value.orig)


def test_deleting_a_corrida_cascades_to_its_events(migrada):
    _evento(migrada, "CERRADO")
    _filas(migrada, "DELETE FROM corrida WHERE id = :c", c=C_BOR)

    assert _filas(
        migrada, "SELECT 1 FROM pedido_evento WHERE corrida_id = :c",
        c=C_BOR) == []


# --- Los modelos coinciden con el DDL (alembic check, acotado) ------------


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


def test_the_models_match_the_ddl_of_m1(base):
    _alembic("upgrade", M1)

    diferencias = _correr(_diferencias(base))

    propias = [
        d for d in diferencias
        if any(t in str(d) for t in (*_TABLAS_M1, "estado_pedido"))]
    assert propias == []
