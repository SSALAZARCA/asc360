"""
Motored "Configuración", T2/T3/T5 against a real Postgres (opt-in): the
purges and the aviso loop read their keys from `parametro_metodologia`
(a scheduled month does not apply yet), and `dias_entre_pedidos` keeps a
value per sucursal next to the global one.
"""
import datetime

import httpx
import pytest
from sqlalchemy import delete

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import avisos_antiguedad, parametros, retencion
from app.motored.services.auth import MotoredUser
from app.motored.services.corridas import retencion_corridas
from tests.motored.pg_real.test_envio_pg import (  # noqa: F401 (fixture)
    URL,
    escenario,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

RUTA = "/api/motored/parametros"
DIAS = "dias_entre_pedidos"
CLAVES = [
    DIAS, "aviso_hora_dia", "aviso_roles_destino",
    "retencion_inventario_habilitada", "retencion_inventario_dias",
    "retencion_corridas_habilitada", "retencion_corridas_dias",
]
D = datetime.date
HOY = D.today()
MES = HOY.replace(day=1).isoformat()
AHORA = datetime.datetime(
    HOY.year, HOY.month, 15, 12, 0, tzinfo=datetime.timezone.utc)


def _mes_siguiente():
    primero = HOY.replace(day=1)
    return (primero + datetime.timedelta(days=32)).replace(day=1)


@pytest.fixture
async def limpio(escenario):
    yield escenario
    async with escenario.maker() as db:
        await db.execute(delete(ParametroMetodologia).where(
            ParametroMetodologia.clave.in_(CLAVES)))
        await db.commit()


@pytest.fixture
async def admin(limpio, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "config-limpieza-pg")
    retencion._memoria_config.clear()
    retencion_corridas._memoria_config.clear()

    async def sesion():
        async with limpio.maker() as db:
            yield db

    async def usuario():
        return MotoredUser(user_id=str(limpio.usuario_id), role="ADMIN")

    app.dependency_overrides[get_motored_db] = sesion
    app.dependency_overrides[get_current_motored_user] = usuario
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://motored") as http:
        yield http
    app.dependency_overrides.clear()


async def _guardar(admin, clave, valor, desde=MES, sucursal=None):
    cuerpo = {"clave": clave, "valor": valor, "vigente_desde": desde}
    if sucursal is not None:
        cuerpo["sucursal_id"] = str(sucursal)
    return await admin.post(RUTA, json=cuerpo)


async def test_the_inventory_purge_reads_its_keys_from_the_app(admin, limpio):
    for clave, valor in (("retencion_inventario_habilitada", True),
                         ("retencion_inventario_dias", 60)):
        respuesta = await _guardar(admin, clave, valor)
        assert respuesta.status_code == 201, respuesta.text

    async with limpio.maker() as db:
        config = await retencion.leer_config(db, AHORA)

    assert config == retencion.ConfigRetencion(True, 60)


async def test_the_corridas_purge_reads_its_keys_from_the_app(admin, limpio):
    for clave, valor in (("retencion_corridas_habilitada", True),
                         ("retencion_corridas_dias", 14)):
        assert (await _guardar(admin, clave, valor)).status_code == 201

    async with limpio.maker() as db:
        config = await retencion_corridas.leer_config(db, AHORA)

    assert config == retencion.ConfigRetencion(True, 14)


async def test_a_scheduled_month_does_not_apply_yet(admin, limpio):
    futuro = _mes_siguiente().isoformat()
    respuesta = await _guardar(
        admin, "retencion_inventario_dias", 365, futuro)
    assert respuesta.status_code == 201, respuesta.text

    async with limpio.maker() as db:
        ahora = await retencion.leer_config(db, AHORA)
        despues = await retencion.leer_config(
            db, datetime.datetime.combine(
                _mes_siguiente(), datetime.time(9, 0),
                tzinfo=datetime.timezone.utc))

    assert ahora.dias == settings.MOTORED_RETENCION_DIAS
    assert despues.dias == 365


async def test_a_value_below_the_minimum_is_refused_and_not_stored(
        admin, limpio):
    respuesta = await _guardar(admin, "retencion_inventario_dias", 10)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert "30" in respuesta.json()["detail"]["message"]
    async with limpio.maker() as db:
        assert (await retencion.leer_config(db, AHORA)).dias == (
            settings.MOTORED_RETENCION_DIAS)


async def test_the_aviso_loop_reads_hour_and_roles(admin, limpio):
    for clave, valor in (("aviso_hora_dia", "07:15"),
                         ("aviso_roles_destino", ["ADMIN", "COMPRAS"])):
        assert (await _guardar(admin, clave, valor)).status_code == 201

    async with limpio.maker() as db:
        config = await avisos_antiguedad.leer_config(db, AHORA, {})

    assert config.hora_dia == datetime.time(7, 15)
    assert [r.value for r in config.roles] == ["ADMIN", "COMPRAS"]
    assert config.hora_vispera == avisos_antiguedad.HORA_VISPERA


async def test_dias_entre_pedidos_keeps_a_value_per_sucursal(admin, limpio):
    assert (await _guardar(admin, DIAS, 20)).status_code == 201
    assert (await _guardar(admin, DIAS, 10, sucursal=limpio.a)).status_code \
        == 201

    async with limpio.maker() as db:
        propia = await parametros.vigente_en(db, DIAS, HOY, limpio.a)
        otra = await parametros.vigente_en(db, DIAS, HOY, limpio.b)

    assert (propia.valor, propia.fuente) == (10, parametros.FUENTE_SUCURSAL)
    assert (otra.valor, otra.fuente) == (20, parametros.FUENTE_GLOBAL)


async def test_dias_entre_pedidos_per_sucursal_is_validated_and_listed(
        admin, limpio):
    malo = await _guardar(admin, DIAS, 61, sucursal=limpio.a)
    assert malo.status_code == 422

    assert (await _guardar(admin, DIAS, 12, sucursal=limpio.b)).status_code \
        == 201
    pagina = await admin.get(f"{RUTA}/configuracion")
    claves = {c["clave"]: c for s in pagina.json()["secciones"]
              for g in s["grupos"] for c in g["claves"]}

    por_sucursal = claves[DIAS]["por_sucursal"]
    assert [(p["sucursal_id"], p["valor"]) for p in por_sucursal] == [
        (str(limpio.b), 12)]
