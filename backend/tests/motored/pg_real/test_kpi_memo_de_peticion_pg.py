"""
The per-request memo against a real Postgres (odd/motored-kpis-velocidad, S1): inside a
`memo_de_peticion` block each KPI read asks for the state of the summaries ONCE, and the answer is the
same as without it.
"""
import pytest
from sqlalchemy import event

from app.config import settings
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import MESES, _mundo
from tests.motored.pg_real.test_kpi_resumen_pg import URL, pytestmark, sesion  # noqa: F401


class _Sentencias:
    """Counts the statements the session sends and, apart, the reads of the summaries' state."""

    def __init__(self, db):
        self.motor = db.bind.sync_engine
        self.total = self.estado = 0

    def __enter__(self):
        event.listen(self.motor, "before_cursor_execute", self._contar)
        return self

    def __exit__(self, *_):
        event.remove(self.motor, "before_cursor_execute", self._contar)

    def _contar(self, conn, cursor, sentencia, *resto):
        self.total += 1
        self.estado += "FROM kpi_resumen_estado" in sentencia


def _llamadas(db, filtro, cedula):
    return {
        "ventas": lambda: kpis.calcular_kpis_ventas(db, filtro),
        "tiendas": lambda: kpis.calcular_kpis_tiendas(db, filtro),
        "asesores": lambda: kpis.calcular_kpis_asesores(db, filtro),
        "detalle": lambda: kpis.calcular_kpis_asesor_detalle(db, filtro, cedula),
        "opciones_asesores": lambda: kpis.calcular_opciones_asesores(db, filtro),
        "comisiones": lambda: kpis.calcular_kpis_comisiones(db, filtro),
    }


async def test_the_state_of_the_summaries_is_read_once_per_request(sesion, monkeypatch):
    mundo = await _mundo(sesion, False)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id, mundo.s2.id])
    cedula = (await kpis.calcular_opciones_asesores(sesion, filtro))["asesores"][0]["cedula"]

    for nombre, llamar in _llamadas(sesion, filtro, cedula).items():
        with _Sentencias(sesion) as sin_memo:
            esperado = await llamar()
        with lectura.memo_de_peticion(sesion), _Sentencias(sesion) as con_memo:
            obtenido = await llamar()
        assert obtenido == esperado, nombre
        assert con_memo.estado == 1, nombre
        assert sin_memo.estado > 1 or nombre == "comisiones", nombre
        assert con_memo.total <= sin_memo.total - (sin_memo.estado - 1), nombre  # the repeats go; so may other lookups


async def test_the_memo_does_not_hide_a_change_made_after_the_block(sesion, monkeypatch):
    from app.motored.services import kpi_resumen as k

    await _mundo(sesion, False)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    with lectura.memo_de_peticion(sesion):
        assert await lectura.usar_resumen(sesion) is True
        await k.marcar_sucio(sesion)
        assert await lectura.usar_resumen(sesion) is True  # one request, one answer
    assert await lectura.usar_resumen(sesion) is False
