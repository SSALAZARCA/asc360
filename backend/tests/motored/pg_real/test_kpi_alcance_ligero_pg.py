"""
The light reads of the Asesores tab against a real Postgres (odd/motored-kpis-velocidad, S2): the
options of the "Asesor" filter and the detail of one asesor do not run the reads whose figures they
never look at, and `solo_unicos` counts the same clients as the full read.
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
    def __init__(self, db):
        self.motor = db.bind.sync_engine
        self.texto = []

    def __enter__(self):
        event.listen(self.motor, "before_cursor_execute", self._guardar)
        return self

    def __exit__(self, *_):
        event.remove(self.motor, "before_cursor_execute", self._guardar)

    def _guardar(self, conn, cursor, sentencia, *resto):
        self.texto.append(sentencia)

    def con(self, fragmento):
        return [s for s in self.texto if fragmento in s]


@pytest.mark.parametrize("resumen", [False, True], ids=["live", "summary"])
async def test_the_options_read_only_the_cube_and_the_people(sesion, monkeypatch, resumen):
    mundo = await _mundo(sesion, False)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", resumen)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id, mundo.s2.id])

    with _Sentencias(sesion) as sentencias:
        opciones = await kpis.calcular_opciones_asesores(sesion, filtro)

    assert opciones["asesores"]
    assert not sentencias.con("row_number")  # no top 5 clients
    assert not sentencias.con("kpi_cliente_mes") and not sentencias.con("kpi_factura_firma")
    assert not sentencias.con("max(kpi_inventario_corte") and not sentencias.con("max(inventario_detalle")  # no cost cut
    assert not sentencias.con("unnest")  # no invoices


@pytest.mark.parametrize("resumen", [False, True], ids=["live", "summary"])
async def test_the_detail_does_not_rank_the_clients(sesion, monkeypatch, resumen):
    mundo = await _mundo(sesion, False)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", resumen)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id, mundo.s2.id])
    cedula = (await kpis.calcular_opciones_asesores(sesion, filtro))["asesores"][0]["cedula"]

    with _Sentencias(sesion) as sentencias:
        detalle = await kpis.calcular_kpis_asesor_detalle(sesion, filtro, cedula)

    assert detalle is not None
    assert not sentencias.con("row_number")


@pytest.mark.parametrize("resumen", [False, True], ids=["live", "summary"])
@pytest.mark.parametrize("dimension", [t.DIM_ASESOR, t.DIM_SUCURSAL, t.DIM_TOTAL])
async def test_solo_unicos_counts_the_same_clients_as_the_full_read(sesion, monkeypatch, resumen, dimension):
    mundo = await _mundo(sesion, True)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", resumen)
    for tiendas in (None, [mundo.s1.id]):
        filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, tiendas)
        completo = await lectura.clientes(sesion, filtro, dimension=dimension)
        unicos = await lectura.clientes(sesion, filtro, dimension=dimension, solo_unicos=True)
        assert completo
        assert sorted((f.clave, f.clientes) for f in unicos) == sorted((f.clave, f.clientes) for f in completo)
        assert all(f.venta_top5 == 0 for f in unicos)
