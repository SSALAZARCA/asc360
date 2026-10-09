"""
Inventory counts, reconteo -- leader side (odd/motored-conteos-
inventario, WU9; design §5.1, §5.2, §6.1, §7, ADR-4).

Pure rules first (valuation, the reconteo threshold, the critical flag,
the final quantity, the different-pair decision and the auto-assign
balance), then the HTTP layer with the services stubbed: scoping (a
leader only reaches its own conteos, another's is a 404), GERENCIA reads
the differences and gets 403 on every write. The SQL itself (the one
aggregate, voided readings, sums across locations, the disjoint-cédula
rule) runs for real in `pg_real/test_conteos_reconteos_pg.py`.
"""
import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import (
    diferencias, errores, reconteos, sesiones,
)
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/conteos"
UTC = datetime.timezone.utc
AHORA = datetime.datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
LIDER_ID = uuid.uuid4()
OTRO_LIDER_ID = uuid.uuid4()
UMBRAL = Decimal("100000")
CRITICO = Decimal("500000")
D = Decimal


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-rec")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-rec-asc360")
    yield
    app.dependency_overrides.clear()


# --- pure rules: valuation, threshold, critical ------------------------------


def _cruda(sistema=None, ronda1=None, costo=None, fuente="BODEGA",
           reconteo_estado=None, ronda2=None, codigo="R-1"):
    return diferencias.FilaCruda(
        referencia_id=uuid.uuid4(), codigo=codigo, nombre="Pastilla",
        sistema=sistema, ronda1=ronda1, costo_unitario=costo,
        costo_fuente=fuente, ubicaciones=["Estante A3"],
        reconteo_id=None if reconteo_estado is None else uuid.uuid4(),
        reconteo_estado=reconteo_estado, reconteo_origen="UMBRAL",
        reconteo_sesion_id=None, misma_pareja_autorizada=False,
        ronda2=ronda2)


def test_a_referencia_with_no_reading_counts_as_zero():
    fila = diferencias.calcular(_cruda(D("10"), None, D("50000")), CRITICO)

    assert (fila.contado, fila.diferencia) == (D("0"), D("-10"))
    assert fila.valor == D("-500000.00")
    assert fila.critico


def test_a_surplus_outside_the_snapshot_has_system_zero_and_no_cost():
    fila = diferencias.calcular(
        _cruda(None, D("2"), None, fuente=None), CRITICO)

    assert (fila.sistema, fila.contado, fila.diferencia) == (
        D("0"), D("2"), D("2"))
    assert fila.sin_costo and fila.valor is None
    assert not fila.critico


def test_a_sin_costo_line_is_never_valued():
    fila = diferencias.calcular(
        _cruda(D("4"), D("1"), D("900"), fuente="SIN_COSTO"), CRITICO)

    assert fila.sin_costo and fila.valor is None


def test_the_value_is_rounded_to_cents():
    assert diferencias.valorar(D("-3"), D("1234.567")) == D("-3703.70")
    assert diferencias.valorar(D("2"), None) is None


@pytest.mark.parametrize("diferencia, valor, esperado", [
    (D("-10"), D("-500000"), True),
    (D("-5"), D("-100000"), True),
    (D("5"), D("99999.99"), False),
    (D("1"), None, True),
    (D("0"), None, False),
    (D("0"), D("0"), False),
])
def test_the_reconteo_threshold_is_inclusive_and_catches_sin_costo(
        diferencia, valor, esperado):
    assert diferencias.requiere_reconteo(
        diferencia, valor, UMBRAL) is esperado


@pytest.mark.parametrize("valor, esperado", [
    (D("-500000"), True), (D("499999.99"), False),
    (D("700000"), True), (None, False)])
def test_the_critical_flag_uses_the_frozen_critical_amount(valor, esperado):
    assert diferencias.es_critica(valor, CRITICO) is esperado


# --- the final quantity (WU10 uses it) ---------------------------------------


@pytest.mark.parametrize("estado, ronda2, esperado", [
    (None, None, D("7")),
    ("PENDIENTE", None, D("7")),
    ("ASIGNADO", D("3"), D("7")),
    ("CANCELADO", D("3"), D("7")),
    ("TERMINADO", D("3"), D("3")),
    ("TERMINADO", None, D("0")),
])
def test_a_finished_reconteo_replaces_round_one(estado, ronda2, esperado):
    assert diferencias.cantidad_final(D("7"), estado, ronda2) == esperado


