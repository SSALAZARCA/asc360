"""
The per-asesor send table and the single send
(odd/motored-reporte-diario-asesor, T3d).

- One row per asesor with sales (`reportes` plus `sin_presupuesto` of ONE
  builder call), with the cédula masked to its last 4 digits.
- `estado` follows a fixed precedence: sin_usuario, cedula_pendiente,
  usuario_inactivo, sin_telegram, sin_enlace, sin_presupuesto, bloqueado,
  listo. Only 'listo' can be sent now.
- `enviar_a_uno` sends one asesor's message, bypassing the once-per-date
  rule, and records a `reenvio` ledger row with the admin.
"""
import datetime
import logging
import uuid
from datetime import date, timezone

import pytest

from app.config import settings
from app.motored.models.reporte_asesor_envio import ReporteAsesorEnvio
from app.motored.services import reporte_asesor_envio as envio
from tests.motored.conftest import FakeAsyncSession

AYER = date(2026, 10, 6)
HOY = date(2026, 10, 7)
CEDULA = "79845123"
PUBLICA = "https://motored.example.co"
CUANDO = datetime.datetime(2026, 10, 6, 13, 5, tzinfo=timezone.utc)


def _titular(**cambios) -> envio.Titular:
    base = dict(
        usuario_id=uuid.uuid4(), nombre="Ana Pérez", cedula=CEDULA,
        cedula_aprobada=True, activo=True, status="approved",
        telegram_id=555, token="tok-" + "a" * 40)
    base.update(cambios)
    return envio.Titular(**base)


def _ultimo(estado=envio.ENVIADO):
    return envio.UltimoEnvio(CUANDO, estado)


# --- estado precedence ----------------------------------------------------

@pytest.mark.parametrize("titular, con_reporte, ultimo, esperado", [
    (None, True, None, envio.SIN_USUARIO),
    (_titular(cedula_aprobada=False, activo=False, telegram_id=None),
     False, None, envio.CEDULA_PENDIENTE),
    (_titular(activo=False, telegram_id=None, token=None), False, None,
     envio.USUARIO_INACTIVO),
    (_titular(status="pending", telegram_id=None), True, None,
     envio.USUARIO_INACTIVO),
    (_titular(telegram_id=None, token=None), False, None,
     envio.SIN_TELEGRAM),
    (_titular(token=None), False, _ultimo(envio.BLOQUEADO),
     envio.SIN_ENLACE),
    (_titular(), False, _ultimo(envio.BLOQUEADO), envio.SIN_PRESUPUESTO),
    (_titular(), True, _ultimo(envio.BLOQUEADO), envio.BLOQUEADO),
    (_titular(), True, _ultimo(envio.FALLIDO), envio.LISTO),
    (_titular(), True, None, envio.LISTO),
])
def test_estado_follows_the_precedence(titular, con_reporte, ultimo,
                                       esperado):
    assert envio.estado_titular(titular, con_reporte, ultimo) == esperado


def test_the_approved_holder_wins_over_a_pending_copy():
    pendiente = _titular(nombre="Impostor", cedula_aprobada=False)
    dueno = _titular(nombre="Dueño")

    assert envio.elegir_titular([pendiente, dueno]) is dueno
    assert envio.elegir_titular([pendiente]) is pendiente
    assert envio.elegir_titular([]) is None


def test_the_mask_keeps_only_the_last_four_digits():
    assert envio.enmascarar(CEDULA) == "****5123"


# --- the rows -------------------------------------------------------------

def _datos():
    return {
        "reportes": {
            CEDULA: {"cedula": CEDULA, "nombre": "PEREZ ANA",
                     "tienda": "Centro"},
            "1001": {"cedula": "1001", "nombre": "GOMEZ JUAN",
                     "tienda": "Norte"},
        },
        "sin_presupuesto": [
            {"cedula": "2002", "nombre": "RUIZ EVA", "venta": 10}],
        "sin_cedula": [{"nombre": "SIN CEDULA", "venta": 5}],
    }


