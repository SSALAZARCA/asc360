"""
reporte_asesor_link (odd/motored-reporte-diario-asesor, T3a): the asesor's
permanent secret report link. Service rules against `FakeAsyncSession`
queues, plus the static migration checks. The HTTP layer and every
auto-revocation path live in `test_reporte_asesor_link_api.py`; the real
partial unique index in `pg_real/test_reporte_asesor_link_pg.py`.
"""
import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import settings
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario
from app.motored.services import reporte_asesor_link as servicio
from tests.motored.conftest import FakeAsyncSession

_RAIZ = Path(__file__).resolve().parents[2]
_MIGRACION = (
    _RAIZ / "alembic_motored" / "versions"
    / "86b1df9d3d5f_reporte_asesor_link.py")


def _usuario(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Ana Asesora", role="ASESOR_MOSTRADOR",
        activo=True, status="approved", telegram_id=555,
        cedula="79845123", cedula_aprobada=True,
    )
    base.update(overrides)
    return Usuario(**base)


def _link(usuario_id=None, **overrides) -> ReporteAsesorLink:
    base = dict(
        id=uuid.uuid4(), usuario_id=usuario_id or uuid.uuid4(),
        cedula="79845123", token="t" * 43,
        creado_en=datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc),
        intentos_fallidos=0,
    )
    base.update(overrides)
    return ReporteAsesorLink(**base)


def _sql(sesion, indice=0) -> str:
    stmt = sesion.executed_statements[indice]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


# --- link_activo ----------------------------------------------------------

async def test_link_activo_returns_the_unrevoked_row():
    link = _link()
    sesion = FakeAsyncSession(execute_queue=[[link]])

    assert await servicio.link_activo(sesion, link.usuario_id) is link
    assert "revocado_en IS NULL" in _sql(sesion)


async def test_link_activo_returns_none_without_a_link():
    sesion = FakeAsyncSession(execute_queue=[[]])

    assert await servicio.link_activo(sesion, uuid.uuid4()) is None


# --- generar_link ---------------------------------------------------------

@pytest.mark.parametrize("cambio, mensaje", [
    ({"activo": False}, "inactivo"),
    ({"status": "pending"}, "registro"),
    ({"cedula": None, "cedula_aprobada": False}, "cédula aprobada"),
    ({"cedula_aprobada": False}, "cédula aprobada"),
    ({"telegram_id": None}, "Telegram"),
])
async def test_generar_requires_an_eligible_usuario(cambio, mensaje):
    sesion = FakeAsyncSession()

    with pytest.raises(servicio.EnlaceNoPermitido, match=mensaje):
        await servicio.generar_link(sesion, _usuario(**cambio), uuid.uuid4())

    assert sesion.executed_statements == []
    assert sesion.added == []


async def test_generar_revokes_the_previous_link_then_creates_one():
    usuario = _usuario()
    admin_id = uuid.uuid4()
    sesion = FakeAsyncSession(execute_queue=[[]])

    link = await servicio.generar_link(sesion, usuario, admin_id)

    sql = _sql(sesion)
    assert sql.startswith("UPDATE reporte_asesor_link")
    assert "revocado_en IS NULL" in sql
    assert "'regenerado'" in sql
    assert str(usuario.id).replace("-", "") in sql.replace("-", "")
    assert sesion.added_of_type(ReporteAsesorLink) == [link]
    assert link.usuario_id == usuario.id
    assert link.cedula == "79845123"
    assert link.creado_por == admin_id
    assert link.creado_en is not None
    assert link.revocado_en is None
    assert len(link.token) >= 43


async def test_generar_twice_never_reuses_a_token():
    usuario = _usuario()
    sesion = FakeAsyncSession(execute_queue=[[], []])

    primero = await servicio.generar_link(sesion, usuario, uuid.uuid4())
    segundo = await servicio.generar_link(sesion, usuario, uuid.uuid4())

    assert primero.token != segundo.token
    assert all(
        _sql(sesion, i).startswith("UPDATE reporte_asesor_link")
        for i in (0, 1))


# --- anular_link ----------------------------------------------------------

async def test_anular_revokes_the_active_link_with_its_motivo():
    usuario_id = uuid.uuid4()
    sesion = FakeAsyncSession(execute_queue=[[]])

    await servicio.anular_link(sesion, usuario_id, "anulado por admin")

    sql = _sql(sesion)
    assert sql.startswith("UPDATE reporte_asesor_link")
    assert "'anulado por admin'" in sql
    assert "revocado_en IS NULL" in sql


# --- revocar_si_cambio ----------------------------------------------------

