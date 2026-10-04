"""
Motored "Configuración": `leer_con_memoria`, the once-per-cycle read the
background jobs use. A stored row wins over the fallback, a failed read keeps
the last known value (then the fallback) and never raises.
"""
import datetime
import uuid

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
from tests.motored.conftest import FakeAsyncSession

HOY = datetime.date(2026, 10, 14)
DIAS = "retencion_inventario_dias"
HAB = "retencion_inventario_habilitada"
FALLBACKS = {HAB: False, DIAS: 90}


def _fila(clave, valor, desde=datetime.date(2026, 10, 1)):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde)


class SesionQueFalla(FakeAsyncSession):
    async def execute(self, stmt, params=None):
        raise RuntimeError("db caída")


async def test_without_rows_every_key_gets_its_fallback():
    db = FakeAsyncSession(execute_queue=[[]])

    valores = await parametros.leer_con_memoria(db, HOY, FALLBACKS, {})

    assert valores == FALLBACKS


async def test_a_stored_row_wins_over_the_fallback():
    db = FakeAsyncSession(execute_queue=[[_fila(DIAS, 60)]])

    valores = await parametros.leer_con_memoria(db, HOY, FALLBACKS, {})

    assert valores == {HAB: False, DIAS: 60}
    assert len(db.executed_statements) == 1


async def test_a_stored_value_that_breaks_the_rule_falls_back(caplog):
    db = FakeAsyncSession(execute_queue=[[_fila(DIAS, 3)]])

    valores = await parametros.leer_con_memoria(db, HOY, FALLBACKS, {})

    assert valores[DIAS] == 90
    assert DIAS in caplog.text


async def test_the_last_read_is_remembered_for_the_next_failure():
    memoria = {}
    ok = FakeAsyncSession(execute_queue=[[_fila(DIAS, 60)]])
    await parametros.leer_con_memoria(ok, HOY, FALLBACKS, memoria)

    roto = SesionQueFalla()
    valores = await parametros.leer_con_memoria(
        roto, HOY, FALLBACKS, memoria)

    assert valores == {HAB: False, DIAS: 60}
    assert roto.rolled_back is True


async def test_a_failure_without_memory_uses_the_fallbacks():
    valores = await parametros.leer_con_memoria(
        SesionQueFalla(), HOY, FALLBACKS, {})

    assert valores == FALLBACKS


async def test_a_session_that_cannot_roll_back_still_does_not_raise():
    class SinRollback:
        async def execute(self, stmt, params=None):
            raise RuntimeError("boom")

    valores = await parametros.leer_con_memoria(
        SinRollback(), HOY, FALLBACKS, {})

    assert valores == FALLBACKS


async def test_the_read_uses_the_first_day_of_the_month():
    db = FakeAsyncSession(execute_queue=[[_fila(DIAS, 60, datetime.date(
        2026, 10, 1))]])

    await parametros.leer_con_memoria(db, datetime.date(2026, 10, 31),
                                      FALLBACKS, {})

    assert "2026-10-01" in str(db.executed_statements[0].compile(
        compile_kwargs={"literal_binds": True}))
