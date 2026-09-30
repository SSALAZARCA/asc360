"""
Motored Pedidos F3 "Motor", S7 (sdd/motored-pedidos-motor, ADR-11): las
cargas EXCEL de DEMANDA_PERDIDA que el cargador lee también se vinculan a la
corrida (`corrida_carga`), para que una corrida CERRADA bloquee su anulación.

Antes de S7 sólo se vinculaban las cinco cargas del preflight. Acá se prueba
la consulta (SQL literal) y el mapeo del tipo; el recorrido real, con la
guarda de anulación, corre en `pg_real/test_corridas_api_pg.py`.
"""
import datetime
import uuid

from sqlalchemy.dialects import postgresql

from app.motored.models.corrida_carga import CorridaCarga
from app.motored.services.corridas import cargas_perdida as cp
from app.motored.services.corridas import persistencia as pe
from tests.motored.conftest import FakeAsyncSession

CORTE = datetime.date(2026, 9, 21)
CARGA_A, CARGA_B = uuid.UUID(int=1), uuid.UUID(int=2)


def _sql(sentencia) -> str:
    return str(sentencia.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))


def test_only_excel_cargas_that_are_not_annulled_are_linked():
    sql = _sql(cp.consulta_cargas_perdida(CORTE, con_m0=False))

    assert "carga_archivo.origen = 'EXCEL'" in sql
    assert "carga_archivo.estado != 'ANULADO'" in sql
    assert "demanda_perdida.origen = 'EXCEL'" in sql


def test_the_query_returns_each_carga_once():
    sql = _sql(cp.consulta_cargas_perdida(CORTE, con_m0=False))

    assert sql.startswith("SELECT DISTINCT demanda_perdida.carga_id")


def test_without_the_current_month_the_window_ends_before_it():
    sql = _sql(cp.consulta_cargas_perdida(CORTE, con_m0=False))

    assert "demanda_perdida.fecha >= '2026-03-01'" in sql
    assert "demanda_perdida.fecha < '2026-09-01'" in sql


def test_with_the_current_month_the_window_ends_at_the_corte():
    sql = _sql(cp.consulta_cargas_perdida(CORTE, con_m0=True))

    assert "demanda_perdida.fecha >= '2026-03-01'" in sql
    assert "demanda_perdida.fecha <= '2026-09-21'" in sql


def test_the_window_follows_the_corte_across_a_year_boundary():
    sql = _sql(cp.consulta_cargas_perdida(
        datetime.date(2026, 2, 15), con_m0=False))

    assert "demanda_perdida.fecha >= '2025-08-01'" in sql
    assert "demanda_perdida.fecha < '2026-02-01'" in sql


async def test_the_ids_come_back_as_a_sorted_tuple():
    db = FakeAsyncSession(execute_queue=[[CARGA_B, CARGA_A]])

    ids = await cp.cargas_demanda_perdida_excel(db, CORTE, con_m0=False)

    assert ids == (CARGA_A, CARGA_B)


async def test_no_lost_demand_cargas_is_an_empty_tuple():
    db = FakeAsyncSession(execute_queue=[[]])

    ids = await cp.cargas_demanda_perdida_excel(db, CORTE, con_m0=True)

    assert ids == ()
    assert "'2026-09-21'" in _sql(db.executed_statements[0])


def test_a_lost_demand_carga_is_registered_with_its_own_tipo():
    db = FakeAsyncSession()
    corrida_id = uuid.uuid4()

    pe.registrar_cargas(
        db, corrida_id,
        {"ventas": (CARGA_A,), "demanda_perdida": (CARGA_B,)})

    vinculos = {(v.carga_id, v.tipo) for v in db.added_of_type(CorridaCarga)}
    assert vinculos == {
        (CARGA_A, "VENTAS"), (CARGA_B, "DEMANDA_PERDIDA")}
