"""
The asesor daily report send through Lore
(odd/motored-reporte-diario-asesor, T3b): readiness and `fecha_datos`, the
minimum and deadline hours, the eligibility filters, the once-per-date
rule, the message, the Telegram outcomes (403 blocked, 429 retried) and the
ledger rows. The token, the URL and the cédula never reach a log.
"""
import datetime
import logging
import uuid
from datetime import date, time, timezone

import httpx
import pytest

from app.config import settings
from app.motored.models.reporte_asesor_envio import ReporteAsesorEnvio
from app.motored.services import kpi_resumen
from app.motored.services import reporte_asesor_envio as envio
from tests.motored.conftest import FakeAsyncSession

HOY = date(2026, 10, 7)
AYER = date(2026, 10, 6)
BOT_TOKEN = "999:secreto-del-bot"
PUBLICA = "https://motored.example.co"


def _asesor(**cambios) -> envio.Asesor:
    base = dict(
        usuario_id=uuid.uuid4(), nombre="Ana Pérez", cedula="79845123",
        cedula_aprobada=True, telegram_id=555, token="tok-" + "a" * 40)
    base.update(cambios)
    return envio.Asesor(**base)


def _reporte(cedula="79845123", pct=0.875, total=1234567) -> dict:
    return {
        "cedula": cedula, "nombre": "PEREZ ANA", "cumplimiento_pct": pct,
        "total_a_pagar": total, "fecha_datos": AYER.isoformat()}


def _config(activo=True, limite=time(10), minima=time(6)):
    return envio.ConfigEnvio(activo, limite, minima)


def _estado(**cambios):
    base = dict(
        sucio=False, reconstruyendo=False,
        actualizado_en=datetime.datetime(2026, 10, 7, tzinfo=timezone.utc),
        ultima_reconstruccion_total=datetime.datetime(
            2026, 10, 7, tzinfo=timezone.utc),
        version=1)
    base.update(cambios)
    return kpi_resumen.Estado(**base)


