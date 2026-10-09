"""
Inventory counts, stage 1 (odd/motored-conteos-inventario, WU2 + WU3):
the models' metadata and the two Alembic revisions, checked STATICALLY
(no database). The real upgrade/downgrade and every CHECK and unique run
against Postgres in `pg_real/test_conteo_modelos_pg.py`.

Owner overrides covered here: the count is per STORE (snapshot unique per
referencia with an informative per-bodega JSON, locations without bodega,
one adjustment bodega per result line) and `conteo.lider_id`.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.motored.database import MotoredBase
import app.motored.models  # noqa: F401  (registers the models)

_RAIZ = Path(__file__).resolve().parents[2]
_VERSIONES = _RAIZ / "alembic_motored" / "versions"
BASE_REV, LECTURAS_REV = "c3e7a1f50d24", "d58b2c9e4a17"
TABLAS_BASE = ("conteo", "conteo_snapshot_linea", "ubicacion_inventario")
TABLAS_LECTURAS = (
    "conteo_sesion", "conteo_integrante", "conteo_reconteo",
    "conteo_lectura", "conteo_acceso_intento", "conteo_resultado",
)


def _tabla(nombre):
    return MotoredBase.metadata.tables[nombre]


def _nombres(tabla, tipo):
    return {
        c.name for c in (*tabla.constraints, *tabla.indexes)
        if isinstance(c, tipo)}


def _fk(tabla, columna):
    (fk,) = _tabla(tabla).c[columna].foreign_keys
    return fk.column.table.name, fk.ondelete


def _cargar(sufijo):
    (archivo,) = _VERSIONES.glob(f"*_{sufijo}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{sufijo}", archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _ops(modulo, direccion):
    with patch.object(modulo, "op") as op_mock:
        getattr(modulo, direccion)()
    return op_mock


# --- models: tables and columns ---------------------------------------------


def test_every_stage_one_table_is_registered():
    for nombre in (*TABLAS_BASE, *TABLAS_LECTURAS):
        assert nombre in MotoredBase.metadata.tables, nombre


def test_stage_three_tables_are_not_created():
    for nombre in ("conteo_abc", "conteo_item", "miniapp_cedula_intento"):
        assert nombre not in MotoredBase.metadata.tables


def test_conteo_has_the_leader_and_the_frozen_thresholds():
    columnas = _tabla("conteo").c

    assert _fk("conteo", "lider_id") == ("usuario", "RESTRICT")
    assert columnas.lider_id.nullable
    assert columnas.umbral_reconteo_pesos.type.scale == 2
    assert columnas.umbral_critico_pesos.type.scale == 2
    assert not columnas.tipo.nullable


def test_conteo_constraints_follow_the_design():
    tabla = _tabla("conteo")

    assert {
        "ck_conteo_tipo", "ck_conteo_estado", "ck_conteo_origen",
        "ck_conteo_lider_si_total", "ck_conteo_snapshot_si_iniciado",
        "ck_conteo_umbrales_si_iniciado", "ck_conteo_slug_solo_total",
    } <= _nombres(tabla, CheckConstraint)
    assert {
        "uq_conteo_total_abierto", "uq_conteo_selectivo_semana",
        "ix_conteo_estado_fecha", "ix_conteo_sucursal_cerrado",
        "ix_conteo_lider",
    } <= _nombres(tabla, Index)
    assert _fk("conteo", "sucursal_id") == ("sucursal", "RESTRICT")
    assert _fk("conteo", "snapshot_carga_id") == (
        "carga_archivo", "SET NULL")


def test_snapshot_line_is_per_store_and_referencia():
    tabla = _tabla("conteo_snapshot_linea")
    (unico,) = [
        c for c in tabla.constraints if isinstance(c, UniqueConstraint)]

    assert [c.name for c in unico.columns] == ["conteo_id", "referencia_id"]
    assert "bodega" not in tabla.c
    assert not tabla.c.existencia_por_bodega.nullable
    assert "costo_unitario" in tabla.c
    assert _fk("conteo_snapshot_linea", "conteo_id") == (
        "conteo", "CASCADE")


def test_location_belongs_to_a_store_without_bodega():
    tabla = _tabla("ubicacion_inventario")

    assert "bodega" not in tabla.c
    assert _fk("ubicacion_inventario", "sucursal_id") == (
        "sucursal", "RESTRICT")
    assert "uq_ubicacion_inventario_codigo" in _nombres(
        tabla, UniqueConstraint)


def test_reading_has_a_client_id_and_an_identity_seq():
    tabla = _tabla("conteo_lectura")

    assert tabla.c.id.primary_key
    assert tabla.c.seq.identity is not None
    assert tabla.c.seq.identity.always
    assert {
        "ix_conteo_lectura_agregado", "ix_conteo_lectura_conteo_seq",
        "ix_conteo_lectura_sesion_seq", "ix_conteo_lectura_conteo_ubicacion",
    } <= _nombres(tabla, Index)
    assert _fk("conteo_lectura", "reconteo_id") == (
        "conteo_reconteo", "CASCADE")


def test_member_stores_the_cedula():
    tabla = _tabla("conteo_integrante")

    assert not tabla.c.cedula.nullable
    assert tabla.c.cedula.type.length == 20
    assert _fk("conteo_integrante", "sesion_id") == (
        "conteo_sesion", "CASCADE")


def test_reconteo_has_its_partial_unique_and_checks():
    tabla = _tabla("conteo_reconteo")

    assert "uq_conteo_reconteo_codigo_activo" in _nombres(tabla, Index)
    assert {
        "ck_conteo_reconteo_sesion_si_asignado",
        "ck_conteo_reconteo_motivo_si_autorizada",
    } <= _nombres(tabla, CheckConstraint)


def test_access_attempt_key_is_conteo_and_client():
    tabla = _tabla("conteo_acceso_intento")

    assert [c.name for c in tabla.primary_key] == ["conteo_id", "cliente"]


def test_result_has_one_adjustment_bodega_per_line():
    tabla = _tabla("conteo_resultado")

    assert _fk("conteo_resultado", "bodega_ajuste_id") == (
        "bodega", "RESTRICT")
    assert not tabla.c.bodega_ajuste_id.nullable
    assert "bodega" not in tabla.c
    assert "uq_conteo_resultado_codigo" in _nombres(tabla, UniqueConstraint)
    assert "ix_conteo_resultado_historial" in _nombres(tabla, Index)


# --- migrations (static) ----------------------------------------------------


def test_revisions_chain_onto_the_role_and_stay_in_the_single_head_line():
    guion = ScriptDirectory.from_config(
        Config(str(_RAIZ / "alembic_motored.ini")))
    base, lecturas = _cargar("conteo_base"), _cargar("conteo_lecturas")

    assert len(guion.get_heads()) == 1  # later features chain on LECTURAS_REV
    assert (base.revision, base.down_revision) == (BASE_REV, "b4f9c2e6a813")
    assert (lecturas.revision, lecturas.down_revision) == (
        LECTURAS_REV, BASE_REV)


@pytest.mark.parametrize("sufijo, tablas", [
    ("conteo_base", TABLAS_BASE),
    ("conteo_lecturas", TABLAS_LECTURAS),
])
def test_upgrade_creates_its_tables_in_order(sufijo, tablas):
    op_mock = _ops(_cargar(sufijo), "upgrade")

    creadas = [c.args[0] for c in op_mock.create_table.call_args_list]
    assert creadas == list(tablas)


@pytest.mark.parametrize("sufijo, tablas", [
    ("conteo_base", TABLAS_BASE),
    ("conteo_lecturas", TABLAS_LECTURAS),
])
def test_downgrade_drops_its_tables_in_reverse(sufijo, tablas):
    op_mock = _ops(_cargar(sufijo), "downgrade")

    borradas = [c.args[0] for c in op_mock.drop_table.call_args_list]
    assert borradas == list(reversed(tablas))
