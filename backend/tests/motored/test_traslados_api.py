"""Pending transfers API (odd/tasks/motored-traslados-pendientes.md, T2).

The service layer is stubbed (the pure rules have their own file and the
pg_real file proves the SQL); this covers roles, shape, filters, validations
and the public link's token/cédula/lock behaviour.
"""
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.services import informe_publico as publico
from app.motored.services import ingresos_pendientes as ip
from app.motored.services import traslados_pendientes as tp
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/gestion-repuestos/traslados"
TIENDA = uuid.uuid4()
OTRA = uuid.uuid4()
CARGA = datetime(2026, 10, 9, 7, 0, tzinfo=timezone.utc)
CEDULA = "79845123"
TOKEN = "t" * 64
LECTORES = ["ADMIN", "COMPRAS", "GERENCIA", "COORDINADOR_REPUESTOS",
            "ANALISTA_ADMINISTRATIVO"]


def _item(doc, estado="SIN_CONFIRMAR", dias=3, tienda=TIENDA, bodega="BA1"):
    return {
        "documento": doc, "bodega_salida": bodega, "sale": "Medellín",
        "sucursal_id": tienda, "llega": "Cali", "tienda": "Cali",
        "fecha": date(2026, 10, 5), "dias": dias, "refs": 1, "unidades": 2.0,
        "num_lineas": 1, "estado": estado, "aviso_erp": estado == "RECIBIDO",
        "lineas": [{"referencia": "R1", "descripcion": "P", "cantidad": 2.0}],
        "confirmado_por": None, "confirmado_en": None}


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "traslados-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "traslados-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "traslados-sonia")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def servicio(monkeypatch):
    items = [_item("79-1", "RECIBIDO", 9), _item("79-2", "SIN_CONFIRMAR", 3),
             _item("79-3", "NO_HA_LLEGADO", 1, OTRA)]

    async def pendientes(db, sucursal_ids=None, hoy=None):
        if sucursal_ids is None:
            return list(items)
        return [i for i in items if i["sucursal_id"] in set(sucursal_ids)]

    monkeypatch.setattr(tp, "pendientes", pendientes)
    monkeypatch.setattr(tp, "ultima_carga", AsyncMock(return_value=CARGA))
    return items


def _como(rol):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 12))


def _get(ruta="", **params):
    with TestClient(app) as client:
        return client.get(f"{BASE}{ruta}", params=params)


@pytest.mark.parametrize("ruta", ["", "/por-tienda", "/detalle"])
@pytest.mark.parametrize("rol", LECTORES)
def test_panel_roles_can_read(servicio, ruta, rol):
    _como(rol)
    r = _get(ruta)
    assert r.status_code == 200
    assert r.json()["ultima_carga"].startswith("2026-10-09T07:00")


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA", "SERVICIO_CLIENTE",
                                 "ASESOR_MOSTRADOR", "LIDER_INVENTARIOS"])
def test_other_roles_are_forbidden(servicio, rol):
    _como(rol)
    for ruta in ("", "/por-tienda", "/detalle", "/asesor"):
        assert _get(ruta).status_code == 403


def test_resumen_shape(servicio):
    _como("ADMIN")
    assert _get().json()["resumen"] == {
        "pendientes": 3, "recibidos_sin_erp": 1, "sin_confirmar": 1,
        "aun_no_llegan": 1,
        "mas_antiguo": {"documento": "79-1", "tienda": "Cali", "dias": 9},
        "lineas": 3}


def test_por_tienda_shape(servicio):
    _como("ADMIN")
    filas = _get("/por-tienda").json()["tiendas"]
    assert [f["pendientes"] for f in filas] == [2, 1]
    assert filas[0]["tienda"] == "Cali" and filas[0]["recibidos"] == 1
    assert filas[0]["mas_antiguo_dias"] == 9 and filas[0]["unidades"] == 4.0


def _docs(r):
    return [i["documento"] for i in r.json()["items"]]


def test_detalle_filters(servicio):
    _como("ADMIN")
    assert _docs(_get("/detalle")) == ["79-1", "79-2", "79-3"]
    assert _docs(_get("/detalle", sucursal=str(OTRA))) == ["79-3"]
    assert _docs(_get("/detalle", estado="RECIBIDO")) == ["79-1"]
    assert _docs(_get("/detalle", estado="SIN_CONFIRMAR")) == ["79-2"]
    assert _docs(_get("/detalle", min_dias=3)) == ["79-1", "79-2"]
    assert _get("/detalle", estado="LLEGO").status_code == 422


@pytest.mark.parametrize("minimo,maximo,esperado", [
    (None, 7, [0, 7]), (8, 15, [8, 15]), (16, None, [16, 40]),
    (7, 8, [7, 8]), (15, 16, [15, 16]),
])
def test_detalle_age_bands_are_inclusive_and_do_not_overlap(
        servicio, monkeypatch, minimo, maximo, esperado):
    _como("ADMIN")
    edades = [0, 7, 8, 15, 16, 40]

    async def pendientes(db, sucursal_ids=None, hoy=None):
        return [_item(f"79-{n}", dias=d) for n, d in enumerate(edades, 1)]

    monkeypatch.setattr(tp, "pendientes", pendientes)
    params = {k: v for k, v in (("min_dias", minimo), ("max_dias", maximo))
              if v is not None}
    assert [i["dias"] for i in _get("/detalle", **params).json()["items"]] == esperado


