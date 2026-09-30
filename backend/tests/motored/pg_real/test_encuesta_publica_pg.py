"""
Motored satisfaction survey: submitting a response against a real Postgres
(opt-in, `MOTORED_TEST_PG_URL`, database migrated to head).

Regression for the 2026-09-30 production bug: a detractor response (overall
satisfaction 3 or less) failed with a foreign-key violation because the case
row was inserted before the response it points to, and the IntegrityError was
reported to the customer as "already answered" (409). The fake session used
by the API tests cannot catch insert ordering, so these run on Postgres.

`registrar_respuesta` commits, so each test seeds its own random identity and
the rows stay in the throwaway test database (the action log is append-only
by trigger, so it cannot be cleaned up anyway).
"""
import os
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.models.encuesta_respuesta import EncuestaRespuesta
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import encuesta_publica as servicio

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

MATRIX = [
    "p_explicacion_tecnica", "p_confianza_reparacion", "p_servicio_taller",
    "p_calidad_mecanicos", "p_claridad_cobros", "p_originalidad_repuestos",
]


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
    await motor.dispose()


async def _registro(db) -> tuple:
    """Seed one surveyable record; returns (registro_id, cedula, last-4)."""
    suffix = uuid.uuid4().int % 10**8
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Admin", role=MotoredRole.ADMIN, activo=True,
        email=f"admin{suffix}@test.co", hashed_password="x",
    )
    db.add(usuario)
    await db.flush()
    carga = EncuestaCarga(id=uuid.uuid4(), nombre_archivo="t.xlsx", total_registros=1, usuario_id=usuario.id)
    db.add(carga)
    await db.flush()
    cedula, celular = str(suffix), f"300{suffix:07d}"
    registro = EncuestaRegistro(
        id=uuid.uuid4(), carga_id=carga.id, tipo="SERVICIO_TALLER",
        nombre="MORENO MOLANO JORGE", cedula=cedula, celular=celular, placa="AAA11A",
    )
    db.add(registro)
    await db.commit()
    return registro.id, cedula, celular[-4:]


def _datos(score: int, autoriza: bool = True) -> dict:
    return dict(satisfaccion_general=score, observaciones="x", autoriza_datos=autoriza, **{m: 4 for m in MATRIX})


async def _contar(db, modelo, *where) -> int:
    return (await db.execute(select(func.count()).select_from(modelo).where(*where))).scalar_one()


@pytest.mark.parametrize("score", [1, 2, 3])
async def test_detractor_response_is_saved_with_case_and_opening_entry(sesion, score):
    registro_id, cedula, ultimos4 = await _registro(sesion)
    resultado = await servicio.registrar_respuesta(
        sesion, cedula_raw=cedula, celular_ultimos4=ultimos4, registro_id=registro_id, datos=_datos(score),
    )
    assert resultado.clasificacion == "DETRACTOR"
    assert resultado.caso_numero is not None
    respuesta_id = (await sesion.execute(
        select(EncuestaRespuesta.id).where(EncuestaRespuesta.registro_id == registro_id)
    )).scalar_one()
    caso = (await sesion.execute(
        select(CasoDetractor).where(CasoDetractor.respuesta_id == respuesta_id)
    )).scalar_one()
    assert caso.numero == resultado.caso_numero
    assert resultado.caso_codigo == f"DET-{caso.created_at.year}-{caso.numero:06d}"
    assert await _contar(sesion, CasoDetractorAccion, CasoDetractorAccion.caso_id == caso.id,
                         CasoDetractorAccion.tipo == "APERTURA") == 1


async def test_satisfied_response_is_saved_without_case(sesion):
    registro_id, cedula, ultimos4 = await _registro(sesion)
    resultado = await servicio.registrar_respuesta(
        sesion, cedula_raw=cedula, celular_ultimos4=ultimos4, registro_id=registro_id, datos=_datos(5),
    )
    assert resultado.clasificacion == "SATISFECHO"
    assert await _contar(sesion, EncuestaRespuesta, EncuestaRespuesta.registro_id == registro_id) == 1


async def test_second_submit_for_the_same_record_is_already_answered(sesion):
    registro_id, cedula, ultimos4 = await _registro(sesion)
    kwargs = dict(cedula_raw=cedula, celular_ultimos4=ultimos4, registro_id=registro_id)
    await servicio.registrar_respuesta(sesion, **kwargs, datos=_datos(2))
    with pytest.raises(servicio.RespuestaYaRegistrada):
        await servicio.registrar_respuesta(sesion, **kwargs, datos=_datos(2))


