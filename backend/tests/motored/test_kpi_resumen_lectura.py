"""Unit checks of the KPI summary read switch (odd/motored-kpis-resumenes, R3): the SQL itself is
covered against a real Postgres in `pg_real/test_kpi_resumen_lectura_pg.py`."""
import pytest

from app.config import settings
from app.motored.services import kpi_resumen_lectura as lectura


class SesionProhibida:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("the switch is off: no query may be made")


def test_the_setting_defaults_to_off():
    assert settings.model_fields["MOTORED_KPI_RESUMEN_ENABLED"].default is False


async def test_with_the_setting_off_the_check_never_touches_the_database(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)

    assert await lectura.usar_resumen(SesionProhibida()) is False


async def test_with_the_setting_off_the_dispatch_calls_the_live_queries(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    vistos = []

    async def vivo(db, *args):
        vistos.append(args)
        return ["vivo"]

    for nombre in ("consultar_cubo", "consultar_ventana_mensual", "consultar_personas"):
        monkeypatch.setattr(lectura.q, nombre, vivo)
    monkeypatch.setattr(lectura.q, "meses_disponibles", vivo)
    monkeypatch.setattr(lectura.qk, "consultar_costo_venta", vivo)
    db = SesionProhibida()

    resultados = [
        await lectura.cubo(db, "f", "corte", "asesor"), await lectura.ventana_mensual(db, "f", "sucursal"),
        await lectura.personas(db, "f"), await lectura.meses(db), await lectura.costo_venta(db, "f", "corte"),
    ]

    assert resultados == [["vivo"]] * 5
    assert vistos == [("f", "corte", "asesor"), ("f", "sucursal"), ("f",), (), ("f", "corte")]