def test_detalle_min_above_max_is_a_422(servicio):
    _como("ADMIN")
    assert _get("/detalle", min_dias=9, max_dias=8).status_code == 422
    assert _get("/detalle", min_dias=8, max_dias=8).status_code == 200


def test_sin_snapshot_las_listas_van_vacias(servicio, monkeypatch):
    monkeypatch.setattr(tp, "pendientes", AsyncMock(return_value=[]))
    monkeypatch.setattr(tp, "ultima_carga", AsyncMock(return_value=None))
    _como("ADMIN")
    assert _get("/detalle").json() == {"ultima_carga": None, "items": []}
    assert _get("/por-tienda").json()["tiendas"] == []
    assert _get().json()["resumen"]["mas_antiguo"] is None


def test_historial_validates_and_answers(servicio, monkeypatch):
    historial = AsyncMock(return_value=[
        {"estado": "RECIBIDO", "por": "Ana", "canal": "web",
         "en": datetime(2026, 10, 7, tzinfo=timezone.utc)}])
    monkeypatch.setattr(tp, "historial", historial)
    _como("ADMIN")
    ok = _get("/historial", documento="79-1", bodega_salida="BA1")
    assert ok.status_code == 200 and ok.json()["historial"][0]["por"] == "Ana"
    assert historial.await_args.args[1:] == ("79-1", "BA1")
    assert _get("/historial", documento=" ", bodega_salida="BA1").status_code == 422


@pytest.mark.parametrize("rol", LECTORES)
def test_asesor_block_for_one_store(servicio, rol):
    _como(rol)
    r = _get("/asesor", sucursal=str(TIENDA))
    assert r.status_code == 200
    cuerpo = r.json()
    assert [i["documento"] for i in cuerpo["items"]] == ["79-1", "79-2"]
    assert cuerpo["resumen"]["pendientes"] == 2
    assert cuerpo["ultima_carga"].startswith("2026-10-09")
    assert _get("/asesor").status_code == 422


# ---------------------------------------------------------------------------
# Confirm (web)
# ---------------------------------------------------------------------------

def _usuario(**extra):
    base = dict(id=uuid.uuid4(), nombre="Ana", role="ADMIN", activo=True,
                status="approved", cedula=CEDULA, cedula_aprobada=True)
    base.update(extra)
    return Usuario(**base)


def _post_confirmar(rol, usuario, cuerpo=None):
    override_motored_user(MotoredUser(user_id=str(usuario.id), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))
    cuerpo = cuerpo or {"documento": "79-2", "bodega_salida": "BA1",
                        "estado": "RECIBIDO"}
    with TestClient(app) as client:
        return client.post(f"{BASE}/confirmar", json=cuerpo)


@pytest.mark.parametrize("rol", ["ADMIN", "COORDINADOR_REPUESTOS",
                                 "ANALISTA_ADMINISTRATIVO"])
def test_confirm_roles_and_actor_is_the_usuario(servicio, monkeypatch, rol):
    confirmar = AsyncMock(return_value=_item("79-2", "RECIBIDO"))
    monkeypatch.setattr(tp, "confirmar", confirmar)
    usuario = _usuario(role=rol)

    r = _post_confirmar(rol, usuario)

    assert r.status_code == 200 and r.json()["aviso_erp"] is True
    args = confirmar.await_args.args
    assert args[1:4] == ("79-2", "BA1", "RECIBIDO")
    assert args[4].nombre == "Ana" and args[4].usuario_id == usuario.id
    assert args[5] == "web"


@pytest.mark.parametrize("rol", ["COMPRAS", "GERENCIA", "SERVICIO_CLIENTE"])
def test_read_only_roles_cannot_confirm(servicio, monkeypatch, rol):
    confirmar = AsyncMock()
    monkeypatch.setattr(tp, "confirmar", confirmar)
    assert _post_confirmar(rol, _usuario(role=rol)).status_code == 403
    confirmar.assert_not_awaited()


def test_confirm_outside_the_snapshot_is_a_404(servicio, monkeypatch):
    monkeypatch.setattr(tp, "confirmar", AsyncMock(
        side_effect=tp.PendienteError(404, tp.MSG_NO_PENDIENTE)))
    r = _post_confirmar("ADMIN", _usuario())
    assert (r.status_code, r.json()["detail"]) == (404, tp.MSG_NO_PENDIENTE)