async def test_detractor_case_full_lifecycle_in_the_panel(sesion):
    """The panel queries (list with search, detail, log, transitions) on real SQL."""
    from app.motored.services import caso_detractor as casos

    registro_id, cedula, ultimos4 = await _registro(sesion)
    resultado = await servicio.registrar_respuesta(
        sesion, cedula_raw=cedula, celular_ultimos4=ultimos4, registro_id=registro_id, datos=_datos(1, False),
    )
    admin_id = (await sesion.execute(select(Usuario.id).where(Usuario.email.like(f"%{cedula}%")))).scalar_one()

    pagina = await casos.listar(sesion, page=1, page_size=50, estado="ABIERTO", autoriza_datos=False, q=cedula)
    assert [item["numero"] for item in pagina["items"]] == [resultado.caso_numero]
    assert pagina["items"][0]["codigo"] == resultado.caso_codigo
    por_codigo = await casos.listar(sesion, page=1, page_size=50, q=resultado.caso_codigo.lower())
    assert [item["codigo"] for item in por_codigo["items"]] == [resultado.caso_codigo]
    caso_id = pagina["items"][0]["id"]

    detalle = await casos.detalle(sesion, caso_id)
    assert detalle["autoriza_datos"] is False
    assert [a["tipo"] for a in detalle["acciones"]] == ["APERTURA"]

    await casos.agregar_accion(sesion, caso_id, usuario_id=str(admin_id), tipo="LLAMADA", descripcion="Llamé al cliente")
    await casos.cambiar_estado(sesion, caso_id, usuario_id=str(admin_id), estado="EN_GESTION", resultado=None,
                               comentario="Tomo el caso")
    await casos.cambiar_estado(sesion, caso_id, usuario_id=str(admin_id), estado="CERRADO",
                               resultado="RECUPERADO", comentario="Cliente conforme")
    reabierto = await casos.cambiar_estado(sesion, caso_id, usuario_id=str(admin_id), estado="EN_GESTION",
                                           resultado=None, comentario="Volvió a llamar")
    assert reabierto["estado"] == "EN_GESTION" and reabierto["resultado"] is None
    assert [a["tipo"] for a in reabierto["acciones"]] == [
        "APERTURA", "LLAMADA", "CAMBIO_ESTADO", "CAMBIO_ESTADO", "CAMBIO_ESTADO",
    ]


async def _caso_detractor(sesion) -> tuple:
    """Submit a detractor response; returns (caso_id, admin_id)."""
    registro_id, cedula, ultimos4 = await _registro(sesion)
    resultado = await servicio.registrar_respuesta(
        sesion, cedula_raw=cedula, celular_ultimos4=ultimos4, registro_id=registro_id, datos=_datos(1, False),
    )
    admin_id = (await sesion.execute(select(Usuario.id).where(Usuario.email.like(f"%{cedula}%")))).scalar_one()
    caso_id = (await sesion.execute(
        select(CasoDetractor.id).where(CasoDetractor.numero == resultado.caso_numero)
    )).scalar_one()
    return caso_id, admin_id


async def test_first_manual_action_makes_the_author_the_responsable(sesion):
    from app.motored.services import caso_detractor as casos

    caso_id, admin_id = await _caso_detractor(sesion)
    assert (await casos.detalle(sesion, caso_id))["asignado_a"] is None

    await casos.agregar_accion(sesion, caso_id, usuario_id=str(admin_id), tipo="NOTA", descripcion="Primer registro")

    responsable = (await casos.detalle(sesion, caso_id))["asignado_a"]
    assert responsable["id"] == admin_id


class _CapturingOp:
    """Stands in for `alembic.op` so the migration's SQL can run on a session."""

    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(str(statement))


async def test_backfill_migration_assigns_the_first_user_entry_only_where_unassigned(sesion):
    """Runs the real migration statements (upgrade) against seeded legacy-shaped data."""
    import importlib.util
    from datetime import datetime
    from pathlib import Path

    from sqlalchemy import text

    caso_id, first_id = await _caso_detractor(sesion)
    second_id = uuid.uuid4()
    sesion.add(Usuario(
        id=second_id, nombre="Otro", role=MotoredRole.ADMIN, activo=True,
        email=f"otro{second_id.hex[:8]}@test.co", hashed_password="x",
    ))
    await sesion.flush()
    for usuario_id, hora in ((second_id, 12), (first_id, 10)):  # the earlier entry is the one that must win
        sesion.add(CasoDetractorAccion(
            id=uuid.uuid4(), caso_id=caso_id, usuario_id=usuario_id, tipo="NOTA",
            descripcion="Entrada antigua", created_at=datetime(2026, 9, 1, hora),
        ))
    await sesion.commit()
    assert (await sesion.get(CasoDetractor, caso_id)).asignado_a is None

    archivo = next((Path(__file__).resolve().parents[3] / "alembic_motored" / "versions").glob("a7c3e91d5b20_*.py"))
    spec = importlib.util.spec_from_file_location("backfill_migration", archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    captura = _CapturingOp()
    modulo.op = captura
    modulo.upgrade()
    for sentencia in captura.statements:
        await sesion.execute(text(sentencia))
    await sesion.commit()

    sesion.expire_all()
    assert (await sesion.get(CasoDetractor, caso_id)).asignado_a == first_id
