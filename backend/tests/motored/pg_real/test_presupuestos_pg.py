"""
Motored budgets (odd/motored-presupuestos-gerencia, T2) against a real
Postgres (opt-in, `MOTORED_TEST_PG_URL` on a database migrated to head).

Covers what doubles cannot: the real constraints (CHECK day = 1, UNIQUE on
mes+version and version+cedula, positive amount, cascade), the month-replace
versioning of an upload, manual edits as new versions, the reads (latest
version, store sums, history) and the per-month version race.

Every test but the race works in a transaction that is rolled back (the code
under test only flushes; the API commit is degraded to a flush).
"""
import asyncio
import datetime
import io
import os
import uuid

import httpx
import openpyxl
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.services import presupuestos
from app.motored.services.auth import MotoredUser
from app.motored.services.presupuestos import (
    PresupuestoConflicto,
    PresupuestoInvalido,
    PresupuestoNoEncontrado,
)

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

D = datetime.date
MARZO, ABRIL = D(2031, 3, 1), D(2031, 4, 1)
RUTA = "/api/motored/presupuestos"


class Escenario:
    def __init__(self, sufijo):
        self.sufijo = sufijo
        base = int(sufijo, 16) % 10**7 * 10
        self.cedulas = [str(1_000_000_000 + base + i) for i in range(4)]
        self.usuario = Usuario(
            id=uuid.uuid4(), nombre=f"Gerente {sufijo}", role=MotoredRole.GERENCIA,
            email=f"g-{sufijo}@x.co", hashed_password="x")
        self.cali = Sucursal(id=uuid.uuid4(), nombre=f"Cali {sufijo}", sic=f"C-{sufijo}")
        self.bogota = Sucursal(id=uuid.uuid4(), nombre=f"Bogotá {sufijo}", sic=f"B-{sufijo}")
        self.cerrada = Sucursal(id=uuid.uuid4(), nombre=f"Cerrada {sufijo}", sic=f"X-{sufijo}", activa=False)
        self.alias = SucursalAlias(
            id=uuid.uuid4(), texto_normalizado=f"SEDE VIEJA {sufijo.upper()}", sucursal_id=self.cali.id)
        c0, c1, c2, c3 = self.cedulas
        self.vendedores = [
            Vendedor(id=uuid.uuid4(), nombre=f"Ana Vieja {sufijo}", nombre_norm=f"ANA VIEJA {sufijo}",
                     cargo="ASESOR", cedula=c0, activo=False),
            Vendedor(id=uuid.uuid4(), nombre=f"Ana Activa {sufijo}", nombre_norm=f"ANA ACTIVA {sufijo}",
                     cargo="ASESOR", cedula=c0, activo=True),
            Vendedor(id=uuid.uuid4(), nombre=f"Beto {sufijo}", nombre_norm=f"BETO {sufijo}",
                     cargo="ASESOR", cedula=c1, activo=True),
            Vendedor(id=uuid.uuid4(), nombre=f"Carla {sufijo}", nombre_norm=f"CARLA {sufijo}",
                     cargo="ASESOR", cedula=c2, activo=True),
            Vendedor(id=uuid.uuid4(), nombre=f"Dario Inactivo {sufijo}", nombre_norm=f"DARIO {sufijo}",
                     cargo="ASESOR", cedula=c3, activo=False),
        ]

    async def sembrar(self, db):
        db.add(self.usuario)
        db.add_all([self.cali, self.bogota, self.cerrada])
        await db.flush()
        db.add(self.alias)
        db.add_all(self.vendedores)
        await db.flush()

    def fila(self, indice, mes="2031-03", tienda=None, presupuesto=1_000_000):
        return {
            "cedula": self.cedulas[indice], "mes": mes,
            "tienda": tienda or self.cali.nombre, "presupuesto": presupuesto,
        }