class SesionContada(FakeAsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commits = 0

    async def commit(self):
        await super().commit()
        self.commits += 1


# --- readiness ------------------------------------------------------------

@pytest.mark.parametrize("maximo, esperada", [
    (None, None),
    (AYER, AYER),
    (HOY, AYER),
    (date(2026, 10, 31), AYER),
    (date(2026, 10, 4), date(2026, 10, 4)),
])
def test_fecha_de_datos_is_the_latest_carga_capped_at_yesterday(
        maximo, esperada):
    assert envio.fecha_de_datos(maximo, HOY) == esperada


def test_ready_only_when_the_data_reaches_yesterday():
    assert envio.esta_lista(AYER, HOY)
    assert not envio.esta_lista(date(2026, 10, 4), HOY)
    assert not envio.esta_lista(None, HOY)


async def test_ultima_fecha_datos_reads_the_aplicado_ventas_cargas():
    db = FakeAsyncSession(execute_queue=[[HOY]])

    assert await envio.ultima_fecha_datos(db, HOY) == AYER
    sql = str(db.executed_statements[0].compile(
        compile_kwargs={"literal_binds": True}))
    assert "max(carga_archivo.periodo_hasta)" in sql
    assert "'VENTAS'" in sql and "'APLICADO'" in sql


async def test_ultima_fecha_datos_without_cargas_is_none():
    db = FakeAsyncSession(execute_queue=[[None]])

    assert await envio.ultima_fecha_datos(db, HOY) is None


@pytest.mark.parametrize("estado, listo", [
    (None, False),
    (_estado(ultima_reconstruccion_total=None), False),
    (_estado(sucio=True), False),
    (_estado(reconstruyendo=True), False),
    (_estado(), True),
])
def test_resumen_al_dia(estado, listo):
    assert envio.resumen_al_dia(estado) is listo


async def test_with_the_summaries_switched_off_live_data_is_ready(
        monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    db = FakeAsyncSession(execute_queue=[])

    assert await envio.resumen_listo(db) is True
    assert db.executed_statements == []


@pytest.mark.parametrize("hora, resumen_ok, toca", [
    (time(5, 59), True, False),
    (time(6, 0), True, True),
    (time(7, 0), False, False),
    (time(9, 59), False, False),
    (time(10, 0), False, True),
    (time(15, 0), False, True),
])
def test_minimum_hour_normal_path_and_deadline(hora, resumen_ok, toca):
    assert envio.toca_enviar(hora, _config(), resumen_ok) is toca


def test_the_minimum_hour_wins_over_an_earlier_deadline():
    config = _config(limite=time(4), minima=time(6))

    assert not envio.toca_enviar(time(5), config, False)
    assert envio.toca_enviar(time(6), config, False)


# --- eligibility ----------------------------------------------------------

def test_clasificar_keeps_only_complete_asesores_with_sales():
    listo = _asesor(nombre="Lista", cedula="1")
    sin_link = _asesor(nombre="Sin enlace", cedula="2", token=None)
    sin_aprobar = _asesor(
        nombre="Sin aprobar", cedula="3", cedula_aprobada=False)
    sin_tg = _asesor(nombre="Sin Telegram", cedula="4", telegram_id=None)
    sin_ventas = _asesor(nombre="Sin ventas", cedula="9")
    reportes = {c: _reporte(c) for c in ("1", "2", "3", "4", "7")}
    reportes["7"]["nombre"] = "NADIE REGISTRADO"

    clas = envio.clasificar(
        [listo, sin_link, sin_aprobar, sin_tg, sin_ventas], reportes)

    assert clas.elegibles == [listo]
    assert clas.sin_enlace == ["Sin enlace"]
    assert clas.sin_cedula_aprobada == ["Sin aprobar"]
    assert clas.sin_telegram == ["Sin Telegram"]
    assert clas.sin_usuario == ["NADIE REGISTRADO"]


def test_an_unapproved_copy_of_an_approved_cedula_is_not_listed():
    dueno = _asesor(nombre="Dueño", cedula="1")
    impostor = _asesor(nombre="Otro", cedula="1", cedula_aprobada=False)

    clas = envio.clasificar([dueno, impostor], {"1": _reporte("1")})

    assert clas.elegibles == [dueno]
    assert clas.sin_cedula_aprobada == []


def _fila(asesor, estado, reenvio=False, n=1):
    return envio.FilaLedger(asesor.usuario_id, asesor.nombre, estado,
                            reenvio, n)


def test_pendientes_applies_the_once_per_date_rule():
    enviado = _asesor(cedula="1")
    reenviado = _asesor(cedula="2")
    bloqueado = _asesor(cedula="3")
    tres_fallos = _asesor(cedula="4")
    dos_fallos = _asesor(cedula="5")
    fallos_de_reenvio = _asesor(cedula="6")
    nuevo = _asesor(cedula="7")
    filas = [
        _fila(enviado, envio.ENVIADO),
        _fila(reenviado, envio.ENVIADO, reenvio=True),
        _fila(bloqueado, envio.BLOQUEADO),
        _fila(tres_fallos, envio.FALLIDO, n=3),
        _fila(dos_fallos, envio.FALLIDO, n=2),
        _fila(fallos_de_reenvio, envio.FALLIDO, reenvio=True, n=5),
    ]
    todos = [enviado, reenviado, bloqueado, tres_fallos, dos_fallos,
             fallos_de_reenvio, nuevo]

    assert envio.pendientes(todos, filas) == [
        dos_fallos, fallos_de_reenvio, nuevo]


def test_resumen_del_ledger_counts_the_final_state_per_asesor():
    a, b, c, d = (_asesor(cedula=str(i)) for i in range(4))
    filas = [
        _fila(a, envio.FALLIDO, n=2), _fila(a, envio.ENVIADO),
        _fila(b, envio.BLOQUEADO),
        _fila(c, envio.FALLIDO, n=3),
        _fila(d, envio.ENVIADO, reenvio=True),
    ]

    resumen = envio.resumir_ledger(filas)

    assert resumen == {
        "enviados": 2, "fallidos": 1, "bloqueados": 1,
        "nombres_bloqueados": [b.nombre]}


# --- message --------------------------------------------------------------

@pytest.mark.parametrize("valor, texto", [
    (0, "$0"), (950, "$950"), (1234567, "$1.234.567"),
    (12000000, "$12.000.000")])
def test_money_uses_dots_for_thousands(valor, texto):
    assert envio.formato_pesos(valor) == texto


@pytest.mark.parametrize("fraccion, texto", [
    (0.875, "87,5%"), (1, "100,0%"), (0.0, "0,0%"), (1.2345, "123,5%"),
    (None, "sin dato")])
def test_percent_has_one_decimal_with_a_comma(fraccion, texto):
    assert envio.formato_pct(fraccion) == texto


def test_the_message_text():
    texto = envio.texto_mensaje(
        "Ana Pérez", AYER, _reporte(), "https://x.co/motored/informe/t")

    assert texto == (
        "Hola Ana Pérez, tu informe con ventas al 06/10/2026: "
        "cumplimiento 87,5% · total estimado a pagar $1.234.567 "
        "(comisión estimada, no es un pago). Ábrelo con tu cédula: "
        "https://x.co/motored/informe/t")


def test_armar_destinos_builds_one_message_per_asesor(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", PUBLICA + "/")
    asesor = _asesor()

    destinos = envio.armar_destinos(
        [asesor], {asesor.cedula: _reporte()}, AYER)

    assert len(destinos) == 1
    assert destinos[0].asesor is asesor
    assert destinos[0].texto.endswith(
        f"{PUBLICA}/motored/informe/{asesor.token}")


# --- Telegram outcomes ----------------------------------------------------

def _transporte(status, headers=None, error=None):
    def responder(request):
        if error is not None:
            raise error
        return httpx.Response(status, headers=headers or {}, json={})
    return httpx.MockTransport(responder)


@pytest.mark.parametrize("status, resultado", [
    (200, envio.RES_OK), (403, envio.RES_BLOQUEADO),
    (429, envio.RES_LIMITE), (500, envio.RES_ERROR),
    (400, envio.RES_ERROR)])
async def test_enviar_telegram_maps_the_status(status, resultado, caplog):
    caplog.set_level(logging.DEBUG)

    respuesta = await envio.enviar_telegram(
        BOT_TOKEN, 555, "hola", transporte=_transporte(status))

    assert respuesta.resultado == resultado
    assert BOT_TOKEN not in caplog.text
    assert BOT_TOKEN not in (respuesta.detalle or "")


async def test_a_429_carries_retry_after():
    respuesta = await envio.enviar_telegram(
        BOT_TOKEN, 555, "hola",
        transporte=_transporte(429, headers={"Retry-After": "3"}))

    assert respuesta.espera == 3.0


async def test_a_network_error_is_an_error_and_never_logs_the_token(
        caplog):
    caplog.set_level(logging.DEBUG)
    error = httpx.ConnectError(f"no route to bot{BOT_TOKEN}")

    respuesta = await envio.enviar_telegram(
        BOT_TOKEN, 555, "hola", transporte=_transporte(0, error=error))

    assert respuesta.resultado == envio.RES_ERROR
    assert BOT_TOKEN not in caplog.text
    assert BOT_TOKEN not in respuesta.detalle


def _guion(*resultados):
    llamadas = []
    cola = list(resultados)

    async def enviar(chat_id, texto):
        llamadas.append((chat_id, texto))
        return cola.pop(0)

    return enviar, llamadas


def _dormidor():
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)

    return dormir, esperas


async def test_a_429_is_retried_with_backoff_then_succeeds():
    enviar, llamadas = _guion(
        envio.Respuesta(envio.RES_LIMITE, espera=2.0),
        envio.Respuesta(envio.RES_LIMITE),
        envio.Respuesta(envio.RES_OK))
    dormir, esperas = _dormidor()

    respuesta = await envio.enviar_con_reintentos(
        enviar, 555, "hola", dormir)

    assert respuesta.resultado == envio.RES_OK
    assert len(llamadas) == 3
    assert esperas[0] == 2.0 and esperas[1] > 0


async def test_three_429_give_up_as_an_error():
    enviar, llamadas = _guion(
        *[envio.Respuesta(envio.RES_LIMITE)] * 3)
    dormir, esperas = _dormidor()

    respuesta = await envio.enviar_con_reintentos(
        enviar, 555, "hola", dormir)

    assert respuesta.resultado == envio.RES_ERROR
    assert len(llamadas) == 3
    assert len(esperas) == 2


async def test_a_403_is_not_retried():
    enviar, llamadas = _guion(envio.Respuesta(envio.RES_BLOQUEADO))
    dormir, esperas = _dormidor()

    respuesta = await envio.enviar_con_reintentos(
        enviar, 555, "hola", dormir)

    assert respuesta.resultado == envio.RES_BLOQUEADO
    assert len(llamadas) == 1 and esperas == []


# --- the batch and its ledger rows ----------------------------------------

def _destinos(*asesores):
    return [envio.Destino(a, f"texto {a.cedula} {a.token}")
            for a in asesores]


def _reloj():
    return datetime.datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


async def test_enviar_lote_commits_one_ledger_row_per_send(caplog):
    caplog.set_level(logging.DEBUG)
    ok, bloqueado, fallido = (_asesor(cedula=f"7984512{i}") for i in range(3))
    enviar, _ = _guion(
        envio.Respuesta(envio.RES_OK),
        envio.Respuesta(envio.RES_BLOQUEADO, detalle="Telegram 403"),
        envio.Respuesta(envio.RES_ERROR, detalle="Telegram 500"))
    dormir, esperas = _dormidor()
    db = SesionContada()

    conteo = await envio.enviar_lote(
        db, _destinos(ok, bloqueado, fallido), AYER, enviar, dormir,
        reloj=_reloj)

    filas = db.added_of_type(ReporteAsesorEnvio)
    assert [f.estado for f in filas] == [
        envio.ENVIADO, envio.BLOQUEADO, envio.FALLIDO]
    assert [f.usuario_id for f in filas] == [
        ok.usuario_id, bloqueado.usuario_id, fallido.usuario_id]
    assert all(f.fecha_datos == AYER and not f.reenvio for f in filas)
    assert all(f.solicitado_por is None for f in filas)
    assert filas[1].detalle == "Telegram 403"
    assert db.commits == 3
    assert esperas == [envio.PAUSA_ENTRE_ENVIOS] * 2
    assert conteo == envio.Conteo(enviados=1, fallidos=1, bloqueados=1)
    for asesor in (ok, bloqueado, fallido):
        assert asesor.token not in caplog.text
        assert asesor.cedula not in caplog.text
    assert "/motored/informe/" not in caplog.text


async def test_a_resend_records_reenvio_and_who_asked():
    admin = uuid.uuid4()
    enviar, _ = _guion(envio.Respuesta(envio.RES_OK))
    dormir, _ = _dormidor()
    db = SesionContada()

    await envio.enviar_lote(
        db, _destinos(_asesor()), AYER, enviar, dormir,
        reenvio=True, solicitado_por=admin, reloj=_reloj)

    fila = db.added_of_type(ReporteAsesorEnvio)[0]
    assert fila.reenvio is True
    assert fila.solicitado_por == admin


async def test_the_detalle_never_carries_the_token_or_url():
    asesor = _asesor()
    detalle = f"fallo {asesor.token} {PUBLICA}/motored/informe/x"
    enviar, _ = _guion(envio.Respuesta(envio.RES_ERROR, detalle=detalle))
    dormir, _ = _dormidor()
    db = SesionContada()

    await envio.enviar_lote(
        db, _destinos(asesor), AYER, enviar, dormir, reloj=_reloj)

    fila = db.added_of_type(ReporteAsesorEnvio)[0]
    assert asesor.token not in fila.detalle
    assert "informe" not in fila.detalle
    assert len(fila.detalle) <= envio.DETALLE_MAX


# --- the daily run --------------------------------------------------------

class Lectores:
    """Monkeypatched readers of `envio_diario`; counts the builder calls."""

    def __init__(self, monkeypatch, *, fecha=AYER, resumen=True,
                 asesores=(), reportes=None, ledger=()):
        self.llamadas_reportes = 0

        async def ultima(db, hoy):
            return fecha

        async def listo(db):
            return resumen

        async def leer_asesores(db):
            return list(asesores)

        async def leer_ledger(db, f):
            return list(ledger)

        async def reportes_asesores(db, f):
            self.llamadas_reportes += 1
            return {"reportes": reportes or {}, "sin_presupuesto": [],
                    "sin_cedula": []}

        monkeypatch.setattr(envio, "ultima_fecha_datos", ultima)
        monkeypatch.setattr(envio, "resumen_listo", listo)
        monkeypatch.setattr(envio, "leer_asesores", leer_asesores)
        monkeypatch.setattr(envio, "leer_ledger", leer_ledger)
        monkeypatch.setattr(envio, "reportes_asesores", reportes_asesores)


def _bogota(hora, minuto=0):
    return datetime.datetime(
        2026, 10, 7, hora + 5, minuto, tzinfo=timezone.utc)


@pytest.fixture
def publica(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", PUBLICA)


async def _diario(ahora, enviar, sin_reporte=None):
    dormir, _ = _dormidor()
    return await envio.envio_diario(
        SesionContada(), ahora, _config(), enviar, dormir,
        sin_reporte={} if sin_reporte is None else sin_reporte)


async def test_no_ready_carga_sends_nothing(monkeypatch, publica):
    lect = Lectores(monkeypatch, fecha=date(2026, 10, 4),
                    asesores=[_asesor()])
    enviar, llamadas = _guion()

    assert await _diario(_bogota(11), enviar) is None
    assert llamadas == [] and lect.llamadas_reportes == 0


async def test_waits_for_the_summary_before_the_deadline(
        monkeypatch, publica):
    asesor = _asesor()
    Lectores(monkeypatch, resumen=False, asesores=[asesor],
             reportes={asesor.cedula: _reporte()})
    enviar, llamadas = _guion(envio.Respuesta(envio.RES_OK))

    assert await _diario(_bogota(8), enviar) is None
    assert llamadas == []


async def test_after_the_deadline_it_sends_anyway(monkeypatch, publica):
    asesor = _asesor()
    lect = Lectores(monkeypatch, resumen=False, asesores=[asesor],
                    reportes={asesor.cedula: _reporte()})
    enviar, llamadas = _guion(envio.Respuesta(envio.RES_OK))

    conteo = await _diario(_bogota(10, 5), enviar)

    assert conteo.enviados == 1
    assert llamadas[0][0] == asesor.telegram_id
    assert "06/10/2026" in llamadas[0][1]
    assert lect.llamadas_reportes == 1


async def test_the_builder_runs_once_for_every_asesor(monkeypatch, publica):
    asesores = [_asesor(cedula=str(i), telegram_id=100 + i)
                for i in range(4)]
    lect = Lectores(monkeypatch, asesores=asesores,
                    reportes={a.cedula: _reporte(a.cedula)
                              for a in asesores})
    enviar, llamadas = _guion(*[envio.Respuesta(envio.RES_OK)] * 4)

    conteo = await _diario(_bogota(7), enviar)

    assert conteo.enviados == 4
    assert lect.llamadas_reportes == 1
    assert [c for c, _ in llamadas] == [100, 101, 102, 103]


async def test_already_sent_asesores_skip_the_builder(monkeypatch, publica):
    asesor = _asesor()
    lect = Lectores(monkeypatch, asesores=[asesor],
                    reportes={asesor.cedula: _reporte()},
                    ledger=[_fila(asesor, envio.ENVIADO)])
    enviar, llamadas = _guion()

    assert await _diario(_bogota(7), enviar) is None
    assert llamadas == [] and lect.llamadas_reportes == 0


async def test_asesores_without_a_link_are_not_messaged(
        monkeypatch, publica):
    sin_link = _asesor(token=None)
    lect = Lectores(monkeypatch, asesores=[sin_link],
                    reportes={sin_link.cedula: _reporte()})
    enviar, llamadas = _guion()

    assert await _diario(_bogota(7), enviar) is None
    assert llamadas == [] and lect.llamadas_reportes == 0


async def test_asesores_without_sales_are_remembered_for_the_day(
        monkeypatch, publica):
    sin_ventas = _asesor(cedula="5")
    lect = Lectores(monkeypatch, asesores=[sin_ventas], reportes={})
    enviar, llamadas = _guion()
    memoria = {}

    await _diario(_bogota(7), enviar, memoria)
    await _diario(_bogota(7, 5), enviar, memoria)

    assert llamadas == []
    assert lect.llamadas_reportes == 1