def test_confirm_bad_body_is_a_422(servicio):
    r = _post_confirmar("ADMIN", _usuario(), cuerpo={"documento": "79-2"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Public link
# ---------------------------------------------------------------------------

def _link(usuario, **extra):
    base = dict(id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
                token=TOKEN, intentos_fallidos=0)
    base.update(extra)
    return ReporteAsesorLink(**base)


def _post_publico(ruta, filas, cuerpo):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(filas))
    override_motored_db(sesion)
    return TestClient(app).post(
        f"/api/motored/publico/informe/{TOKEN}/{ruta}", json=cuerpo), sesion


def _cabeceras(r):
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_public_list_returns_the_stores_transfers(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario, intentos_fallidos=2)
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    bloque = {"ultima_carga": CARGA, "items": [_item("79-2")],
              "resumen": {"pendientes": 1}}
    para_asesor = AsyncMock(return_value=bloque)
    monkeypatch.setattr(tp, "para_asesor", para_asesor)

    r, sesion = _post_publico(
        "traslados", [[(link, usuario)]], {"cedula": "79.845.123"})

    assert r.status_code == 200
    assert r.json()["items"][0]["documento"] == "79-2"
    assert link.intentos_fallidos == 0 and sesion.committed
    assert para_asesor.await_args.args[1] == [TIENDA]
    _cabeceras(r)


def test_public_list_wrong_cedula_counts_and_commits_before_the_401(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario)
    para_asesor = AsyncMock()
    monkeypatch.setattr(tp, "para_asesor", para_asesor)

    r, sesion = _post_publico(
        "traslados", [[(link, usuario)]], {"cedula": "99999999"})

    assert (r.status_code, r.json()) == (401, {"detail": publico.MSG_GENERICO})
    assert link.intentos_fallidos == 1 and sesion.committed
    para_asesor.assert_not_awaited()
    _cabeceras(r)


def test_public_list_without_store_is_a_404(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[]))
    r, _ = _post_publico(
        "traslados", [[(_link(usuario), usuario)]], {"cedula": CEDULA})
    assert (r.status_code, r.json()["detail"]) == (404, ip.MSG_SIN_TIENDA)
    _cabeceras(r)


@pytest.mark.parametrize("ruta", ["traslados", "traslados/confirmar"])
def test_public_unknown_token_and_non_object_body(ruta):
    r, _ = _post_publico(ruta, [[]], {"cedula": CEDULA})
    assert (r.status_code, r.json()) == (401, {"detail": publico.MSG_GENERICO})
    _cabeceras(r)
    r, _ = _post_publico(ruta, [[]], ["x"])
    assert r.status_code == 401


def _cuerpo(**extra):
    base = {"cedula": CEDULA, "documento": "79-2", "bodega_salida": "BA1",
            "estado": "RECIBIDO"}
    base.update(extra)
    return base


def test_public_confirm_uses_the_asesor_stores_and_channel(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario, intentos_fallidos=2)
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    confirmar = AsyncMock(return_value=_item("79-2", "RECIBIDO"))
    monkeypatch.setattr(tp, "confirmar", confirmar)

    r, sesion = _post_publico(
        "traslados/confirmar", [[(link, usuario)]], _cuerpo(cedula="79.845.123"))

    assert r.status_code == 200 and r.json()["estado"] == "RECIBIDO"
    assert link.intentos_fallidos == 0 and sesion.committed
    args = confirmar.await_args
    assert args.args[1:4] == ("79-2", "BA1", "RECIBIDO")
    assert args.args[4].nombre == "Ana" and args.args[4].cedula == CEDULA
    assert args.args[5] == "link" and args.kwargs["tiendas"] == [TIENDA]
    _cabeceras(r)


def test_public_confirm_wrong_cedula_counts_and_commits_before_the_401(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario)
    confirmar = AsyncMock()
    monkeypatch.setattr(tp, "confirmar", confirmar)

    r, sesion = _post_publico(
        "traslados/confirmar", [[(link, usuario)]], _cuerpo(cedula="99999999"))

    assert (r.status_code, r.json()) == (401, {"detail": publico.MSG_GENERICO})
    assert link.intentos_fallidos == 1 and sesion.committed
    confirmar.assert_not_awaited()
    _cabeceras(r)


def test_public_confirm_respects_the_lock(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario, bloqueado_hasta=datetime(2999, 1, 1, tzinfo=timezone.utc))
    confirmar = AsyncMock()
    monkeypatch.setattr(tp, "confirmar", confirmar)

    r, _ = _post_publico("traslados/confirmar", [[(link, usuario)]], _cuerpo())

    assert r.status_code == 429
    confirmar.assert_not_awaited()
    _cabeceras(r)


def test_public_confirm_of_another_stores_transfer_is_a_404(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    monkeypatch.setattr(tp, "confirmar", AsyncMock(
        side_effect=tp.PendienteError(404, tp.MSG_NO_PENDIENTE)))
    r, _ = _post_publico(
        "traslados/confirmar", [[(_link(usuario), usuario)]], _cuerpo())
    assert (r.status_code, r.json()["detail"]) == (404, tp.MSG_NO_PENDIENTE)
    _cabeceras(r)


def test_public_confirm_validation_error_is_422(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    r, _ = _post_publico(
        "traslados/confirmar", [[(_link(usuario), usuario)]],
        _cuerpo(estado="LLEGO"))
    assert r.status_code == 422
    _cabeceras(r)