@pytest.fixture
async def esc(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        escenario = Escenario(uuid.uuid4().hex[:8])
        await escenario.sembrar(db)
        escenario.db = db
        yield escenario
        await db.rollback()
    await motor.dispose()


async def _aplicar(esc, filas, nombre="p.xlsx"):
    return await presupuestos.aplicar_archivo(esc.db, filas, nombre, esc.usuario.id)


async def _lineas(db, mes, version):
    consulta = (
        select(PresupuestoLinea.cedula, PresupuestoLinea.monto)
        .join(PresupuestoVersion, PresupuestoVersion.id == PresupuestoLinea.version_id)
        .where(PresupuestoVersion.mes == mes, PresupuestoVersion.version == version))
    return dict((await db.execute(consulta)).all())


# --- constraints ------------------------------------------------------------


async def _rechaza(db, *objetos):
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add_all(list(objetos))
            await db.flush()


def _version(mes=MARZO, version=1, origen="EXCEL", **extra):
    return PresupuestoVersion(id=uuid.uuid4(), mes=mes, version=version, origen=origen, **extra)


async def test_a_month_must_be_the_first_day(esc):
    await _rechaza(esc.db, _version(mes=D(2031, 3, 15)))


async def test_origin_and_version_number_are_constrained(esc):
    await _rechaza(esc.db, _version(origen="OTRO"))
    await _rechaza(esc.db, _version(version=0))


async def test_the_same_month_and_version_cannot_repeat(esc):
    esc.db.add(_version())
    await esc.db.flush()

    await _rechaza(esc.db, _version())


async def test_line_constraints_unique_cedula_per_version_and_positive_amount(esc):
    cabecera = _version()
    esc.db.add(cabecera)
    await esc.db.flush()

    def linea(cedula, monto):
        return PresupuestoLinea(
            id=uuid.uuid4(), version_id=cabecera.id, cedula=cedula, sucursal_id=esc.cali.id, monto=monto)

    esc.db.add(linea("1", 10))
    await esc.db.flush()

    await _rechaza(esc.db, linea("1", 20))
    await _rechaza(esc.db, linea("2", 0))


async def test_deleting_a_version_cascades_to_its_lines(esc):
    await _aplicar(esc, [esc.fila(0)])
    await esc.db.execute(delete(PresupuestoVersion).where(PresupuestoVersion.mes == MARZO))

    assert await _lineas(esc.db, MARZO, 1) == {}


# --- apply: month replace + versioning --------------------------------------


async def test_two_uploads_of_a_month_create_versions_1_and_2_and_replace_the_month(esc):
    primera = await _aplicar(esc, [esc.fila(0, presupuesto=100), esc.fila(1, presupuesto=200)])
    segunda = await _aplicar(esc, [esc.fila(0, presupuesto=300), esc.fila(2, presupuesto=400)])

    assert [m["version"] for m in primera["meses"]] == [1]
    assert [m["version"] for m in segunda["meses"]] == [2]
    assert await _lineas(esc.db, MARZO, 1) == {esc.cedulas[0]: 100, esc.cedulas[1]: 200}
    assert await _lineas(esc.db, MARZO, 2) == {esc.cedulas[0]: 300, esc.cedulas[2]: 400}
    por_asesor = await presupuestos.presupuesto_por_asesor(esc.db, MARZO, MARZO)
    assert {c for (_, c) in por_asesor} >= {esc.cedulas[0], esc.cedulas[2]}
    assert (MARZO, esc.cedulas[1]) not in por_asesor  # omitted asesor: no budget that month


async def test_a_multi_month_file_versions_each_month_and_leaves_other_months_untouched(esc):
    await _aplicar(esc, [esc.fila(0, mes="2031-04", presupuesto=50)])

    resultado = await _aplicar(esc, [
        esc.fila(0, mes="2031-03", presupuesto=100),
        esc.fila(1, mes="03/2031", presupuesto=200),
        esc.fila(0, mes="2031-05", presupuesto=300),
    ])

    assert [(m["mes"], m["version"], m["asesores"], m["total"]) for m in resultado["meses"]] == [
        ("2031-03", 1, 2, 300), ("2031-05", 1, 1, 300)]
    assert await _lineas(esc.db, ABRIL, 1) == {esc.cedulas[0]: 50}
    assert (await _lineas(esc.db, ABRIL, 2)) == {}


async def test_a_file_with_errors_writes_nothing(esc):
    antes = len((await esc.db.execute(select(PresupuestoVersion))).all())

    with pytest.raises(PresupuestoInvalido) as exc:
        await _aplicar(esc, [esc.fila(0), {**esc.fila(1), "cedula": "999"}])

    assert [e["fila"] for e in exc.value.errores] == [2]
    assert len((await esc.db.execute(select(PresupuestoVersion))).all()) == antes


async def test_dry_run_reports_the_version_it_replaces_without_writing(esc):
    filas = [esc.fila(0, presupuesto=100), esc.fila(1, tienda=esc.bogota.nombre, presupuesto=200),
             esc.fila(3, tienda=f"sede vieja {esc.sufijo}", presupuesto=50)]
    antes = await presupuestos.validar_archivo(esc.db, filas)
    await _aplicar(esc, filas)

    despues = await presupuestos.validar_archivo(esc.db, filas)

    assert antes["meses"][0]["reemplaza_version"] is None
    assert despues["meses"][0]["reemplaza_version"] == 1
    assert [t["total"] for t in despues["meses"][0]["por_tienda"]] == [200, 150]  # Bogotá, Cali
    assert [w["fila"] for w in despues["warnings"]] == [3]  # inactive-only vendedor
    assert len((await esc.db.execute(select(PresupuestoVersion).where(PresupuestoVersion.mes == MARZO))).all()) == 1


async def test_the_apply_audit_trail_is_the_version_header(esc):
    await _aplicar(esc, [esc.fila(0)], nombre="marzo.xlsx")

    [cabecera] = (await esc.db.execute(
        select(PresupuestoVersion).where(PresupuestoVersion.mes == MARZO))).scalars().all()
    assert (cabecera.origen, cabecera.archivo_nombre, cabecera.created_by) == (
        "EXCEL", "marzo.xlsx", esc.usuario.id)


# --- manual edits -----------------------------------------------------------


async def test_a_manual_edit_clones_the_latest_version_with_the_change(esc):
    await _aplicar(esc, [esc.fila(0, presupuesto=100), esc.fila(1, presupuesto=200)])

    editado = await presupuestos.editar_asesor(
        esc.db, MARZO, esc.cedulas[0], esc.bogota.id, 999, "ajuste", esc.usuario.id)
    agregado = await presupuestos.editar_asesor(
        esc.db, MARZO, esc.cedulas[2], esc.cali.id, 5, None, esc.usuario.id)

    assert (editado["version"], agregado["version"]) == (2, 3)
    assert await _lineas(esc.db, MARZO, 1) == {esc.cedulas[0]: 100, esc.cedulas[1]: 200}
    assert await _lineas(esc.db, MARZO, 3) == {esc.cedulas[0]: 999, esc.cedulas[1]: 200, esc.cedulas[2]: 5}
    historial = await presupuestos.historial_mes(esc.db, MARZO)
    assert [(h["version"], h["origen"], h["nota"]) for h in historial] == [
        (3, "MANUAL", None), (2, "MANUAL", "ajuste"), (1, "EXCEL", None)]


async def test_a_manual_edit_validates_cedula_store_and_amount(esc):
    with pytest.raises(PresupuestoInvalido):
        await presupuestos.editar_asesor(esc.db, MARZO, "999", esc.cali.id, 10, None, esc.usuario.id)
    with pytest.raises(PresupuestoInvalido):
        await presupuestos.editar_asesor(esc.db, MARZO, esc.cedulas[0], esc.cerrada.id, 10, None, esc.usuario.id)
    with pytest.raises(PresupuestoInvalido):
        await presupuestos.editar_asesor(esc.db, MARZO, esc.cedulas[0], uuid.uuid4(), 10, None, esc.usuario.id)
    with pytest.raises(PresupuestoInvalido):
        await presupuestos.editar_asesor(esc.db, MARZO, esc.cedulas[0], esc.cali.id, 0, None, esc.usuario.id)


async def test_a_manual_edit_of_a_month_without_budget_starts_version_1(esc):
    resultado = await presupuestos.editar_asesor(
        esc.db, ABRIL, esc.cedulas[0], esc.cali.id, 70, None, esc.usuario.id)

    assert resultado["version"] == 1
    assert await _lineas(esc.db, ABRIL, 1) == {esc.cedulas[0]: 70}


async def test_removing_an_asesor_creates_a_version_without_him_and_the_last_one_is_allowed(esc):
    await _aplicar(esc, [esc.fila(0), esc.fila(1)])

    await presupuestos.quitar_asesor(esc.db, MARZO, esc.cedulas[0], "se fue", esc.usuario.id)
    vacia = await presupuestos.quitar_asesor(esc.db, MARZO, esc.cedulas[1], None, esc.usuario.id)

    assert vacia["version"] == 3
    assert await _lineas(esc.db, MARZO, 2) == {esc.cedulas[1]: 1_000_000}
    assert (await presupuestos.detalle_mes(esc.db, MARZO))["lineas"] == []


async def test_removing_an_asesor_without_budget_is_not_found(esc):
    await _aplicar(esc, [esc.fila(0)])

    with pytest.raises(PresupuestoNoEncontrado):
        await presupuestos.quitar_asesor(esc.db, MARZO, esc.cedulas[1], None, esc.usuario.id)
    with pytest.raises(PresupuestoNoEncontrado):
        await presupuestos.quitar_asesor(esc.db, ABRIL, esc.cedulas[0], None, esc.usuario.id)


# --- reads ------------------------------------------------------------------


async def test_month_detail_groups_by_store_and_prefers_the_active_vendedor_name(esc):
    await _aplicar(esc, [
        esc.fila(0, presupuesto=100), esc.fila(1, presupuesto=200),
        esc.fila(2, tienda=esc.bogota.nombre, presupuesto=400)])

    detalle = await presupuestos.detalle_mes(esc.db, MARZO)

    assert (detalle["mes"], detalle["version"], detalle["total"], detalle["asesores"]) == ("2031-03", 1, 700, 3)
    nombres = {linea["cedula"]: linea["asesor"] for linea in detalle["lineas"]}
    assert nombres[esc.cedulas[0]] == f"Ana Activa {esc.sufijo}"
    assert {t["tienda"]: (t["asesores"], t["total"]) for t in detalle["por_tienda"]} == {
        esc.cali.nombre: (2, 300), esc.bogota.nombre: (1, 400)}


async def test_the_name_falls_back_to_an_inactive_vendedor(esc):
    await _aplicar(esc, [esc.fila(3)])

    [linea] = (await presupuestos.detalle_mes(esc.db, MARZO))["lineas"]

    assert linea["asesor"] == f"Dario Inactivo {esc.sufijo}"


async def test_month_detail_of_a_month_without_budget_is_not_found(esc):
    with pytest.raises(PresupuestoNoEncontrado):
        await presupuestos.detalle_mes(esc.db, ABRIL)


async def test_month_list_shows_the_latest_version_of_each_month(esc):
    await _aplicar(esc, [esc.fila(0, presupuesto=100), esc.fila(0, mes="2031-04", presupuesto=7)])
    await _aplicar(esc, [esc.fila(0, presupuesto=100), esc.fila(1, presupuesto=50)])

    lista = [m for m in await presupuestos.listar_meses(esc.db) if m["mes"] in ("2031-03", "2031-04")]

    assert [(m["mes"], m["version"], m["asesores"], m["total"]) for m in lista] == [
        ("2031-04", 1, 1, 7), ("2031-03", 2, 2, 150)]


async def test_history_lists_versions_newest_first_with_author_lines_and_total(esc):
    await _aplicar(esc, [esc.fila(0, presupuesto=100)], nombre="a.xlsx")
    await _aplicar(esc, [esc.fila(0, presupuesto=100), esc.fila(1, presupuesto=50)], nombre="b.xlsx")

    historial = await presupuestos.historial_mes(esc.db, MARZO)

    assert [(h["version"], h["archivo_nombre"], h["lineas"], h["total"], h["created_by_nombre"])
            for h in historial] == [
        (2, "b.xlsx", 2, 150, esc.usuario.nombre), (1, "a.xlsx", 1, 100, esc.usuario.nombre)]


async def test_a_specific_version_can_be_read(esc):
    await _aplicar(esc, [esc.fila(0, presupuesto=100)])
    await _aplicar(esc, [esc.fila(1, presupuesto=50)])
    [primera] = [h for h in await presupuestos.historial_mes(esc.db, MARZO) if h["version"] == 1]

    detalle = await presupuestos.detalle_version(esc.db, uuid.UUID(primera["id"]))

    assert (detalle["version"], detalle["total"]) == (1, 100)
    with pytest.raises(PresupuestoNoEncontrado):
        await presupuestos.detalle_version(esc.db, uuid.uuid4())


async def test_kpi_reads_use_the_latest_version_per_month_and_sum_per_store(esc):
    await _aplicar(esc, [esc.fila(0, presupuesto=1), esc.fila(0, mes="2031-04", presupuesto=9)])
    await _aplicar(esc, [
        esc.fila(0, presupuesto=100), esc.fila(1, tienda=esc.bogota.nombre, presupuesto=200),
        esc.fila(2, presupuesto=300)])

    por_asesor = await presupuestos.presupuesto_por_asesor(esc.db, MARZO, ABRIL)
    por_sucursal = await presupuestos.presupuesto_por_sucursal(esc.db, MARZO, ABRIL)

    assert por_asesor[(MARZO, esc.cedulas[0])].monto == 100
    assert por_asesor[(MARZO, esc.cedulas[1])].sucursal_id == esc.bogota.id
    assert por_asesor[(ABRIL, esc.cedulas[0])].monto == 9
    assert por_sucursal[(MARZO, esc.cali.id)] == 400
    assert por_sucursal[(MARZO, esc.bogota.id)] == 200
    assert por_sucursal[(ABRIL, esc.cali.id)] == 9
    assert await presupuestos.presupuesto_por_sucursal(esc.db, D(2040, 1, 1), D(2040, 12, 1)) == {}


# --- version race -----------------------------------------------------------


async def test_two_concurrent_uploads_of_the_same_month_get_distinct_versions():
    motor = create_async_engine(URL)
    maker = async_sessionmaker(motor, expire_on_commit=False)
    esc = Escenario(uuid.uuid4().hex[:8])
    mes = D(2032, 7, 1)
    async with maker() as db:
        await esc.sembrar(db)
        await db.commit()
    filas = [esc.fila(0, mes="2032-07", presupuesto=10)]

    async def subir():
        async with maker() as db:
            resultado = await presupuestos.aplicar_archivo(db, filas, "x.xlsx", esc.usuario.id)
            await db.commit()
            return resultado["meses"][0]["version"]

    try:
        versiones = await asyncio.gather(*[subir() for _ in range(4)])
        assert sorted(versiones) == [1, 2, 3, 4]
    finally:
        async with maker() as db:
            await db.execute(delete(PresupuestoVersion).where(PresupuestoVersion.mes == mes))
            await db.execute(delete(Vendedor).where(Vendedor.id.in_([v.id for v in esc.vendedores])))
            await db.execute(delete(SucursalAlias).where(SucursalAlias.id == esc.alias.id))
            await db.execute(delete(Sucursal).where(Sucursal.id.in_([esc.cali.id, esc.bogota.id, esc.cerrada.id])))
            await db.execute(delete(Usuario).where(Usuario.id == esc.usuario.id))
            await db.commit()
        await motor.dispose()


async def test_an_unexpected_unique_violation_surfaces_as_a_conflict(esc, monkeypatch):
    async def siempre_1(db, mes):
        return 1
    await _aplicar(esc, [esc.fila(0)])
    monkeypatch.setattr(presupuestos, "_siguiente_version", siempre_1)

    with pytest.raises(PresupuestoConflicto):
        await _aplicar(esc, [esc.fila(0)])


# --- API over the real database --------------------------------------------


@pytest.fixture
async def http(esc, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "presupuestos-pg")

    async def sesion():
        yield esc.db

    async def usuario():
        return MotoredUser(user_id=str(esc.usuario.id), role="GERENCIA")

    app.dependency_overrides[get_motored_db] = sesion
    app.dependency_overrides[get_current_motored_user] = usuario
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://motored") as cliente:
        yield cliente
    app.dependency_overrides.clear()


def _xlsx(filas):
    libro = openpyxl.Workbook()
    libro.active.append(["Cédula", "Mes", "Tienda", "Presupuesto"])
    for fila in filas:
        libro.active.append([fila["cedula"], fila["mes"], fila["tienda"], fila["presupuesto"]])
    buffer = io.BytesIO()
    libro.save(buffer)
    return {"file": ("marzo.xlsx", buffer.getvalue(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def test_api_validar_then_aplicar_then_read_back(esc, http):
    def archivo():
        return _xlsx([esc.fila(0, presupuesto=100), esc.fila(1, tienda=esc.bogota.nombre, presupuesto=200)])

    validar = await http.post(f"{RUTA}/validar", files=archivo())
    aplicar = await http.post(f"{RUTA}/aplicar", files=archivo())
    meses = await http.get(f"{RUTA}/meses")
    detalle = await http.get(f"{RUTA}/meses/2031-03")
    versiones = await http.get(f"{RUTA}/meses/2031-03/versiones")
    version = await http.get(f"{RUTA}/versiones/{versiones.json()[0]['id']}")

    assert validar.status_code == 200 and validar.json()["valido"] is True
    assert validar.json()["meses"][0]["total"] == 300
    assert aplicar.status_code == 200 and aplicar.json()["meses"][0]["version"] == 1
    assert [m["mes"] for m in meses.json()][:1] == ["2031-03"]
    assert detalle.json()["total"] == 300 and len(detalle.json()["por_tienda"]) == 2
    assert [v["version"] for v in versiones.json()] == [1]
    assert version.json()["total"] == 300


async def test_api_aplicar_with_errors_is_422_and_writes_nothing(esc, http):
    respuesta = await http.post(f"{RUTA}/aplicar", files=_xlsx([{**esc.fila(0), "cedula": "999"}]))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["errores"][0]["columna"] == "Cédula"
    assert (await http.get(f"{RUTA}/meses/2031-03")).status_code == 404


async def test_api_manual_edit_and_removal(esc, http):
    await http.post(f"{RUTA}/aplicar", files=_xlsx([esc.fila(0, presupuesto=100)]))
    cedula = esc.cedulas[0]

    editar = await http.put(
        f"{RUTA}/meses/2031-03/asesores/{cedula}",
        json={"sucursal_id": str(esc.bogota.id), "monto": 250, "nota": "ajuste"})
    quitar = await http.delete(f"{RUTA}/meses/2031-03/asesores/{cedula}", params={"nota": "baja"})
    notas = [v["nota"] for v in (await http.get(f"{RUTA}/meses/2031-03/versiones")).json()]
    # Last: a rejected request rolls the (shared, rolled-back-at-the-end) session back.
    otra_vez = await http.delete(f"{RUTA}/meses/2031-03/asesores/{cedula}")

    assert editar.status_code == 200 and editar.json() == {"mes": "2031-03", "version": 2}
    assert quitar.status_code == 200 and quitar.json()["version"] == 3
    assert notas == ["baja", "ajuste", None]
    assert otra_vez.status_code == 404


async def test_api_manual_edit_with_a_bad_amount_is_422(esc, http):
    respuesta = await http.put(
        f"{RUTA}/meses/2031-03/asesores/{esc.cedulas[0]}",
        json={"sucursal_id": str(esc.cali.id), "monto": 0})

    assert respuesta.status_code == 422


async def test_tiendas_lists_only_active_sucursales_ordered_by_name(esc):
    tiendas = {t["id"]: t["nombre"] for t in await presupuestos.listar_tiendas(esc.db)}

    assert tiendas[str(esc.cali.id)] == esc.cali.nombre and tiendas[str(esc.bogota.id)] == esc.bogota.nombre
    assert str(esc.cerrada.id) not in tiendas
    assert list(tiendas.values()) == sorted(tiendas.values())


async def test_the_tienda_column_accepts_the_codigo_co_and_the_summary_shows_the_name(esc):
    co = "Y" + str(int(esc.sufijo, 16) % 100).zfill(2)
    esc.cali.codigo_co = co
    await esc.db.flush()

    resumen = await presupuestos.validar_archivo(
        esc.db, [esc.fila(0, tienda=co.lower()), esc.fila(1, tienda=f" {co} ")])

    assert resumen["errores"] == []
    [mes] = resumen["meses"]
    assert [t["tienda"] for t in mes["por_tienda"]] == [esc.cali.nombre]

    await _aplicar(esc, [esc.fila(0, tienda=co)])
    assert await _lineas(esc.db, MARZO, 1) == {esc.cedulas[0]: 1_000_000}


async def test_an_inactive_store_is_still_rejected_when_named_by_its_codigo_co(esc):
    esc.cerrada.codigo_co = "Y" + str(int(esc.sufijo, 16) % 100).zfill(2)
    await esc.db.flush()

    resumen = await presupuestos.validar_archivo(esc.db, [esc.fila(0, tienda=esc.cerrada.codigo_co)])

    assert any("inactiva" in e["mensaje"] for e in resumen["errores"])
