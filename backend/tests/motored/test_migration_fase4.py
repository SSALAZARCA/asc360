"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B1, ADR-2): la
migración M1 `a3f7c1d9e642` (estado del pedido por tienda, historial de
edición, eventos del pedido y envíos), probada de forma ESTÁTICA con un `op`
simulado, al estilo de `test_migration_fase3_corridas.py`. El upgrade, el
downgrade y el backfill contra un Postgres real viven en
`pg_real/test_migration_fase4_pg.py`.

Cubre la cadena (una sola cabeza, encadenada sobre `d9a2b6e04f71`), que sea
aditiva, el `lock_timeout`, el backfill de F3 y el downgrade.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

_RAIZ = Path(__file__).resolve().parents[2]
_ARCHIVO = (
    _RAIZ / "alembic_motored" / "versions"
    / "a3f7c1d9e642_fase4_pedido_tienda.py")
_TABLAS = ("corrida_linea_historial", "pedido_evento", "corrida_envio")


def _cargar():
    spec = importlib.util.spec_from_file_location("sdd_fase4_m1", _ARCHIVO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


m1 = _cargar()


def _correr(direccion):
    with patch.object(m1, "op") as op_mock:
        getattr(m1, direccion)()
    return op_mock


def _sql(op_mock):
    return [str(c.args[0]) for c in op_mock.execute.call_args_list]


def test_alembic_single_head():
    guion = ScriptDirectory.from_config(
        Config(str(_RAIZ / "alembic_motored.ini")))

    assert guion.get_heads() == ["a8d4f1c6b923"]  # factura_linea_cliente_nit_tipo_pedido


def test_m1_chains_onto_the_login_lockout_head():
    assert m1.revision == "a3f7c1d9e642"
    assert m1.down_revision == "d9a2b6e04f71"


def test_upgrade_sets_a_lock_timeout_first():
    op_mock = _correr("upgrade")

    assert _sql(op_mock)[0] == "SET LOCAL lock_timeout = '5s'"


def test_upgrade_creates_the_three_tables_and_the_column():
    op_mock = _correr("upgrade")

    creadas = [c.args[0] for c in op_mock.create_table.call_args_list]
    assert sorted(creadas) == sorted(_TABLAS)
    columna = op_mock.add_column.call_args.args
    assert columna[0] == "corrida_sucursal"
    assert columna[1].name == "estado_pedido" and columna[1].nullable is True


def test_upgrade_is_purely_additive():
    op_mock = _correr("upgrade")

    assert not op_mock.drop_table.called
    assert not op_mock.drop_column.called
    assert not op_mock.alter_column.called
    for sentencia in _sql(op_mock):
        assert "DROP" not in sentencia.upper()
        assert "DELETE" not in sentencia.upper()


def test_upgrade_backfills_only_the_new_column_and_inserts_events():
    sentencias = _sql(_correr("upgrade"))

    actualizaciones = [
        s for s in sentencias if s.lstrip().startswith("UPDATE")]
    assert actualizaciones
    for sentencia in actualizaciones:
        assert "UPDATE corrida_sucursal" in sentencia
        asignado = sentencia.split("SET", 1)[1].split("FROM", 1)[0]
        assert asignado.strip().startswith("estado_pedido")
        assert "estado " not in asignado.replace("estado_pedido", "")


def test_the_backfill_skips_scenarios_and_non_ok_tiendas():
    sentencias = " ".join(_sql(_correr("upgrade")))

    assert "NOT c.es_escenario" in sentencias
    assert "cs.estado = 'OK'" in sentencias


def test_the_backfill_closes_f3_cerrada_corridas_with_a_migrado_event():
    sentencias = _sql(_correr("upgrade"))

    insercion = next(s for s in sentencias if "INSERT INTO pedido_evento" in s)
    assert "'CERRADO'" in insercion and "migrado_f3" in insercion
    assert "c.estado = 'CERRADA'" in insercion
    assert "NULL" in insercion.split("SELECT", 1)[1].split("FROM", 1)[0]


def test_the_constraint_on_estado_pedido_is_added():
    op_mock = _correr("upgrade")

    llamada = op_mock.create_check_constraint.call_args
    assert llamada.args[0] == "ck_corrida_sucursal_estado_pedido"
    assert llamada.args[1] == "corrida_sucursal"


def test_downgrade_drops_children_first_then_the_column():
    op_mock = _correr("downgrade")

    caidas = [c.args[0] for c in op_mock.drop_table.call_args_list]
    assert sorted(caidas) == sorted(_TABLAS)
    assert op_mock.drop_constraint.call_args.args[0] == (
        "ck_corrida_sucursal_estado_pedido")
    assert op_mock.drop_column.call_args.args == (
        "corrida_sucursal", "estado_pedido")