def test_the_difference_uses_the_final_quantity():
    fila = diferencias.calcular(_cruda(
        D("10"), D("2"), D("1000"), reconteo_estado="TERMINADO",
        ronda2=D("10")), CRITICO)

    assert (fila.contado_ronda1, fila.contado) == (D("2"), D("10"))
    assert fila.diferencia == D("0") and fila.valor == D("0.00")
    assert fila.reconteo.estado == "TERMINADO"


# --- order and filters -------------------------------------------------------


def _lista():
    return [
        diferencias.calcular(_cruda(D("1"), D("0"), D("1000"),
                                    codigo="CHICA"), CRITICO),
        diferencias.calcular(_cruda(None, D("3"), None, fuente=None,
                                    codigo="SOBRA"), CRITICO),
        diferencias.calcular(_cruda(D("0"), D("20"), D("30000"),
                                    codigo="GRANDE"), CRITICO),
        diferencias.calcular(_cruda(D("9"), D("4"), D("40000"),
                                    reconteo_estado="PENDIENTE",
                                    codigo="MEDIA"), CRITICO),
    ]


def test_differences_sort_by_absolute_value_then_unvalued_last():
    orden = [f.codigo for f in diferencias.ordenar(_lista())]

    assert orden == ["GRANDE", "MEDIA", "CHICA", "SOBRA"]


def test_differences_filter_critical_and_in_reconteo():
    lista = diferencias.ordenar(_lista())

    assert [f.codigo for f in diferencias.filtrar(lista, "criticas")] == [
        "GRANDE"]
    assert [f.codigo for f in diferencias.filtrar(lista, "reconteo")] == [
        "MEDIA"]
    assert len(diferencias.filtrar(lista, "todas")) == 4


# --- the different-pair decision (ADR-4) -------------------------------------


def test_an_eligible_pair_needs_no_override():
    assert reconteos.decidir_asignacion(
        elegible=True, hay_elegibles=True, autorizar=True,
        motivo=None) is False


def test_the_same_pair_without_override_is_refused():
    with pytest.raises(errores.MismaPareja):
        reconteos.decidir_asignacion(
            elegible=False, hay_elegibles=False, autorizar=False,
            motivo="x")


def test_the_override_is_refused_while_another_pair_is_eligible():
    with pytest.raises(errores.HayParejaElegible):
        reconteos.decidir_asignacion(
            elegible=False, hay_elegibles=True, autorizar=True,
            motivo="solo hay una")


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_the_override_needs_a_reason(motivo):
    with pytest.raises(errores.MotivoRequerido):
        reconteos.decidir_asignacion(
            elegible=False, hay_elegibles=False, autorizar=True,
            motivo=motivo)


def test_the_override_with_a_reason_and_no_eligible_pair_is_allowed():
    assert reconteos.decidir_asignacion(
        elegible=False, hay_elegibles=False, autorizar=True,
        motivo="Solo vino una pareja") is True


# --- auto-assign balance -----------------------------------------------------


def test_auto_assign_balances_and_reports_the_ones_without_a_pair():
    s1, s2 = uuid.uuid4(), uuid.uuid4()
    r = [uuid.uuid4() for _ in range(5)]
    elegibles = {r[0]: [s1, s2], r[1]: [s1, s2], r[2]: [s1, s2],
                 r[3]: [s1, s2], r[4]: []}

    reparto = reconteos.repartir(r, elegibles, {s1: 1})

    cuenta = {s1: 1, s2: 0}
    for sesion in reparto.asignaciones.values():
        cuenta[sesion] += 1
    assert cuenta == {s1: 3, s2: 2}
    assert reparto.sin_pareja == [r[4]]
    assert r[4] not in reparto.asignaciones


def test_auto_assign_serves_the_most_constrained_reconteo_first():
    s1, s2 = uuid.uuid4(), uuid.uuid4()
    libre, atada = uuid.uuid4(), uuid.uuid4()

    reparto = reconteos.repartir(
        [libre, atada], {libre: [s1, s2], atada: [s1]}, {})

    assert reparto.asignaciones == {atada: s1, libre: s2}


# --- HTTP: scoping and RBAC --------------------------------------------------


def _usuario(rol):
    ids = {"LIDER_INVENTARIOS": LIDER_ID}
    return MotoredUser(user_id=str(ids.get(rol, uuid.uuid4())), role=rol)


