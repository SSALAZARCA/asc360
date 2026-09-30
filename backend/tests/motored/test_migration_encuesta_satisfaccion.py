"""
Motored satisfaction survey, slice T2 -- static tests for the
`encuesta_satisfaccion_schema` revision. Same approach as
`test_migration_lore_bot_schema.py`: load the revision by file path and assert
against a mocked `op` plus the migration source (no live Postgres in tests).
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic_motored" / "versions"
_FILE = _VERSIONS_DIR / "c4e81a7d3f26_encuesta_satisfaccion_schema.py"

_spec = importlib.util.spec_from_file_location("sdd_encuesta_schema_migration", _FILE)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)

SOURCE = _FILE.read_text(encoding="utf-8")

TABLES_IN_CREATE_ORDER = [
    "encuesta_carga",
    "encuesta_registro",
    "encuesta_respuesta",
    "caso_detractor",
    "caso_detractor_accion",
]


def _run(fn_name: str) -> MagicMock:
    with patch.object(migration, "op", MagicMock()) as op_mock:
        getattr(migration, fn_name)()
    return op_mock


def _created(op_mock) -> dict:
    return {c.args[0]: c for c in op_mock.create_table.call_args_list}


def _columns(call) -> dict:
    return {a.name: a for a in call.args[1:] if hasattr(a, "nullable")}


def test_revision_chain():
    assert migration.revision == "c4e81a7d3f26"
    assert migration.down_revision == "7be41d9c0a26"


def test_upgrade_creates_five_tables_in_dependency_order():
    op_mock = _run("upgrade")
    order = [c.args[0] for c in op_mock.create_table.call_args_list]
    assert order == TABLES_IN_CREATE_ORDER


def test_downgrade_drops_in_reverse_order():
    op_mock = _run("downgrade")
    order = [c.args[0] for c in op_mock.drop_table.call_args_list]
    assert order == list(reversed(TABLES_IN_CREATE_ORDER))


def test_upgrade_creates_append_only_trigger_and_function():
    op_mock = _run("upgrade")
    sql = " ".join(str(c.args[0]) for c in op_mock.execute.call_args_list)
    assert "CREATE OR REPLACE FUNCTION" in sql
    assert "RAISE EXCEPTION" in sql
    assert "BEFORE UPDATE OR DELETE ON caso_detractor_accion" in sql
    assert "CREATE TRIGGER" in sql


def test_downgrade_drops_trigger_and_function_before_table():
    op_mock = _run("downgrade")
    calls = [c[0] for c in op_mock.method_calls]
    sql = " ".join(str(c.args[0]) for c in op_mock.execute.call_args_list)
    assert "DROP TRIGGER" in sql and "DROP FUNCTION" in sql
    first_exec = calls.index("execute")
    accion_drop = [
        i for i, c in enumerate(op_mock.method_calls)
        if c[0] == "drop_table" and c[1][0] == "caso_detractor_accion"
    ][0]
    assert first_exec < accion_drop


def test_respuesta_matrix_nullable_and_satisfaccion_required():
    cols = _columns(_created(_run("upgrade"))["encuesta_respuesta"])
    assert cols["satisfaccion_general"].nullable is False
    for name in (
        "p_explicacion_tecnica", "p_confianza_reparacion", "p_servicio_taller",
        "p_calidad_mecanicos", "p_claridad_cobros", "p_originalidad_repuestos",
    ):
        assert cols[name].nullable is True, name


def test_caso_detractor_resultado_iff_cerrado_check_present():
    assert "ck_caso_detractor_resultado_iff_cerrado" in SOURCE
    assert "resultado IS NOT NULL" in SOURCE
    assert "ck_caso_detractor_estado" in SOURCE
    assert "ck_caso_detractor_resultado" in SOURCE


def test_caso_detractor_numero_is_identity_and_unique():
    call = _created(_run("upgrade"))["caso_detractor"]
    numero = _columns(call)["numero"]
    assert numero.identity is not None
    assert numero.nullable is False
    assert "uq_caso_detractor_numero" in SOURCE


def test_registro_unique_and_cedula_index():
    assert "uq_encuesta_registro_carga_cedula_placa_tipo" in SOURCE
    op_mock = _run("upgrade")
    idx = [c.args for c in op_mock.create_index.call_args_list]
    assert any(a[1] == "encuesta_registro" and a[2] == ["cedula"] for a in idx)


def test_chain_keeps_a_single_head_and_encuesta_is_not_orphaned():
    revisions, downs = set(), set()
    for path in _VERSIONS_DIR.glob("*.py"):
        spec = importlib.util.spec_from_file_location(f"m_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        revisions.add(module.revision)
        downs.add(module.down_revision)
    # Later slices (Fase 3 S4a) chain on top of this revision, so it is no
    # longer the head itself: what matters is one head and no fork here.
    assert len(revisions - downs) == 1
    assert migration.revision in downs
