"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B1, ADR-2): pruebas
de estructura de los modelos nuevos, siguiendo la convención de
`test_models_corridas.py`: los modelos son esquema, no comportamiento. Sin
base de datos viva.

Cubre `corrida_sucursal.estado_pedido` y las tres tablas nuevas
(`corrida_linea_historial`, `pedido_evento`, `corrida_envio`). Que el DDL de
la migración M1 coincide con estos modelos lo prueba
`pg_real/test_migration_fase4_pg.py` (compara contra la base migrada).
"""
import ast
from pathlib import Path

import pytest
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Numeric,
    UniqueConstraint,
)

from app.motored.database import MotoredBase
from app.motored.models import (
    CorridaEnvio,
    CorridaLineaHistorial,
    CorridaSucursal,
    PedidoEvento,
)

_RAIZ = Path(__file__).resolve().parents[2]
_MODULOS_NUEVOS = (
    "app/motored/models/corrida_linea_historial.py",
    "app/motored/models/pedido_evento.py",
    "app/motored/models/corrida_envio.py",
    "app/motored/services/corridas/pedido_tienda.py",
    "app/motored/services/corridas/valores.py",
    "app/motored/services/corridas/bloqueos.py",
    "app/motored/services/corridas/edicion.py",
    "app/motored/services/corridas/lecturas_pedido.py",
    "app/motored/services/corridas/envio.py",
    "app/motored/services/corridas/guardas.py",
    "app/motored/services/corridas/exportacion.py",
    "app/motored/services/corridas/exportacion_hmcl.py",
    "app/motored/api/corridas_comun.py",
    "app/motored/api/corridas_pedido.py",
    "app/motored/schemas/pedido.py",
    "app/motored/services/corridas/recorte.py",
    "app/motored/services/corridas/tope.py",
    "app/motored/services/parametros_claves.py",
    "app/motored/services/parametros_topes.py",
    "app/motored/api/parametros.py",
    "alembic_motored/versions/a3f7c1d9e642_fase4_pedido_tienda.py",
)
_NUEVAS = {
    "corrida_linea_historial": CorridaLineaHistorial,
    "pedido_evento": PedidoEvento,
    "corrida_envio": CorridaEnvio,
}


def _check(tabla, nombre):
    return next(
        c for c in tabla.constraints
        if isinstance(c, CheckConstraint) and c.name == nombre)


def _fk(tabla, columna):
    return next(
        c for c in tabla.constraints
        if isinstance(c, ForeignKeyConstraint)
        and columna in {e.parent.name for e in c.elements})


def _indices(tabla):
    return {ix.name: [str(c) for c in ix.expressions] for ix in tabla.indexes}


def test_the_three_new_tables_are_registered_on_motored_base():
    assert set(_NUEVAS) <= set(MotoredBase.metadata.tables)
    for modelo in _NUEVAS.values():
        assert modelo.metadata is MotoredBase.metadata


# --- corrida_sucursal.estado_pedido ---------------------------------------


def test_estado_pedido_is_a_nullable_varchar_10_without_default():
    columna = CorridaSucursal.__table__.c.estado_pedido

    assert columna.nullable is True
    assert columna.type.length == 10
    assert columna.server_default is None and columna.default is None


def test_estado_pedido_is_limited_to_the_three_pedido_states():
    check = _check(
        CorridaSucursal.__table__, "ck_corrida_sucursal_estado_pedido")

    assert str(check.sqltext) == (
        "estado_pedido IN ('BORRADOR', 'CERRADO', 'ENVIADO')")


# --- corrida_linea_historial ----------------------------------------------


def test_the_historial_has_the_adr2_columns():
    tabla = CorridaLineaHistorial.__table__

    assert [c.name for c in tabla.columns] == [
        "id", "corrida_id", "linea_id", "sucursal_id", "campo",
        "valor_anterior", "valor_nuevo", "motivo", "detalle", "usuario_id",
        "creado_en"]
    assert isinstance(tabla.c.id.type, BigInteger)
    assert tabla.c.id.identity is not None
    assert tabla.c.detalle.nullable is True
    for nombre in ("corrida_id", "linea_id", "sucursal_id", "campo",
                   "valor_anterior", "valor_nuevo", "motivo", "usuario_id",
                   "creado_en"):
        assert tabla.c[nombre].nullable is False, nombre


def test_the_historial_stores_quantities_as_numeric_14_2():
    tabla = CorridaLineaHistorial.__table__

    for nombre in ("valor_anterior", "valor_nuevo"):
        assert isinstance(tabla.c[nombre].type, Numeric)
        assert (tabla.c[nombre].type.precision,
                tabla.c[nombre].type.scale) == (14, 2)


def test_the_historial_checks_the_field_and_the_motivo():
    tabla = CorridaLineaHistorial.__table__

    assert str(_check(tabla, "ck_corrida_linea_historial_campo").sqltext) == (
        "campo IN ('pedido_final')")
    assert str(_check(tabla, "ck_corrida_linea_historial_motivo").sqltext) == (
        "motivo IN ('MANUAL', 'RECORTE_PRESUPUESTO')")
    assert tabla.c.campo.server_default.arg == "pedido_final"


def test_the_historial_cascades_with_the_corrida_and_the_line():
    tabla = CorridaLineaHistorial.__table__

    assert _fk(tabla, "corrida_id").ondelete == "CASCADE"
    assert _fk(tabla, "linea_id").ondelete == "CASCADE"
    assert _fk(tabla, "linea_id").elements[0].target_fullname == (
        "corrida_linea.id")
    assert _fk(tabla, "usuario_id").elements[0].target_fullname == "usuario.id"


def test_the_historial_has_its_two_lookup_indexes():
    indices = _indices(CorridaLineaHistorial.__table__)

    assert indices["ix_corrida_linea_historial_linea_creado"] == [
        "corrida_linea_historial.linea_id", "creado_en DESC"]
    assert indices["ix_corrida_linea_historial_corrida_sucursal"] == [
        "corrida_linea_historial.corrida_id",
        "corrida_linea_historial.sucursal_id"]


# --- pedido_evento --------------------------------------------------------


def test_pedido_evento_has_the_adr2_columns():
    tabla = PedidoEvento.__table__

    assert [c.name for c in tabla.columns] == [
        "id", "corrida_id", "sucursal_id", "evento", "motivo", "detalle",
        "usuario_id", "creado_en"]
    assert tabla.c.id.identity is not None
    assert tabla.c.evento.type.length == 20
    for nombre in ("motivo", "detalle", "usuario_id"):
        assert tabla.c[nombre].nullable is True, nombre
    for nombre in ("corrida_id", "sucursal_id", "evento", "creado_en"):
        assert tabla.c[nombre].nullable is False, nombre


def test_pedido_evento_admits_the_four_events_including_the_correction():
    check = _check(PedidoEvento.__table__, "ck_pedido_evento_evento")

    assert str(check.sqltext) == (
        "evento IN ('CERRADO', 'REABIERTO', 'ENVIADO', 'ENVIO_CORREGIDO')")


def test_a_reopen_event_needs_a_non_blank_motivo():
    check = _check(PedidoEvento.__table__, "ck_pedido_evento_reabierto_motivo")

    assert str(check.sqltext) == (
        "evento <> 'REABIERTO' OR "
        "(motivo IS NOT NULL AND length(btrim(motivo)) > 0)")


def test_pedido_evento_foreign_keys_and_index():
    tabla = PedidoEvento.__table__

    assert _fk(tabla, "corrida_id").ondelete == "CASCADE"
    assert _fk(tabla, "sucursal_id").elements[0].target_fullname == (
        "sucursal.id")
    assert _fk(tabla, "usuario_id").elements[0].target_fullname == "usuario.id"
    assert _indices(tabla)["ix_pedido_evento_corrida_sucursal_creado"] == [
        "pedido_evento.corrida_id", "pedido_evento.sucursal_id",
        "pedido_evento.creado_en"]


# --- corrida_envio --------------------------------------------------------


def test_corrida_envio_has_the_adr2_columns_and_a_composite_key():
    tabla = CorridaEnvio.__table__

    assert [c.name for c in tabla.columns] == [
        "corrida_id", "sucursal_id", "proveedor_id", "fecha_corte",
        "numero_pedido_proveedor", "fecha_envio", "enviada_por",
        "enviada_en"]
    assert [c.name for c in tabla.primary_key.columns] == [
        "corrida_id", "sucursal_id"]
    assert tabla.c.numero_pedido_proveedor.type.length == 50
    assert all(not c.nullable for c in tabla.columns)


def test_corrida_envio_restricts_the_corrida_delete():
    tabla = CorridaEnvio.__table__

    assert _fk(tabla, "corrida_id").ondelete == "RESTRICT"
    assert _fk(tabla, "proveedor_id").elements[0].target_fullname == (
        "proveedor.id")
    assert _fk(tabla, "enviada_por").elements[0].target_fullname == (
        "usuario.id")


def test_one_sent_pedido_per_proveedor_corte_and_tienda_f4_13():
    tabla = CorridaEnvio.__table__
    unicos = {
        u.name: [c.name for c in u.columns] for u in tabla.constraints
        if isinstance(u, UniqueConstraint)}

    assert unicos == {"uq_corrida_envio_corte_sucursal": [
        "proveedor_id", "fecha_corte", "sucursal_id"]}


def test_the_order_number_cannot_be_blank():
    check = _check(CorridaEnvio.__table__, "ck_corrida_envio_numero")

    assert str(check.sqltext) == "length(btrim(numero_pedido_proveedor)) > 0"


# --- Python 3.11 (producción) ---------------------------------------------


def _ast_311(ruta):
    return ast.parse(
        (_RAIZ / ruta).read_text(encoding="utf-8"), feature_version=(3, 11))


@pytest.mark.parametrize("ruta", _MODULOS_NUEVOS)
def test_new_modules_parse_as_python_311(ruta):
    _ast_311(ruta)


@pytest.mark.parametrize("ruta", _MODULOS_NUEVOS)
def test_new_modules_have_no_unhashable_field_default(ruta):
    """`field(default=<lista, dict, set o mappingproxy>)` importa bien en una
    versión nueva pero tumba el backend 3.11 al arrancar (caída 2026-09-30)."""
    ofensas = []
    for nodo in ast.walk(_ast_311(ruta)):
        if not isinstance(nodo, ast.Call):
            continue
        nombre = getattr(nodo.func, "id", getattr(nodo.func, "attr", ""))
        if nombre != "field":
            continue
        for palabra in nodo.keywords:
            peligroso = isinstance(
                palabra.value, (ast.List, ast.Dict, ast.Set, ast.Call))
            if palabra.arg == "default" and peligroso:
                ofensas.append(nodo.lineno)
    assert ofensas == []