class Lectores:
    """Monkeypatched readers; counts the builder calls."""

    def __init__(self, monkeypatch, titulares=(), ultimos=None):
        self.llamadas_reportes = 0
        self.cedulas_pedidas = None

        async def leer_titulares(db, cedulas):
            self.cedulas_pedidas = set(cedulas)
            return [t for t in titulares if t.cedula in self.cedulas_pedidas]

        async def leer_titular(db, usuario_id):
            return next(
                (t for t in titulares if t.usuario_id == usuario_id), None)

        async def leer_ultimos_envios(db, ids):
            return {k: v for k, v in (ultimos or {}).items() if k in ids}

        async def reportes_asesores(db, fecha):
            self.llamadas_reportes += 1
            return _datos()

        monkeypatch.setattr(envio, "leer_titulares", leer_titulares)
        monkeypatch.setattr(envio, "leer_titular", leer_titular)
        monkeypatch.setattr(
            envio, "leer_ultimos_envios", leer_ultimos_envios)
        monkeypatch.setattr(envio, "reportes_asesores", reportes_asesores)


async def test_one_row_per_asesor_with_sales(monkeypatch):
    ana = _titular()
    eva = _titular(nombre="Eva Ruiz", cedula="2002")
    Lectores(monkeypatch, [ana, eva], {ana.usuario_id: _ultimo()})

    filas = await envio.filas_asesores(FakeAsyncSession(), _datos())

    por_mask = {f["cedula_mask"]: f for f in filas}
    assert set(por_mask) == {"****5123", "****1001", "****2002"}
    assert por_mask["****5123"] == {
        "cedula_mask": "****5123", "nombre": "Ana Pérez",
        "tienda": "Centro", "usuario_id": str(ana.usuario_id),
        "estado": envio.LISTO,
        "ultimo_envio": {"en": CUANDO.isoformat(),
                         "estado": envio.ENVIADO},
        "puede_enviar": True,
    }
    juan = por_mask["****1001"]
    assert juan["estado"] == envio.SIN_USUARIO
    assert juan["nombre"] == "GOMEZ JUAN" and juan["usuario_id"] is None
    assert juan["ultimo_envio"] is None and juan["puede_enviar"] is False
    assert por_mask["****2002"]["estado"] == envio.SIN_PRESUPUESTO
    assert por_mask["****2002"]["puede_enviar"] is False
    assert CEDULA not in str(filas)


async def test_the_rows_are_sorted_by_name(monkeypatch):
    Lectores(monkeypatch)

    filas = await envio.filas_asesores(FakeAsyncSession(), _datos())

    assert [f["nombre"] for f in filas] == [
        "GOMEZ JUAN", "PEREZ ANA", "RUIZ EVA"]


async def test_estado_envio_builds_the_rows_from_one_builder_call(
        monkeypatch):
    ana = _titular()
    lectores = Lectores(monkeypatch, [ana])

    async def leer_config(db, ahora, memoria):
        return envio.ConfigEnvio(False, datetime.time(10),
                                 datetime.time(6))

    async def ultima(db, hoy):
        return AYER

    async def ultimo(db):
        return {"fecha_datos": None, "enviados": 0, "fallidos": 0,
                "bloqueados": 0, "nombres_bloqueados": []}

    async def leer_asesores(db):
        return [ana.como_asesor()]

    monkeypatch.setattr(envio, "leer_config", leer_config)
    monkeypatch.setattr(envio, "ultima_fecha_datos", ultima)
    monkeypatch.setattr(envio, "_ultimo_envio", ultimo)
    monkeypatch.setattr(envio, "leer_asesores", leer_asesores)

    estado = await envio.estado_envio(FakeAsyncSession(), HOY)

    assert lectores.llamadas_reportes == 1
    assert lectores.cedulas_pedidas == {CEDULA, "1001", "2002"}
    assert len(estado["asesores"]) == 3
    assert estado["elegibles"] == 1
    assert CEDULA not in str(estado)
    assert ana.token not in str(estado)


async def test_without_sales_there_are_no_rows(monkeypatch):
    async def leer_config(db, ahora, memoria):
        return envio.ConfigEnvio(False, datetime.time(10),
                                 datetime.time(6))

    async def ninguna(db, hoy):
        return None

    async def ultimo(db):
        return {"fecha_datos": None, "enviados": 0, "fallidos": 0,
                "bloqueados": 0, "nombres_bloqueados": []}

    lectores = Lectores(monkeypatch)
    monkeypatch.setattr(envio, "leer_config", leer_config)
    monkeypatch.setattr(envio, "ultima_fecha_datos", ninguna)
    monkeypatch.setattr(envio, "_ultimo_envio", ultimo)

    estado = await envio.estado_envio(FakeAsyncSession(), HOY)

    assert estado["asesores"] == []
    assert lectores.llamadas_reportes == 0


# --- the single send ------------------------------------------------------