@pytest.mark.parametrize("cambio, motivo", [
    ({"activo": False}, "usuario desactivado"),
    ({"cedula": "11223344"}, "cédula cambiada"),
    ({"cedula": None, "cedula_aprobada": False}, "cédula cambiada"),
    ({"cedula_aprobada": False}, "cédula cambiada"),
    ({"telegram_id": 999}, "telegram cambiado"),
    ({"telegram_id": None}, "telegram cambiado"),
])
async def test_revocar_si_cambio_revokes_on_each_change(cambio, motivo):
    usuario = _usuario()
    antes = servicio.huella(usuario)
    for campo, valor in cambio.items():
        setattr(usuario, campo, valor)
    sesion = FakeAsyncSession(execute_queue=[[]])

    assert await servicio.revocar_si_cambio(sesion, usuario, antes) is True

    assert f"'{motivo}'" in _sql(sesion)


async def test_revocar_si_cambio_skips_an_unchanged_usuario():
    usuario = _usuario()
    antes = servicio.huella(usuario)
    sesion = FakeAsyncSession()

    assert await servicio.revocar_si_cambio(sesion, usuario, antes) is False
    assert sesion.executed_statements == []


async def test_revocar_si_cambio_skips_a_usuario_that_had_no_link():
    usuario = _usuario(cedula_aprobada=False)
    antes = servicio.huella(usuario)
    usuario.cedula = None
    sesion = FakeAsyncSession()

    assert await servicio.revocar_si_cambio(sesion, usuario, antes) is False
    assert sesion.executed_statements == []


async def test_revocar_por_telegram_nuevo_only_with_an_approved_cedula():
    sin = FakeAsyncSession()
    con = FakeAsyncSession(execute_queue=[[]])

    assert await servicio.revocar_por_telegram_nuevo(
        sin, _usuario(cedula_aprobada=None)) is False
    assert await servicio.revocar_por_telegram_nuevo(con, _usuario()) is True

    assert sin.executed_statements == []
    assert "'telegram cambiado'" in _sql(con)


# --- url_del_link / mensaje / estado --------------------------------------

def test_url_requires_motored_public_url(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", "")

    with pytest.raises(
            servicio.FaltaConfiguracion,
            match="Falta configurar MOTORED_PUBLIC_URL"):
        servicio.url_del_link("abc")


def test_url_joins_the_public_base_and_the_token(monkeypatch):
    monkeypatch.setattr(
        settings, "MOTORED_PUBLIC_URL", "https://motored.example.co/")

    assert servicio.url_del_link("abc") == (
        "https://motored.example.co/motored/informe/abc")


def test_mensaje_names_the_asesor_and_carries_the_url():
    texto = servicio.texto_mensaje("Ana", "https://x.co/motored/informe/t")

    assert texto == (
        "Hola Ana, este es tu enlace personal al informe de ventas y "
        "comisión. Ábrelo y escribe tu cédula para verlo: "
        "https://x.co/motored/informe/t\nNo lo compartas.")


def test_estado_never_carries_the_token():
    link = _link(ultimo_acceso_en=None)

    estado = servicio.estado(link)

    assert estado == {
        "activo": True,
        "creado_en": "2026-10-08T14:00:00+00:00",
        "ultimo_acceso_en": None,
    }
    assert servicio.estado(None) == {
        "activo": False, "creado_en": None, "ultimo_acceso_en": None,
    }


# --- migration (static) ---------------------------------------------------

def _migracion():
    spec = importlib.util.spec_from_file_location(
        "reporte_asesor_link_mig", _MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_migration_is_the_single_head_on_top_of_the_cedula():
    guion = ScriptDirectory.from_config(
        Config(str(_RAIZ / "alembic_motored.ini")))

    # The head itself is pinned in test_migration_fase4.py; here only
    # check the chain stays linear and this revision sits on the cédula.
    assert len(guion.get_heads()) == 1
    assert _migracion().down_revision == "c6d2f8a41b97"


def test_migration_creates_the_table_and_the_partial_index():
    modulo = _migracion()
    with patch.object(modulo, "op") as op_mock:
        modulo.upgrade()

    tabla = op_mock.create_table.call_args
    columnas = {
        c.name: c for c in tabla.args[1:] if hasattr(c, "nullable")}
    assert tabla.args[0] == "reporte_asesor_link"
    assert set(columnas) == {
        "id", "usuario_id", "cedula", "token", "creado_en", "creado_por",
        "revocado_en", "motivo_revocacion", "ultimo_acceso_en",
        "intentos_fallidos", "bloqueado_hasta",
    }
    assert not columnas["intentos_fallidos"].nullable
    assert columnas["bloqueado_hasta"].nullable
    indice = op_mock.create_index.call_args
    assert indice.args[0] == "uq_reporte_asesor_link_activo"
    assert indice.kwargs["unique"] is True
    assert str(indice.kwargs["postgresql_where"]) == "revocado_en IS NULL"


def test_migration_downgrade_drops_the_index_then_the_table():
    modulo = _migracion()
    with patch.object(modulo, "op") as op_mock:
        modulo.downgrade()

    nombres = [c[0] for c in op_mock.method_calls]
    assert nombres == ["drop_index", "drop_table"]
