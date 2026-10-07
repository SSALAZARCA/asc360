"""
Ventas and Tiendas tabs without repeated reads (odd/motored-kpis-velocidad, S4), against a real Postgres:
the asesores cube of the network is read once (not once for the company gauge and again for the
cumplimiento), the Tecnired client counts take one statement, and the asesores' names are not read by the
tabs that never show them. The figures are the golden ones (`test_kpis_golden_pg`).
"""
import pytest
from sqlalchemy import event

from app.config import settings
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import MESES, _mundo
from tests.motored.pg_real.test_kpi_resumen_pg import URL, pytestmark, sesion  # noqa: F401


class _Sentencias:
    def __init__(self, db):
        self.motor = db.bind.sync_engine
        self.texto = []

    def __enter__(self):
        event.listen(self.motor, "before_cursor_execute", self._guardar)
        return self

    def __exit__(self, *_):
        event.remove(self.motor, "before_cursor_execute", self._guardar)

    def _guardar(self, conn, cursor, sentencia, *resto):
        self.texto.append(" ".join(sentencia.split()))

    def cuantas(self, *fragmentos):
        return sum(all(f in s for f in fragmentos) for s in self.texto)


@pytest.mark.parametrize("filtrar_tiendas", [False, True], ids=["all-stores", "store-filter"])
async def test_ventas_reads_each_cube_once(sesion, monkeypatch, filtrar_tiendas):
    mundo = await _mundo(sesion, False)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    tiendas = [mundo.s1.id] if filtrar_tiendas else None
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, tiendas)

    with _Sentencias(sesion) as sentencias:
        await kpis.calcular_kpis_ventas(sesion, filtro)

    cubos_de_asesor = sentencias.cuantas("FROM kpi_venta_mes", "LEFT OUTER JOIN vendedor")
    # The company gauge (the filter's stores) and, only when stores are filtered, the network's for cumplimiento.
    assert cubos_de_asesor == (2 if filtrar_tiendas else 1)
    assert sentencias.cuantas("count(distinct(kpi_cliente_mes.cliente_norm))") == 1  # total and per month, together
    assert sentencias.cuantas("FROM vendedor WHERE vendedor.cedula IS NOT NULL") == 0  # names nobody shows


async def test_tiendas_does_not_read_the_asesores_names(sesion, monkeypatch):
    mundo = await _mundo(sesion, False)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id, mundo.s2.id])

    with _Sentencias(sesion) as sentencias:
        await kpis.calcular_kpis_tiendas(sesion, filtro)

    assert sentencias.cuantas("FROM vendedor WHERE vendedor.cedula IS NOT NULL") == 0
    assert sentencias.cuantas("FROM sucursal WHERE sucursal.id IN") <= 2  # the cube's stores, then the budgets' missing ones
