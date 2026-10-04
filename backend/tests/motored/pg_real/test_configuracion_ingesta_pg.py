"""
Motored "Configuración", T4 against a real Postgres (opt-in): the period
tolerance of a VENTAS file is read from `parametro_metodologia` and changes
the verdict of the real period evaluation.
"""
import datetime

import httpx
import pytest
from sqlalchemy import delete

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services.auth import MotoredUser
from app.motored.services.ingesta import orquestador, ventas
from tests.motored.pg_real.test_envio_pg import (  # noqa: F401 (fixture)
    URL,
    escenario,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

CLAVE = "periodo_tolerancia_pct"
MES = datetime.date.today().replace(day=1).isoformat()
# 33 September lines and 1 August line: 2.94 % outside the declared month.
HISTOGRAMA = {(2026, 9): 33, (2026, 8): 1}


@pytest.fixture
async def admin(escenario, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "config-ingesta-pg")
    monkeypatch.setattr(
        settings, "MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT", 0.5)
    orquestador._memoria_tolerancia.clear()

    async def sesion():
        async with escenario.maker() as db:
            yield db

    async def usuario():
        return MotoredUser(user_id=str(escenario.usuario_id), role="ADMIN")

    app.dependency_overrides[get_motored_db] = sesion
    app.dependency_overrides[get_current_motored_user] = usuario
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://motored") as http:
        yield http
    app.dependency_overrides.clear()
    async with escenario.maker() as db:
        await db.execute(delete(ParametroMetodologia).where(
            ParametroMetodologia.clave == CLAVE))
        await db.commit()


async def _veredicto(escenario):
    async with escenario.maker() as db:
        tolerancia = await orquestador._leer_tolerancia_periodo(db)
    return tolerancia, ventas.evaluar_periodo_declarado(
        HISTOGRAMA, datetime.date(2026, 9, 1), datetime.date(2026, 9, 30),
        tolerancia).tipo.value


async def test_the_period_tolerance_comes_from_the_app(admin, escenario):
    assert await _veredicto(escenario) == (0.5, "RECHAZO")

    respuesta = await admin.post("/api/motored/parametros", json={
        "clave": CLAVE, "valor": 5, "vigente_desde": MES})
    assert respuesta.status_code == 201, respuesta.text

    assert await _veredicto(escenario) == (5, "ADVERTENCIA")
