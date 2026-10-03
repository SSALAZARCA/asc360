"""
Motored `motored-referencia-identidad` contra un Postgres real (opt-in).

Corre solo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`).

- La migracion `f3a8d1c5b704` (unico por `codigo`): upgrade, downgrade y
  upgrade sobre una base descartable, la guarda que ABORTA si hay codigos
  repetidos (ignorando mayusculas y espacios) sin tocar nada, y el trim.
- Mover una referencia de proveedor conserva su id y su `venta_mensual`.
"""
import asyncio
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_mensual import VentaMensual
from app.motored.schemas.referencia import ReferenciaCreate
from app.motored.services import maestros

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

_RAIZ = Path(__file__).resolve().parents[3]
ANTERIOR, NUEVA = "e8c2a5f17b93", "f3a8d1c5b704"
PA, PB = uuid.uuid4(), uuid.uuid4()  # proveedores sembrados en las bases descartables


# --- Infraestructura de migracion (base descartable por test) ---------------


def _correr(corrutina):
    return asyncio.run(corrutina)


async def _admin(sentencia):
    motor = create_async_engine(URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conexion:
        await conexion.execute(text(sentencia))
    await motor.dispose()


async def _sql(url, sentencia, **params):
    motor = create_async_engine(url, poolclass=NullPool)
    try:
        async with motor.begin() as conexion:
            resultado = await conexion.execute(text(sentencia), params)
            return resultado.all() if resultado.returns_rows else []
    finally:
        await motor.dispose()


def _filas(url, sentencia, **params):
    return _correr(_sql(url, sentencia, **params))


def _alembic(accion, destino):
    config = Config()
    config.set_main_option("script_location", str(_RAIZ / "alembic_motored"))
    getattr(command, accion)(config, destino)


@pytest.fixture
def base(monkeypatch):
    nombre = f"mig_ref_{uuid.uuid4().hex[:10]}"
    _correr(_admin(f'CREATE DATABASE "{nombre}"'))
    url = make_url(URL).set(database=nombre).render_as_string(hide_password=False)
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", url)
    yield url
    _correr(_admin(f'DROP DATABASE "{nombre}" WITH (FORCE)'))


def _constraints(url):
    filas = _filas(url, "SELECT conname FROM pg_constraint WHERE conrelid = 'referencia'::regclass "
                   "AND contype = 'u'")
    return {f[0] for f in filas}


def _version(url):
    return _filas(url, "SELECT version_num FROM alembic_version_motored")[0][0]


def _sembrar_proveedores(url):
    _filas(url, "INSERT INTO proveedor(id, codigo, nombre, es_principal, activa) VALUES "
           "(:a, 'HMCL', 'HMCL', true, true), (:b, 'OTRO', 'Otro', false, true)",
           a=PA, b=PB)


def _referencia(url, codigo, proveedor):
    _filas(url, "INSERT INTO referencia(id, codigo, proveedor_id, unidad_empaque, "
           "unidad_empaque_advertencia, activa, homologados) VALUES "
           "(:i, :c, :p, 1, false, true, '{}')", i=uuid.uuid4(), c=codigo, p=proveedor)


# --- Migracion ---------------------------------------------------------------


def test_upgrade_downgrade_upgrade_cambia_el_unico_y_vuelve(base):
    _alembic("upgrade", ANTERIOR)
    assert _constraints(base) == {"uq_referencia_codigo_proveedor"}

    _alembic("upgrade", NUEVA)
    assert _constraints(base) == {"uq_referencia_codigo"}

    _alembic("downgrade", "-1")
    assert _constraints(base) == {"uq_referencia_codigo_proveedor"}
    assert _version(base) == ANTERIOR

    _alembic("upgrade", NUEVA)
    assert _constraints(base) == {"uq_referencia_codigo"}


def test_el_upgrade_recorta_los_codigos_guardados_con_espacios(base):
    _alembic("upgrade", ANTERIOR)
    _sembrar_proveedores(base)
    _referencia(base, "  AB-1 ", PA)
    _referencia(base, "CD-2", PA)

    _alembic("upgrade", NUEVA)

    codigos = {f[0] for f in _filas(base, "SELECT codigo FROM referencia")}
    assert codigos == {"AB-1", "CD-2"}


def test_la_guarda_aborta_con_codigos_duplicados_y_no_toca_nada(base):
    _alembic("upgrade", ANTERIOR)
    _sembrar_proveedores(base)
    _referencia(base, "ABC-1", PA)
    _referencia(base, " abc-1", PB)  # mismo codigo ignorando mayusculas y espacios (otro proveedor)
    _referencia(base, "SOLA", PA)

    with pytest.raises(Exception) as exc:
        _alembic("upgrade", NUEVA)

    assert "ABC-1" in str(exc.value)
    assert _version(base) == ANTERIOR
    assert _constraints(base) == {"uq_referencia_codigo_proveedor"}
    assert {f[0] for f in _filas(base, "SELECT codigo FROM referencia")} == {"ABC-1", " abc-1", "SOLA"}


def test_con_el_unico_nuevo_el_mismo_codigo_en_otro_proveedor_se_rechaza(base):
    _alembic("upgrade", NUEVA)
    _sembrar_proveedores(base)
    _referencia(base, "R-1", PA)

    with pytest.raises(IntegrityError):
        _referencia(base, "R-1", PB)


# --- Mover conserva id y ventas (base ya migrada a head) ---------------------


@pytest.fixture
async def sesion(monkeypatch):
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        monkeypatch.setattr(db, "commit", db.flush)
        yield db
        await db.rollback()
    await motor.dispose()


def _sfx():
    return uuid.uuid4().hex[:8].upper()


async def _proveedores(db, n=2):
    provs = [Proveedor(id=uuid.uuid4(), codigo=f"P{i}-{_sfx()}", nombre=f"P{i}", es_principal=False)
             for i in range(n)]
    db.add_all(provs)
    await db.flush()
    return provs


async def test_mover_una_referencia_conserva_su_id_y_su_venta_mensual(sesion):
    sfx = _sfx()
    hmcl, otro = await _proveedores(sesion)
    sucursal = Sucursal(id=uuid.uuid4(), nombre=f"S {sfx}", sic=f"SIC-{sfx}")
    carga = CargaArchivo(id=uuid.uuid4(), tipo="VENTAS", origen="EXCEL", estado="APLICADO",
                         nombre_archivo="v.xlsx", hash_sha256="h" * 64, ruta_objeto="r", bytes=1)
    sesion.add_all([sucursal, carga])
    await sesion.flush()
    codigo = f"MOV-{sfx}"
    original, _, creada = await maestros.upsert_referencia(
        sesion, ReferenciaCreate(codigo=codigo, proveedor_id=hmcl.id, precio_normal=Decimal("10")))
    sesion.add(VentaMensual(sucursal_id=sucursal.id, referencia_id=original.id, anio=2026, mes=9,
                            origen="MOSTRADOR", unidades=Decimal("7"), carga_id=carga.id))
    await sesion.flush()
    id_original = original.id

    movida, _, creada_otra_vez = await maestros.upsert_referencia(
        sesion, ReferenciaCreate(codigo=f" {codigo} ", proveedor_id=otro.id))
    await sesion.flush()

    assert creada is True and creada_otra_vez is False
    assert movida.id == id_original and movida.proveedor_id == otro.id
    filas = (await sesion.execute(select(Referencia).where(Referencia.codigo == codigo))).scalars().all()
    assert len(filas) == 1
    ventas = (await sesion.execute(
        select(VentaMensual).where(VentaMensual.referencia_id == id_original))).scalars().all()
    assert [v.unidades for v in ventas] == [Decimal("7.00")]


async def test_mover_quita_con_aviso_el_vinculo_de_quien_la_tenia_de_sustituta(sesion):
    sfx = _sfx()
    hmcl, otro = await _proveedores(sesion)
    destino, _, _ = await maestros.upsert_referencia(
        sesion, ReferenciaCreate(codigo=f"NUEVA-{sfx}", proveedor_id=hmcl.id))
    vieja, _, _ = await maestros.upsert_referencia(
        sesion, ReferenciaCreate(codigo=f"VIEJA-{sfx}", proveedor_id=hmcl.id, sustituida_por=destino.id))
    await sesion.flush()
    avisos = []

    await maestros.upsert_referencia(
        sesion, ReferenciaCreate(codigo=f"NUEVA-{sfx}", proveedor_id=otro.id), avisos=avisos)
    await sesion.flush()
    await sesion.refresh(vieja)

    assert vieja.sustituida_por is None
    assert len(avisos) == 1 and f"VIEJA-{sfx}" in avisos[0]
