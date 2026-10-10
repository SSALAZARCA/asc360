"""
Inventory counts, test counts against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`; odd/tasks/motored-conteo-prueba.md).

- the migration adds `conteo.es_prueba` and rebuilds the open-count index
  with `AND NOT es_prueba`, and its downgrade undoes both;
- the index never lets a test count block a real one;
- `borrar_conteo_prueba` deletes a test count and every row keyed to it,
  keeps the store's locations and never deletes a real count.

Reuses the world and row builders of `test_conteo_modelos_pg.py`.
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.motored.models.conteo import Conteo
from app.motored.models.conteo_acceso_intento import ConteoAccesoIntento
from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.conteo_resultado import ConteoResultado
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.models.conteo_snapshot_linea import ConteoSnapshotLinea
from app.motored.services.conteos import errores, snapshot
from tests.motored.pg_real.test_conteo_modelos_pg import (  # noqa: F401
    AHORA, URL, _abierto, _alembic, _consultar, _correr, _cuenta,
    _guardar, _lectura, _linea, _rechazada, _reconteo, _resultado,
    _sesion, _ubicacion, base_vacia, mundo, sesion,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

PREVIA = "c4e8a2d6f931"
PRUEBA = "f4b8d2a6c917"
INDICE = "uq_conteo_total_abierto"


# --- migration --------------------------------------------------------------


def _columna(url):
    return _correr(_consultar(
        url, "SELECT column_default, is_nullable FROM "
        "information_schema.columns WHERE table_name = 'conteo' "
        "AND column_name = 'es_prueba'"))


def _indice(url):
    return _correr(_consultar(
        url, f"SELECT indexdef FROM pg_indexes WHERE indexname = '{INDICE}'"
    ))[0][0]


def test_the_migration_adds_the_flag_and_rebuilds_the_index(base_vacia):
    _alembic("upgrade", PRUEBA)
    assert _columna(base_vacia) == [("false", "NO")]
    assert "NOT es_prueba" in _indice(base_vacia)

    _alembic("downgrade", PREVIA)
    assert _columna(base_vacia) == []
    assert "es_prueba" not in _indice(base_vacia)

    _alembic("upgrade", "head")
    assert "NOT es_prueba" in _indice(base_vacia)


# --- the open-count index ---------------------------------------------------


async def test_a_test_count_never_blocks_a_real_one(sesion, mundo):
    await _guardar(
        sesion, _abierto(mundo, es_prueba=True),
        _abierto(mundo, es_prueba=True), _abierto(mundo))

    await _rechazada(sesion, INDICE, _abierto(mundo, estado="EN_RECONTEO"))


async def test_a_new_count_defaults_to_real(sesion, mundo):
    conteo = _abierto(mundo)
    await _guardar(sesion, conteo)

    valor = await sesion.scalar(
        select(Conteo.es_prueba).where(Conteo.id == conteo.id))
    assert valor is False


async def test_the_start_check_ignores_open_test_counts(sesion, mundo):
    await _guardar(sesion, _abierto(mundo, es_prueba=True))
    real = _abierto(mundo, estado="PROGRAMADO", snapshot_tomado_en=None)
    await _guardar(sesion, real)

    await snapshot._exigir_sin_total_abierto(sesion, real)

    await _guardar(sesion, _abierto(mundo))
    with pytest.raises(errores.ConteoTotalAbierto):
        await snapshot._exigir_sin_total_abierto(sesion, real)


# --- delete -----------------------------------------------------------------


async def _con_todo(sesion, mundo, conteo):
    """A test conteo with a row in every table keyed to it."""
    ubicacion = _ubicacion(mundo, f"U{uuid.uuid4().hex[:6].upper()}")
    dispositivo = _sesion(conteo)
    await _guardar(sesion, conteo, ubicacion, dispositivo)
    contexto = (conteo, ubicacion, dispositivo)
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
    return dispositivo, ubicacion


async def test_deleting_a_test_count_removes_every_row(sesion, mundo):
    conteo = _abierto(mundo, estado="EN_RECONTEO", es_prueba=True)
    dispositivo, ubicacion = await _con_todo(sesion, mundo, conteo)

    await snapshot.borrar_conteo_prueba(sesion, conteo.id)

    for modelo in (
            ConteoSnapshotLinea, ConteoSesion, ConteoLectura,
            ConteoReconteo, ConteoAccesoIntento, ConteoResultado):
        assert await _cuenta(sesion, modelo, conteo.id) == 0, modelo
    integrantes = await sesion.scalar(text(
        "SELECT count(*) FROM conteo_integrante WHERE sesion_id = :s"
    ).bindparams(s=dispositivo.id))
    assert integrantes == 0
    assert await sesion.scalar(text(
        "SELECT count(*) FROM conteo WHERE id = :c"
    ).bindparams(c=conteo.id)) == 0
    assert await sesion.scalar(text(
        "SELECT count(*) FROM ubicacion_inventario WHERE id = :u"
    ).bindparams(u=ubicacion.id)) == 1


async def test_a_real_count_is_never_deleted(sesion, mundo):
    conteo = _abierto(mundo, estado="CERRADO")
    await _guardar(sesion, conteo, _linea(conteo, mundo))

    with pytest.raises(errores.NoEsPrueba):
        await snapshot.borrar_conteo_prueba(sesion, conteo.id)

    assert await _cuenta(sesion, ConteoSnapshotLinea, conteo.id) == 1


async def test_a_missing_count_is_not_found(sesion):
    with pytest.raises(errores.ConteoNoEncontrado):
        await snapshot.borrar_conteo_prueba(sesion, uuid.uuid4())