def _conteo(estado="EN_RECONTEO", lider_id=LIDER_ID):
    return Conteo(
        id=uuid.uuid4(), tipo="TOTAL", estado=estado, origen="MANUAL",
        sucursal_id=uuid.uuid4(), lider_id=lider_id,
        fecha_programada=AHORA.date(), created_at=AHORA,
        snapshot_tomado_en=AHORA, umbral_reconteo_pesos=UMBRAL,
        umbral_critico_pesos=CRITICO)


def _llamar(rol, metodo, ruta, conteo=None, cola=None, json=None):
    override_motored_user(_usuario(rol))
    db = FakeAsyncSession(
        execute_queue=[[]] + list(cola or []),
        get_queue=[conteo] if conteo is not None else [None])
    override_motored_db(db)
    return TestClient(app).request(metodo, BASE + ruta, json=json), db


RID, SID = uuid.uuid4(), uuid.uuid4()
ESCRITURAS = [
    ("POST", "/{id}/terminar-ronda", None),
    ("POST", "/{id}/reconteos", {"codigo": "R-1"}),
    ("POST", f"/{{id}}/reconteos/{RID}/asignar", {"sesion_id": str(SID)}),
    ("POST", "/{id}/reconteos/auto-asignar", None),
    ("POST", f"/{{id}}/reconteos/{RID}/cancelar", None),
]


@pytest.mark.parametrize("metodo, ruta, cuerpo", ESCRITURAS)
def test_gerencia_gets_403_on_every_reconteo_write(metodo, ruta, cuerpo):
    conteo = _conteo()

    r, _ = _llamar(
        "GERENCIA", metodo, ruta.format(id=conteo.id), conteo, json=cuerpo)

    assert r.status_code == 403, r.text


@pytest.mark.parametrize("metodo, ruta, cuerpo", ESCRITURAS + [
    ("GET", "/{id}/diferencias", None)])
def test_another_leaders_conteo_is_a_404_on_reconteo_routes(
        metodo, ruta, cuerpo):
    conteo = _conteo(lider_id=OTRO_LIDER_ID)

    r, _ = _llamar(
        "LIDER_INVENTARIOS", metodo, ruta.format(id=conteo.id), conteo,
        json=cuerpo)

    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "CONTEO_NO_ENCONTRADO"


def _diferencia(**extra):
    fila = diferencias.calcular(_cruda(
        D("10"), D("0"), D("60000"), reconteo_estado="ASIGNADO"), CRITICO)
    vista = fila.reconteo._replace(sesion_id=SID)
    return fila._replace(reconteo=vista, **extra)


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS", "GERENCIA"])
def test_readers_see_the_differences_with_the_assigned_pair(
        monkeypatch, rol):
    conteo = _conteo()
    monkeypatch.setattr(diferencias, "listar", AsyncMock(
        return_value=[_diferencia()]))
    monkeypatch.setattr(sesiones, "listar", AsyncMock(return_value=[
        sesiones.FilaSesion(
            type("S", (), {"id": SID})(), 2, [], None)]))

    r, _ = _llamar(rol, "GET", f"/{conteo.id}/diferencias", conteo)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["parcial"], cuerpo["total"], cuerpo["criticas"]) == (
        False, 1, 1)
    item = cuerpo["items"][0]
    assert (item["sistema"], item["contado"], item["diferencia"]) == (
        "10", "0", "-10")
    assert item["valor"] == "-600000.00" and item["critico"] is True
    assert item["reconteo"]["estado"] == "ASIGNADO"
    assert item["reconteo"]["sesion"] == {
        "id": str(SID), "etiqueta": "Pareja 2 · "}
    assert item["ubicaciones"] == ["Estante A3"]


def test_the_differences_filter_is_validated():
    conteo = _conteo()

    r, _ = _llamar(
        "ADMIN", "GET", f"/{conteo.id}/diferencias?filtro=otras", conteo)

    assert r.status_code == 422


def test_the_leader_ends_round_one(monkeypatch):
    conteo = _conteo("EN_CONTEO")
    fin = reconteos.FinRonda(conteo, diferencias=7, reconteos=3)
    terminar = AsyncMock(return_value=fin)
    monkeypatch.setattr(reconteos, "terminar_ronda", terminar)

    r, db = _llamar(
        "LIDER_INVENTARIOS", "POST", f"/{conteo.id}/terminar-ronda", conteo)

    assert r.status_code == 200, r.text
    assert r.json()["diferencias"] == 7
    assert r.json()["reconteos_creados"] == 3
    assert terminar.await_args.args[1] == conteo.id
    assert db.committed