class SesionContada(FakeAsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commits = 0

    async def commit(self):
        await super().commit()
        self.commits += 1


def _enviar(*resultados):
    textos = []
    pendientes = list(resultados)

    async def enviar(chat_id, texto):
        textos.append((chat_id, texto))
        return pendientes.pop(0)

    return enviar, textos


async def _no_dormir(segundos):
    return None


@pytest.fixture
def publica(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", PUBLICA)


async def test_enviar_a_uno_sends_and_records_a_resend(
        monkeypatch, publica, caplog):
    caplog.set_level(logging.DEBUG)
    ana = _titular()
    admin = uuid.uuid4()
    lectores = Lectores(monkeypatch, [ana],
                        {ana.usuario_id: _ultimo(envio.ENVIADO)})
    enviar, textos = _enviar(envio.Respuesta(envio.RES_OK))
    db = SesionContada()

    resultado = await envio.enviar_a_uno(
        db, ana.usuario_id, AYER, enviar, _no_dormir, admin)

    assert resultado == envio.EnvioUno(envio.ENVIADO, "Ana Pérez")
    assert lectores.llamadas_reportes == 1
    assert textos[0][0] == 555 and PUBLICA in textos[0][1]
    fila = db.added_of_type(ReporteAsesorEnvio)[0]
    assert fila.reenvio is True and fila.solicitado_por == admin
    assert fila.estado == envio.ENVIADO and fila.fecha_datos == AYER
    assert db.commits == 1
    assert CEDULA not in caplog.text and ana.token not in caplog.text


async def test_enviar_a_uno_maps_a_403_to_bloqueado(monkeypatch, publica):
    ana = _titular()
    Lectores(monkeypatch, [ana])
    enviar, _ = _enviar(
        envio.Respuesta(envio.RES_BLOQUEADO, detalle="Telegram 403"))
    db = SesionContada()

    resultado = await envio.enviar_a_uno(
        db, ana.usuario_id, AYER, enviar, _no_dormir, uuid.uuid4())

    assert resultado.estado == envio.BLOQUEADO
    assert db.added_of_type(ReporteAsesorEnvio)[0].estado == envio.BLOQUEADO


async def test_enviar_a_uno_reports_a_telegram_failure(monkeypatch, publica):
    ana = _titular()
    Lectores(monkeypatch, [ana])
    enviar, _ = _enviar(
        envio.Respuesta(envio.RES_ERROR, detalle="Telegram 500"))

    resultado = await envio.enviar_a_uno(
        SesionContada(), ana.usuario_id, AYER, enviar, _no_dormir,
        uuid.uuid4())

    assert resultado.estado == envio.FALLIDO


@pytest.mark.parametrize("cambios, ultimo, esperado", [
    (dict(cedula_aprobada=False), None, envio.CEDULA_PENDIENTE),
    (dict(activo=False), None, envio.USUARIO_INACTIVO),
    (dict(telegram_id=None), None, envio.SIN_TELEGRAM),
    (dict(token=None), None, envio.SIN_ENLACE),
    (dict(cedula="2002"), None, envio.SIN_PRESUPUESTO),
    ({}, envio.BLOQUEADO, envio.BLOQUEADO),
    (dict(cedula=None), None, envio.SIN_CEDULA),
    (dict(cedula="3003"), None, envio.SIN_VENTAS),
])
async def test_enviar_a_uno_refuses_who_is_not_listo(
        monkeypatch, publica, cambios, ultimo, esperado):
    ana = _titular(**cambios)
    ultimos = {ana.usuario_id: _ultimo(ultimo)} if ultimo else None
    Lectores(monkeypatch, [ana], ultimos)
    enviar, textos = _enviar()
    db = SesionContada()

    with pytest.raises(envio.NoListo) as error:
        await envio.enviar_a_uno(
            db, ana.usuario_id, AYER, enviar, _no_dormir, uuid.uuid4())

    assert error.value.estado == esperado
    assert textos == [] and db.added_of_type(ReporteAsesorEnvio) == []


async def test_enviar_a_uno_of_an_unknown_usuario(monkeypatch, publica):
    lectores = Lectores(monkeypatch)
    enviar, _ = _enviar()

    with pytest.raises(LookupError):
        await envio.enviar_a_uno(
            SesionContada(), uuid.uuid4(), AYER, enviar, _no_dormir,
            uuid.uuid4())

    assert lectores.llamadas_reportes == 0
