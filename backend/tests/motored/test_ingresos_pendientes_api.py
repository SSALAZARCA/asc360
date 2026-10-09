"""Pending invoice ingresos API (odd/tasks/motored-ingresos-pendientes.md, P1).

The service layer is stubbed here (the pure rule has its own file and the
pg_real file proves the SQL); this covers roles, shape, validations and the
public confirm's token/lock behaviour.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal as D
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.services import informe_publico as publico
from app.motored.services import ingresos_pendientes as ip
from app.motored.services import sucursal_grupo
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/gestion-repuestos/ingresos-facturas"
TIENDA = uuid.uuid4()
OTRA = uuid.uuid4()
DESDE = date(2026, 9, 1)
CEDULA = "79845123"
TOKEN = "t" * 64


def _item(numero, estado="SIN_CONFIRMAR", dias=3, tienda=TIENDA):
    return {
        "prefijo_rh": "RH", "numero_rh": numero, "factura": f"RH {numero}",
        "sucursal_id": tienda, "tienda": "Cali", "fecha": date(2026, 10, 5),
        "dias": dias, "unidades": 2.0, "valor": 100.0, "estado": estado,
        "confirmado_por": None, "confirmado_en": None}


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "ingresos-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "ingresos-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "ingresos-sonia")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def servicio(monkeypatch):
    items = [_item(1, "LLEGO", 9), _item(2, "SIN_CONFIRMAR", 3),
             _item(3, "NO_HA_LLEGADO", 1, OTRA)]

    async def pendientes(db, sucursal_ids=None, hoy=None):
        if sucursal_ids is None:
            return list(items)
        return [i for i in items if i["sucursal_id"] in set(sucursal_ids)]

    monkeypatch.setattr(ip, "verificable_desde", AsyncMock(return_value=DESDE))
    monkeypatch.setattr(ip, "pendientes", pendientes)
    monkeypatch.setattr(
        sucursal_grupo, "principal_de",
        AsyncMock(return_value={TIENDA: TIENDA, OTRA: OTRA}))
    return items


def _como(rol, filas=()):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    override_motored_db(FakeAsyncSession(execute_queue=[[]] * 12))


def _get(ruta="", **params):
    with TestClient(app) as client:
        return client.get(f"{BASE}{ruta}", params=params)


@pytest.mark.parametrize("ruta", ["", "/por-tienda", "/detalle"])
@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "GERENCIA", "COORDINADOR_REPUESTOS"])
def test_panel_roles_can_read(servicio, ruta, rol):
    _como(rol)
    r = _get(ruta)
    assert r.status_code == 200
    assert r.json()["verificable_desde"] == "2026-09-01"


@pytest.mark.parametrize("rol", ["SUCURSAL", "CONSULTA", "SERVICIO_CLIENTE"])
def test_other_roles_are_forbidden(servicio, rol):
    _como(rol)
    assert _get().status_code == 403
    assert _get("/detalle").status_code == 403


def test_resumen_shape(servicio):
    _como("ADMIN")
    assert _get().json()["resumen"] == {
        "pendientes": 3, "llegaron_sin_ingresar": 1, "sin_confirmar": 1,
        "aun_no_llegan": 1, "mas_antigua": 9, "valor_pendiente": 300.0}


def test_por_tienda_shape(servicio):
    _como("ADMIN")
    filas = _get("/por-tienda").json()["tiendas"]
    assert [f["pendientes"] for f in filas] == [2, 1]
    assert filas[0]["tienda"] == "Cali" and filas[0]["mas_antigua"] == 9


def test_detalle_filters(servicio):
    _como("ADMIN")
    assert [i["numero_rh"] for i in _get("/detalle").json()["items"]] == [1, 2, 3]
    assert [i["numero_rh"] for i in _get("/detalle", sucursal=str(OTRA)).json()["items"]] == [3]
    assert [i["numero_rh"] for i in _get("/detalle", estado="LLEGO").json()["items"]] == [1]
    assert [i["numero_rh"] for i in _get("/detalle", min_dias=3).json()["items"]] == [1, 2]
    assert _get("/detalle", estado="X").status_code == 422


def test_nothing_verifiable_gives_empty_lists_and_a_null_flag(servicio, monkeypatch):
    monkeypatch.setattr(ip, "verificable_desde", AsyncMock(return_value=None))
    _como("ADMIN")
    assert _get("/detalle").json() == {"verificable_desde": None, "items": []}
    assert _get().json()["resumen"]["pendientes"] == 0
    assert _get("/por-tienda").json()["tiendas"] == []


def test_historial_validates_the_factura(servicio, monkeypatch):
    monkeypatch.setattr(ip, "historial", AsyncMock(return_value=[
        {"estado": "LLEGO", "por": "Ana", "canal": "web",
         "en": datetime(2026, 10, 7, tzinfo=timezone.utc)}]))
    _como("ADMIN")
    ok = _get("/historial", factura="RH 1", sucursal=str(TIENDA))
    assert ok.status_code == 200 and ok.json()["historial"][0]["por"] == "Ana"
    assert _get("/historial", factura="x", sucursal=str(TIENDA)).status_code == 422


def _usuario(**extra):
    base = dict(id=uuid.uuid4(), nombre="Ana", role="ADMIN", activo=True,
                status="approved", cedula=CEDULA, cedula_aprobada=True)
    base.update(extra)
    return Usuario(**base)


def _post_confirmar(rol, usuario, cuerpo=None, filas=()):
    override_motored_user(MotoredUser(user_id=str(usuario.id), role=rol))
    sesion = FakeAsyncSession(execute_queue=[[], [usuario], *filas])
    override_motored_db(sesion)
    cuerpo = cuerpo or {"factura": "RH 2", "sucursal_id": str(TIENDA), "estado": "LLEGO"}
    with TestClient(app) as client:
        return client.post(f"{BASE}/confirmar", json=cuerpo), sesion


def test_coordinador_confirms_and_the_actor_is_the_usuario(servicio, monkeypatch):
    confirmar = AsyncMock(return_value=_item(2, "LLEGO"))
    monkeypatch.setattr(ip, "confirmar", confirmar)
    usuario = _usuario(role="COORDINADOR_REPUESTOS")

    r, _ = _post_confirmar("COORDINADOR_REPUESTOS", usuario)

    assert r.status_code == 200 and r.json()["estado"] == "LLEGO"
    args = confirmar.await_args.args
    assert args[1:4] == ("RH 2", TIENDA, "LLEGO")
    assert args[4].nombre == "Ana" and args[4].usuario_id == usuario.id
    assert args[5] == "web"


@pytest.mark.parametrize("rol", ["ADMIN", "COMPRAS", "GERENCIA", "SERVICIO_CLIENTE"])
def test_only_the_coordinador_may_confirm(servicio, monkeypatch, rol):
    confirmar = AsyncMock()
    monkeypatch.setattr(ip, "confirmar", confirmar)
    r, _ = _post_confirmar(rol, _usuario(role=rol))
    assert r.status_code == 403
    confirmar.assert_not_awaited()


def test_not_pending_is_a_409(servicio, monkeypatch):
    monkeypatch.setattr(ip, "confirmar", AsyncMock(
        side_effect=ip.PendienteError(409, ip.MSG_NO_PENDIENTE)))
    r, _ = _post_confirmar("COORDINADOR_REPUESTOS", _usuario())
    assert (r.status_code, r.json()["detail"]) == (409, ip.MSG_NO_PENDIENTE)


def test_a_bad_body_is_a_422(servicio):
    r, _ = _post_confirmar("COORDINADOR_REPUESTOS", _usuario(), cuerpo={"factura": "RH 2"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Public confirm
# ---------------------------------------------------------------------------

def _link(usuario, **extra):
    base = dict(id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
                token=TOKEN, intentos_fallidos=0)
    base.update(extra)
    return ReporteAsesorLink(**base)


def _post_publico(filas, cuerpo):
    sesion = FakeAsyncSession(execute_queue=[[]] + list(filas))
    override_motored_db(sesion)
    return TestClient(app).post(
        f"/api/motored/publico/informe/{TOKEN}/pendientes", json=cuerpo), sesion


def _cuerpo(**extra):
    base = {"cedula": CEDULA, "factura": "RH 2", "estado": "LLEGO"}
    base.update(extra)
    return base


def _cabeceras(r):
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_public_confirm_uses_the_link_asesor_store_and_channel(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario, intentos_fallidos=2)
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    confirmar = AsyncMock(return_value=_item(2, "LLEGO"))
    monkeypatch.setattr(ip, "confirmar", confirmar)

    r, sesion = _post_publico([[(link, usuario)]], _cuerpo(cedula="79.845.123"))

    assert r.status_code == 200 and r.json()["estado"] == "LLEGO"
    assert link.intentos_fallidos == 0 and sesion.committed
    args = confirmar.await_args.args
    assert args[1:4] == ("RH 2", TIENDA, "LLEGO")
    assert args[4].nombre == "Ana" and args[4].cedula == CEDULA and args[5] == "link"
    _cabeceras(r)


def test_public_confirm_wrong_cedula_counts_and_commits_before_the_401(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario)
    confirmar = AsyncMock()
    monkeypatch.setattr(ip, "confirmar", confirmar)

    r, sesion = _post_publico([[(link, usuario)]], _cuerpo(cedula="99999999"))

    assert (r.status_code, r.json()) == (401, {"detail": publico.MSG_GENERICO})
    assert link.intentos_fallidos == 1 and sesion.committed
    confirmar.assert_not_awaited()
    _cabeceras(r)


def test_public_confirm_respects_the_lock(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    link = _link(usuario, bloqueado_hasta=datetime(2999, 1, 1, tzinfo=timezone.utc))
    confirmar = AsyncMock()
    monkeypatch.setattr(ip, "confirmar", confirmar)

    r, _ = _post_publico([[(link, usuario)]], _cuerpo())

    assert r.status_code == 429
    confirmar.assert_not_awaited()
    _cabeceras(r)


def test_public_confirm_unknown_token_and_non_object_body():
    r, _ = _post_publico([[]], _cuerpo())
    assert (r.status_code, r.json()) == (401, {"detail": publico.MSG_GENERICO})
    _cabeceras(r)
    r, _ = _post_publico([[]], ["x"])
    assert r.status_code == 401


def test_public_confirm_without_store_is_a_404(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[]))
    r, _ = _post_publico([[(_link(usuario), usuario)]], _cuerpo())
    assert (r.status_code, r.json()["detail"]) == (404, ip.MSG_SIN_TIENDA)
    _cabeceras(r)


def test_public_confirm_not_pending_is_409_with_headers(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    monkeypatch.setattr(ip, "confirmar", AsyncMock(
        side_effect=ip.PendienteError(409, ip.MSG_NO_PENDIENTE)))
    r, _ = _post_publico([[(_link(usuario), usuario)]], _cuerpo())
    assert (r.status_code, r.json()["detail"]) == (409, ip.MSG_NO_PENDIENTE)
    _cabeceras(r)


def test_public_confirm_validation_error_is_422(monkeypatch):
    usuario = _usuario(role="ASESOR_MOSTRADOR")
    monkeypatch.setattr(ip, "tiendas_de_asesor", AsyncMock(return_value=[TIENDA]))
    r, _ = _post_publico([[(_link(usuario), usuario)]], _cuerpo(estado="HOLA"))
    assert r.status_code == 422
    _cabeceras(r)