def _reconteo(conteo, **extra):
    valores = dict(
        id=RID, conteo_id=conteo.id, codigo="R-1", estado="ASIGNADO",
        origen="LIDER", sesion_id=SID, misma_pareja_autorizada=True,
        motivo_autorizacion="Solo una pareja", asignado_en=AHORA,
        diferencia_ronda1=D("-2"), valor_ronda1=D("-2000.00"))
    valores.update(extra)
    return ConteoReconteo(**valores)


def test_the_leader_assigns_with_an_override(monkeypatch):
    conteo = _conteo()
    asignar = AsyncMock(return_value=_reconteo(conteo))
    monkeypatch.setattr(reconteos, "asignar", asignar)

    r, db = _llamar(
        "ADMIN", "POST", f"/{conteo.id}/reconteos/{RID}/asignar", conteo,
        json={"sesion_id": str(SID), "autorizar_misma_pareja": True,
              "motivo": "Solo una pareja"})

    assert r.status_code == 200, r.text
    assert r.json()["misma_pareja_autorizada"] is True
    assert r.json()["motivo_autorizacion"] == "Solo una pareja"
    kwargs = asignar.await_args.kwargs
    assert (kwargs["autorizar"], kwargs["motivo"]) == (
        True, "Solo una pareja")
    assert db.committed


@pytest.mark.parametrize("error, estado, codigo", [
    (errores.MismaPareja(), 409, "MISMA_PAREJA"),
    (errores.HayParejaElegible(), 409, "HAY_PAREJA_ELEGIBLE"),
    (errores.SesionNoDisponible(), 409, "SESION_NO_DISPONIBLE"),
    (errores.ReconteoNoEncontrado(), 404, "RECONTEO_NO_ENCONTRADO"),
    (errores.MotivoRequerido(), 422, "MOTIVO_REQUERIDO"),
])
def test_assignment_errors_map_to_http(monkeypatch, error, estado, codigo):
    conteo = _conteo()
    monkeypatch.setattr(reconteos, "asignar", AsyncMock(side_effect=error))

    r, db = _llamar(
        "ADMIN", "POST", f"/{conteo.id}/reconteos/{RID}/asignar", conteo,
        json={"sesion_id": str(SID)})

    assert r.status_code == estado, r.text
    assert r.json()["detail"]["code"] == codigo
    assert not db.committed


def test_a_manual_reconteo_for_a_duplicate_code_is_a_409(monkeypatch):
    conteo = _conteo()
    monkeypatch.setattr(reconteos, "crear_manual", AsyncMock(
        side_effect=errores.ReconteoDuplicado()))

    r, _ = _llamar(
        "ADMIN", "POST", f"/{conteo.id}/reconteos", conteo,
        json={"codigo": "R-1"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "RECONTEO_DUPLICADO"


def test_auto_assign_reports_what_stayed_without_a_pair(monkeypatch):
    conteo = _conteo()
    pendiente = _reconteo(
        conteo, id=uuid.uuid4(), estado="PENDIENTE", sesion_id=None,
        misma_pareja_autorizada=False, motivo_autorizacion=None)
    asignado = _reconteo(conteo, misma_pareja_autorizada=False,
                         motivo_autorizacion=None)
    monkeypatch.setattr(reconteos, "auto_asignar", AsyncMock(
        return_value=reconteos.ResultadoReparto([asignado], [pendiente])))

    r, db = _llamar(
        "LIDER_INVENTARIOS", "POST", f"/{conteo.id}/reconteos/auto-asignar",
        conteo)

    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["asignados"]] == [str(RID)]
    assert [x["id"] for x in r.json()["sin_pareja"]] == [str(pendiente.id)]
    assert db.committed


def test_the_leader_cancels_a_reconteo(monkeypatch):
    conteo = _conteo()
    cancelado = _reconteo(conteo, estado="CANCELADO", cancelado_en=AHORA)
    monkeypatch.setattr(
        reconteos, "cancelar", AsyncMock(return_value=cancelado))

    r, db = _llamar(
        "LIDER_INVENTARIOS", "POST",
        f"/{conteo.id}/reconteos/{RID}/cancelar", conteo)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "CANCELADO"
    assert db.committed
