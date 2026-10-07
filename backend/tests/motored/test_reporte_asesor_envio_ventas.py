"""
The light month-to-date read behind the send state and the messages
(odd/motored-reporte-diario-asesor, perf fix).

- `estado_envio` never runs the full report builder (`reportes_asesores`);
  it reads `ventas_del_mes`, a liquidation of the month only.
- `armar_ventas` shapes one liquidation into the per-cédula rows: the
  rated asesores carry their report numbers, the ones without a budget
  carry `con_reporte=False`.
"""
import datetime
from datetime import date

import pytest

from app.motored.services import reporte_asesor_envio as envio
from app.motored.services import reporte_asesor_ventas as ventas
from app.motored.services import reportes_asesores as builder
from tests.motored.conftest import FakeAsyncSession

HOY = date(2026, 10, 7)
AYER = date(2026, 10, 6)


def _asesor(cedula, nombre, tienda, pct, total):
    return {"cedula": cedula, "nombre": nombre, "tienda": tienda,
            "cumplimiento_pct": pct, "total_a_pagar": total}


def test_armar_ventas_keeps_the_rated_and_the_unbudgeted_asesores():
    resultado = ventas.armar_ventas(
        [_asesor("1001", "GOMEZ JUAN", "Norte", 0.875, 1234.5)],
        [{"cedula": "2002", "nombre": "RUIZ EVA", "venta": 10.0}],
        {"P:XX": 5})

    assert resultado.asesores == {
        "1001": {"nombre": "GOMEZ JUAN", "tienda": "Norte",
                 "con_reporte": True, "cumplimiento_pct": 0.875,
                 "total_a_pagar": 1235},
        "2002": {"nombre": "RUIZ EVA", "tienda": None,
                 "con_reporte": False, "cumplimiento_pct": None,
                 "total_a_pagar": None},
    }
    assert set(resultado.reportes) == {"1001"}
    assert resultado.sin_presupuesto == 1
    assert resultado.sin_cedula == 1


def test_a_rated_asesor_is_never_also_unbudgeted():
    resultado = ventas.armar_ventas(
        [_asesor("1001", "A", "Norte", 1.0, 10)],
        [{"cedula": "1001", "nombre": "A", "venta": 1.0}], {})

    assert resultado.asesores["1001"]["con_reporte"] is True


async def test_estado_envio_never_runs_the_full_builder(monkeypatch):
    async def prohibido(db, fecha):
        raise AssertionError("the full builder must not run here")

    async def leer_config(db, ahora, memoria):
        return envio.ConfigEnvio(False, datetime.time(10),
                                 datetime.time(6))

    async def ultima(db, hoy):
        return AYER

    async def ultimo(db):
        return {"fecha_datos": None, "enviados": 0, "fallidos": 0,
                "bloqueados": 0, "nombres_bloqueados": []}

    async def ninguno(db, *args):
        return []

    async def sin_envios(db, ids):
        return {}

    async def del_mes(db, fecha):
        return ventas.armar_ventas(
            [_asesor("1001", "GOMEZ JUAN", "Norte", 0.9, 10)], [], {})

    monkeypatch.setattr(builder, "reportes_asesores", prohibido)
    monkeypatch.setattr(envio, "reportes_asesores", prohibido,
                        raising=False)
    monkeypatch.setattr(envio, "ventas_del_mes", del_mes, raising=False)
    monkeypatch.setattr(envio, "leer_config", leer_config)
    monkeypatch.setattr(envio, "ultima_fecha_datos", ultima)
    monkeypatch.setattr(envio, "_ultimo_envio", ultimo)
    monkeypatch.setattr(envio, "leer_asesores", ninguno)
    monkeypatch.setattr(envio, "leer_titulares", ninguno)
    monkeypatch.setattr(envio, "leer_ultimos_envios", sin_envios)

    estado = await envio.estado_envio(FakeAsyncSession(), HOY)

    assert [f["cedula_mask"] for f in estado["asesores"]] == ["****1001"]
    assert estado["asesores"][0]["estado"] == envio.SIN_USUARIO
    assert estado["sin_usuario"] == ["GOMEZ JUAN"]


@pytest.mark.parametrize("pct, total, esperado", [
    (0.875, 1234.5, "cumplimiento 87,5% · total estimado a pagar $1.235"),
])
def test_the_message_reads_the_light_numbers(pct, total, esperado):
    fila = ventas.armar_ventas(
        [_asesor("1", "A", "N", pct, total)], [], {}).reportes["1"]

    assert esperado in envio.texto_mensaje("Ana", AYER, fila, "u")
