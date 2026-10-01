"""
Migraciones de la Fase 3 "Motor" (sdd/motored-pedidos-motor, S4a):

- `e5b19c47a3d8` crea las 5 tablas `corrida*` (ADR-3).
- `f2a6d83b9e14` agrega `parametro_metodologia.sucursal_id` (ADR-7).

Mismo enfoque que `test_migration_multi_asesor_telegram.py`: se cargan por
ruta y se ejercitan contra un `op` simulado, más un chequeo de acuerdo entre
los modelos y el DDL. Ambas son estrictamente aditivas.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from app.motored.database import MotoredBase
from app.motored.models import ParametroMetodologia

_VERSIONS = (
    Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
)

_TABLAS = (
    "corrida",
    "corrida_sucursal",
    "corrida_linea",
    "corrida_resumen",
    "corrida_carga",
)

# Columnas que los modelos tienen y que una migración POSTERIOR agregó a una
# tabla de F3 (F4, M1 `a3f7c1d9e642`): la migración de F3 no las crea.
_COLUMNAS_POSTERIORES = {"corrida_sucursal": {"estado_pedido"}}

_TABLAS_EXISTENTES = (
    "sucursal", "referencia", "proveedor", "usuario", "carga_archivo",
    "venta_mensual", "inventario_snapshot", "backorder_linea",
)


def _cargar(nombre_archivo: str, alias: str):
    spec = importlib.util.spec_from_file_location(
        alias, _VERSIONS / nombre_archivo,
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


corridas = _cargar("e5b19c47a3d8_fase3_corridas.py", "sdd_fase3_corridas")
param = _cargar(
    "f2a6d83b9e14_fase3_parametro_sucursal.py", "sdd_fase3_param_sucursal",
)


def _correr(modulo, direccion: str):
    with patch.object(modulo, "op") as op_mock:
        getattr(modulo, direccion)()
    return op_mock


def _tablas_creadas(op_mock) -> dict:
    return {c.args[0]: c for c in op_mock.create_table.call_args_list}


def _columnas(llamada) -> dict:
    return {
        a.name: a for a in llamada.args[1:] if hasattr(a, "nullable")
    }


def _sql(op_mock, indice: int) -> str:
    return str(op_mock.execute.call_args_list[indice].args[0])


# ---------------------------------------------------------------------------
# Cadena de revisiones
# ---------------------------------------------------------------------------


def test_corridas_chains_onto_the_encuesta_head():
    assert corridas.revision == "e5b19c47a3d8"
    assert corridas.down_revision == "c4e81a7d3f26"


def test_parametro_sucursal_chains_onto_corridas():
    assert param.revision == "f2a6d83b9e14"
    assert param.down_revision == "e5b19c47a3d8"


def test_the_motored_chain_has_a_single_head():
    revisiones, padres = set(), set()
    for archivo in _VERSIONS.glob("*.py"):
        modulo = _cargar(archivo.name, f"sdd_chain_{archivo.stem}")
        revisiones.add(modulo.revision)
        if modulo.down_revision:
            padres.add(modulo.down_revision)

    assert len(revisiones - padres) == 1
    assert {"e5b19c47a3d8", "f2a6d83b9e14"} <= padres | revisiones


# ---------------------------------------------------------------------------
# e5b19c47a3d8 -- corridas
# ---------------------------------------------------------------------------


def test_corridas_upgrade_sets_a_lock_timeout_first():
    op_mock = _correr(corridas, "upgrade")

    assert "lock_timeout" in _sql(op_mock, 0)
    assert "SET LOCAL" in _sql(op_mock, 0)


def test_corridas_upgrade_creates_the_five_tables_parent_first():
    op_mock = _correr(corridas, "upgrade")

    orden = [c.args[0] for c in op_mock.create_table.call_args_list]
    assert set(orden) == set(_TABLAS)
    assert orden[0] == "corrida"


def test_corridas_upgrade_is_purely_additive():
    op_mock = _correr(corridas, "upgrade")

    assert not op_mock.drop_table.called
    assert not op_mock.drop_column.called
    assert not op_mock.add_column.called
    assert not op_mock.alter_column.called
    assert not op_mock.drop_constraint.called
    assert not op_mock.drop_index.called


def test_corridas_upgrade_never_references_existing_tables_as_targets():
    op_mock = _correr(corridas, "upgrade")

    creadas = set(_tablas_creadas(op_mock))
    assert not creadas & set(_TABLAS_EXISTENTES)
    for llamada in op_mock.create_index.call_args_list:
        assert llamada.args[1] in _TABLAS


def test_corridas_upgrade_creates_the_adr3_indexes():
    op_mock = _correr(corridas, "upgrade")

    nombres = {c.args[0] for c in op_mock.create_index.call_args_list}
    assert nombres == {
        "ix_corrida_proveedor_fecha_corte",
        "ix_corrida_estado_created_at",
        "ix_corrida_estado_latido_en",
        "ix_corrida_sucursal_corrida_estado",
        "ix_corrida_linea_corrida_sucursal_orden_abc",
        "ix_corrida_linea_corrida_referencia",
        "ix_corrida_linea_corrida_estado_quiebre",
        "ix_corrida_carga_carga_id",
    }


def test_corridas_heartbeat_index_is_partial():
    op_mock = _correr(corridas, "upgrade")

    ix = next(
        c for c in op_mock.create_index.call_args_list
        if c.args[0] == "ix_corrida_estado_latido_en"
    )
    assert "latido_en IS NOT NULL" in str(ix.kwargs["postgresql_where"])


def test_corridas_downgrade_drops_children_before_the_parent():
    op_mock = _correr(corridas, "downgrade")

    orden = [c.args[0] for c in op_mock.drop_table.call_args_list]
    assert set(orden) == set(_TABLAS)
    assert orden[-1] == "corrida"
    assert orden.index("corrida_linea") < orden.index("corrida")


def test_corridas_downgrade_touches_only_the_new_tables():
    op_mock = _correr(corridas, "downgrade")

    assert not op_mock.drop_column.called
    assert not op_mock.alter_column.called


def test_corridas_tables_match_the_models_column_for_column():
    op_mock = _correr(corridas, "upgrade")
    creadas = _tablas_creadas(op_mock)

    for nombre in _TABLAS:
        modelo = MotoredBase.metadata.tables[nombre]
        ddl = _columnas(creadas[nombre])
        posteriores = _COLUMNAS_POSTERIORES.get(nombre, set())
        assert set(ddl) == set(modelo.c.keys()) - posteriores, nombre
        for col in modelo.c:
            if col.name in posteriores:
                continue
            assert ddl[col.name].nullable == col.nullable, (nombre, col.name)


def test_corridas_numeric_scales_match_the_models():
    op_mock = _correr(corridas, "upgrade")
    creadas = _tablas_creadas(op_mock)

    for nombre in _TABLAS:
        modelo = MotoredBase.metadata.tables[nombre]
        ddl = _columnas(creadas[nombre])
        for col in modelo.c:
            if col.name in ddl and col.type.__class__.__name__ == "Numeric":
                tipo = ddl[col.name].type
                assert (tipo.precision, tipo.scale) == (
                    col.type.precision, col.type.scale,
                ), (nombre, col.name)


# ---------------------------------------------------------------------------
# f2a6d83b9e14 -- parametro_metodologia.sucursal_id
# ---------------------------------------------------------------------------


def test_parametro_upgrade_sets_a_lock_timeout_first():
    op_mock = _correr(param, "upgrade")

    assert "lock_timeout" in _sql(op_mock, 0)


def test_parametro_upgrade_adds_one_nullable_column_and_one_index():
    op_mock = _correr(param, "upgrade")

    assert op_mock.add_column.call_count == 1
    tabla, columna = op_mock.add_column.call_args.args
    assert tabla == "parametro_metodologia"
    assert columna.name == "sucursal_id"
    assert columna.nullable is True
    assert columna.server_default is None
    assert [f.target_fullname for f in columna.foreign_keys] == [
        "sucursal.id",
    ]

    ix = op_mock.create_index.call_args
    assert ix.args[0] == "ix_parametro_metodologia_clave_sucursal_vigente"
    assert ix.args[1] == "parametro_metodologia"
    assert list(ix.args[2]) == ["clave", "sucursal_id", "vigente_desde"]


def test_parametro_upgrade_changes_nothing_else():
    op_mock = _correr(param, "upgrade")

    assert not op_mock.alter_column.called
    assert not op_mock.drop_column.called
    assert not op_mock.drop_table.called
    assert not op_mock.create_table.called


def test_parametro_downgrade_removes_the_index_then_the_column():
    op_mock = _correr(param, "downgrade")

    op_mock.drop_index.assert_called_once_with(
        "ix_parametro_metodologia_clave_sucursal_vigente",
        table_name="parametro_metodologia",
    )
    op_mock.drop_column.assert_called_once_with(
        "parametro_metodologia", "sucursal_id",
    )
    nombres = [c[0] for c in op_mock.mock_calls]
    assert nombres.index("drop_index") < nombres.index("drop_column")


def test_parametro_downgrade_deletes_scoped_rows_before_dropping():
    op_mock = _correr(param, "downgrade")

    borrado = _sql(op_mock, 1)
    assert "DELETE FROM parametro_metodologia" in borrado
    assert "sucursal_id IS NOT NULL" in borrado


def test_parametro_column_matches_the_model():
    op_mock = _correr(param, "upgrade")
    columna = op_mock.add_column.call_args.args[1]

    modelo = ParametroMetodologia.__table__.c.sucursal_id
    assert columna.nullable == modelo.nullable
