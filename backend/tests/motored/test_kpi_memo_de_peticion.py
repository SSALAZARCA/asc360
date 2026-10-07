"""
The per-request memo of the KPI reads (odd/motored-kpis-velocidad, S1): inside a `memo_de_peticion`
block a value is read once; outside of it nothing is remembered.
"""
from types import SimpleNamespace

from app.motored.services import kpi_resumen_lectura as lectura


class _Sesion:
    """What the memo needs of an AsyncSession: its `info` dict."""

    def __init__(self):
        self.info = {}


def _lector():
    llamadas = []

    async def obtener():
        llamadas.append(1)
        return len(llamadas)

    return llamadas, obtener


async def test_a_value_is_read_once_per_block():
    db, (llamadas, obtener) = _Sesion(), _lector()
    with lectura.memo_de_peticion(db):
        assert [await lectura.recordado(db, "x", obtener) for _ in range(3)] == [1, 1, 1]
    assert len(llamadas) == 1


async def test_nothing_is_remembered_outside_the_block_nor_after_it():
    db, (llamadas, obtener) = _Sesion(), _lector()
    assert [await lectura.recordado(db, "x", obtener) for _ in range(2)] == [1, 2]
    with lectura.memo_de_peticion(db):
        await lectura.recordado(db, "x", obtener)
    assert db.info == {}
    assert await lectura.recordado(db, "x", obtener) == 4


async def test_keys_are_independent_and_an_inner_block_shares_the_outer_one():
    db, (llamadas, obtener) = _Sesion(), _lector()
    with lectura.memo_de_peticion(db):
        assert await lectura.recordado(db, "a", obtener) == 1
        with lectura.memo_de_peticion(db):
            assert await lectura.recordado(db, "a", obtener) == 1
            assert await lectura.recordado(db, "b", obtener) == 2
        assert await lectura.recordado(db, "b", obtener) == 2  # the inner exit did not drop the outer memo


async def test_a_none_value_is_remembered_too():
    db = _Sesion()
    llamadas = []

    async def obtener():
        llamadas.append(1)

    with lectura.memo_de_peticion(db):
        assert await lectura.recordado(db, "x", obtener) is None
        assert await lectura.recordado(db, "x", obtener) is None
    assert len(llamadas) == 1


async def test_the_block_is_released_when_the_work_fails():
    db = _Sesion()
    try:
        with lectura.memo_de_peticion(db):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert db.info == {}


async def test_a_session_without_info_just_reads_every_time():
    db, (llamadas, obtener) = SimpleNamespace(), _lector()
    with lectura.memo_de_peticion(db):
        assert [await lectura.recordado(db, "x", obtener) for _ in range(2)] == [1, 2]
