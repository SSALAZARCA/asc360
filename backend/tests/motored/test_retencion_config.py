"""
Motored "Configuración", T5 (Limpieza): the two purges read their on/off
switch and days from the `retencion_*` keys once per cycle, fall back to the
last known value and then to the env, and a change applies from the next run.
"""
import datetime
import uuid

import pytest

from app.config import settings
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import retencion
from app.motored.services.corridas import retencion_corridas as rc
from tests.motored.conftest import FakeAsyncSession

AHORA = datetime.datetime(
    2026, 10, 14, 12, 0, tzinfo=datetime.timezone.utc)
D = datetime.date(2026, 10, 1)


def _fila(clave, valor):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=D)


class SesionQueFalla(FakeAsyncSession):
    async def execute(self, stmt, params=None):
        raise RuntimeError("db caída")


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", False)
    monkeypatch.setattr(settings, "MOTORED_RETENCION_DIAS", 90)
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", False)
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_DIAS", 45)
    retencion._memoria_config.clear()
    rc._memoria_config.clear()
    yield
    retencion._memoria_config.clear()
    rc._memoria_config.clear()


# --- inventario ------------------------------------------------------------


async def test_inventory_without_rows_reads_the_env(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_RETENCION_DIAS", 120)
    db = FakeAsyncSession(execute_queue=[[]])

    config = await retencion.leer_config(db, AHORA)

    assert config == retencion.ConfigRetencion(True, 120)


async def test_inventory_rows_override_the_env():
    db = FakeAsyncSession(execute_queue=[[
        _fila("retencion_inventario_habilitada", True),
        _fila("retencion_inventario_dias", 60)]])

    config = await retencion.leer_config(db, AHORA)

    assert config == retencion.ConfigRetencion(True, 60)


async def test_inventory_disabled_by_the_app_runs_nothing(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", True)
    db = FakeAsyncSession(execute_queue=[[
        _fila("retencion_inventario_habilitada", False)]])

    assert await retencion.ejecutar_si_corresponde(db, AHORA) is None
    assert len(db.executed_statements) == 1


async def test_inventory_enabled_in_the_app_purges_with_its_days():
    db = FakeAsyncSession(execute_queue=[
        [_fila("retencion_inventario_habilitada", True),
         _fila("retencion_inventario_dias", 60)],
        [],  # hay_job_activo
        [AHORA - datetime.timedelta(hours=25)],  # esta_vencida
        [datetime.date(2026, 9, 15)],  # max(fecha_corte)
        [], [],  # nada que borrar
    ])

    ejecucion = await retencion.ejecutar_si_corresponde(db, AHORA)

    assert ejecucion.fecha_limite == datetime.date(2026, 7, 17)


async def test_inventory_failed_read_keeps_the_last_known_value():
    ok = FakeAsyncSession(execute_queue=[[
        _fila("retencion_inventario_habilitada", True)]])
    await retencion.leer_config(ok, AHORA)

    config = await retencion.leer_config(SesionQueFalla(), AHORA)

    assert config.habilitada is True


async def test_inventory_failed_first_read_uses_the_env(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", True)

    config = await retencion.leer_config(SesionQueFalla(), AHORA)

    assert config == retencion.ConfigRetencion(True, 90)


async def test_the_days_are_fixed_for_the_whole_purge(monkeypatch):
    """A change mid-purge cannot move the limit: the days travel with the
    call, the purge never re-reads them."""
    monkeypatch.setattr(settings, "MOTORED_RETENCION_DIAS", 10)
    db = FakeAsyncSession(execute_queue=[
        [datetime.date(2026, 9, 15)], [], []])

    ejecucion = await retencion.ejecutar_purga_inventario(
        db, now=AHORA, dias=45)

    assert ejecucion.fecha_limite == datetime.date(2026, 8, 1)


# --- corridas --------------------------------------------------------------


async def test_corridas_without_rows_reads_the_env(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", True)
    db = FakeAsyncSession(execute_queue=[[]])

    config = await rc.leer_config(db, AHORA)

    assert config == retencion.ConfigRetencion(True, 45)


async def test_corridas_rows_override_the_env():
    db = FakeAsyncSession(execute_queue=[[
        _fila("retencion_corridas_habilitada", True),
        _fila("retencion_corridas_dias", 14)]])

    config = await rc.leer_config(db, AHORA)

    assert config == retencion.ConfigRetencion(True, 14)


async def test_corridas_disabled_by_the_app_runs_nothing(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", True)
    db = FakeAsyncSession(execute_queue=[[
        _fila("retencion_corridas_habilitada", False)]])

    assert await rc.ejecutar_si_corresponde(db, AHORA) is None
    assert len(db.executed_statements) == 1


async def test_corridas_failed_read_keeps_the_last_known_value():
    ok = FakeAsyncSession(execute_queue=[[
        _fila("retencion_corridas_habilitada", True),
        _fila("retencion_corridas_dias", 14)]])
    await rc.leer_config(ok, AHORA)

    config = await rc.leer_config(SesionQueFalla(), AHORA)

    assert config == retencion.ConfigRetencion(True, 14)


async def test_corridas_cutoff_uses_the_days_of_the_app():
    class Db(FakeAsyncSession):
        async def commit(self):
            pass

    db = Db(execute_queue=[
        [_fila("retencion_corridas_habilitada", True),
         _fila("retencion_corridas_dias", 14)],
        [None],  # esta_vencida
        [],  # ningún id que borrar
    ])

    await rc.ejecutar_si_corresponde(db, AHORA)

    ledger = [o for o in db.added if o.tabla == "corrida"][0]
    assert ledger.fecha_limite == datetime.date(2026, 9, 30)
