"""
Fase 3 "Motor" (sdd/motored-pedidos-motor, S4a) -- pruebas de estructura
de los modelos de corrida, siguiendo la convención de
`test_models_movimientos.py`: los modelos son esquema, no comportamiento.
Sin base de datos viva.

Cubre ADR-3 del diseño: las 5 tablas `corrida*` y la columna
`parametro_metodologia.sucursal_id`.
"""
import re

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Numeric,
    UniqueConstraint,
)

from app.motored.database import MotoredBase
from app.motored.models import (
    Corrida,
    CorridaCarga,
    CorridaLinea,
    CorridaResumen,
    CorridaSucursal,
    ParametroMetodologia,
)

_TABLAS = {
    "corrida": Corrida,
    "corrida_sucursal": CorridaSucursal,
    "corrida_linea": CorridaLinea,
    "corrida_resumen": CorridaResumen,
    "corrida_carga": CorridaCarga,
}

_ESTADOS_CORRIDA = {
    "PENDIENTE", "CALCULANDO", "FALLIDA", "BORRADOR",
    "EN_REVISION", "CERRADA", "ENVIADA", "ANULADA",
}


def _cols(nombres):
    return set(nombres)


def _uniques(tabla):
    return [
        {c.name for c in u.columns}
        for u in tabla.constraints
        if isinstance(u, UniqueConstraint)
    ]


def _indices(tabla):
    return {
        ix.name: [c.name for c in ix.columns] for ix in tabla.indexes
    }


def _check(tabla, nombre):
    return next(
        c for c in tabla.constraints
        if isinstance(c, CheckConstraint) and c.name == nombre
    )


def _escala(columna):
    return columna.type.precision, columna.type.scale


def test_five_corrida_tables_are_registered_on_motored_base():
    assert set(_TABLAS) <= set(MotoredBase.metadata.tables)
    for modelo in _TABLAS.values():
        assert modelo.metadata is MotoredBase.metadata


# ---------------------------------------------------------------------------
# corrida
# ---------------------------------------------------------------------------


def test_corrida_declares_the_adr3_columns():
    esperadas = {
        "id", "codigo", "proveedor_id", "fecha_corte", "estado",
        "es_escenario", "overrides", "alcance", "parametros_en_fecha",
        "parametros_snapshot", "maestro_sustitucion", "seleccion_datos",
        "invalidada", "motivo_invalidacion", "sucursales_total",
        "sucursales_procesadas", "latido_en", "intentos",
        "reintentar_despues_de", "log", "usuario_id", "iniciado_en",
        "terminado_en", "cerrada_en", "cerrada_por", "anulada_en",
        "anulada_por", "motivo_anulacion", "created_at",
    }
    assert esperadas == _cols(Corrida.__table__.c.keys())


def test_corrida_required_columns_are_not_nullable():
    cols = Corrida.__table__.c
    for nombre in ("codigo", "proveedor_id", "fecha_corte", "estado",
                   "es_escenario", "invalidada", "intentos"):
        assert cols[nombre].nullable is False, nombre


def test_corrida_snapshot_columns_are_jsonb_and_nullable():
    cols = Corrida.__table__.c
    for nombre in ("overrides", "parametros_snapshot",
                   "maestro_sustitucion", "seleccion_datos", "log",
                   "motivo_invalidacion"):
        assert cols[nombre].type.__class__.__name__ == "JSONB", nombre
        assert cols[nombre].nullable is True, nombre


def test_corrida_estado_check_lists_the_eight_states():
    texto = str(_check(Corrida.__table__, "ck_corrida_estado").sqltext)

    assert set(re.findall(r"'([A-Z_]+)'", texto)) == _ESTADOS_CORRIDA


def test_corrida_alcance_check_allows_todas_or_seleccion():
    texto = str(_check(Corrida.__table__, "ck_corrida_alcance").sqltext)

    assert set(re.findall(r"'([A-Z_]+)'", texto)) == {"TODAS", "SELECCION"}


def test_corrida_codigo_is_unique():
    assert {"codigo"} in _uniques(Corrida.__table__)


def test_corrida_indexes_match_adr3():
    indices = _indices(Corrida.__table__)

    assert indices["ix_corrida_proveedor_fecha_corte"] == ["proveedor_id"]
    assert indices["ix_corrida_estado_created_at"] == [
        "estado", "created_at",
    ]
    assert indices["ix_corrida_estado_latido_en"] == ["estado", "latido_en"]


def test_corrida_heartbeat_index_is_partial_on_latido_en():
    ix = next(
        i for i in Corrida.__table__.indexes
        if i.name == "ix_corrida_estado_latido_en"
    )

    donde = str(ix.dialect_options["postgresql"]["where"])
    assert "latido_en IS NOT NULL" in donde


def test_corrida_fecha_corte_index_is_descending():
    ix = next(
        i for i in Corrida.__table__.indexes
        if i.name == "ix_corrida_proveedor_fecha_corte"
    )

    assert "fecha_corte DESC" in [str(e) for e in ix.expressions]


# ---------------------------------------------------------------------------
# corrida_sucursal / corrida_resumen / corrida_carga
# ---------------------------------------------------------------------------


def test_corrida_sucursal_pk_is_corrida_and_sucursal():
    pk = [c.name for c in CorridaSucursal.__table__.primary_key.columns]

    assert pk == ["corrida_id", "sucursal_id"]


def test_corrida_sucursal_estado_check_lists_four_states():
    texto = str(
        _check(CorridaSucursal.__table__, "ck_corrida_sucursal_estado")
        .sqltext
    )

    assert set(re.findall(r"'([A-Z_]+)'", texto)) == {
        "PENDIENTE", "OK", "OMITIDA", "FALLIDA",
    }


def test_corrida_sucursal_snapshot_columns():
    cols = CorridaSucursal.__table__.c

    for nombre in ("orden", "estado", "codigo", "mensaje", "fecha_apertura",
                   "divisor", "buckets_operados", "dias_empaque",
                   "dias_transito", "dias_seguridad", "dias_entre_pedidos",
                   "parametros", "coberturas", "lineas", "excluidas",
                   "unidades", "valor", "intentos", "iniciado_en",
                   "terminado_en"):
        assert nombre in cols, nombre
    assert _escala(cols.dias_entre_pedidos) == (6, 2)


def test_corrida_sucursal_has_estado_index():
    indices = _indices(CorridaSucursal.__table__)

    assert indices["ix_corrida_sucursal_corrida_estado"] == [
        "corrida_id", "estado",
    ]


def test_corrida_resumen_pk_is_corrida_sucursal_clase():
    pk = [c.name for c in CorridaResumen.__table__.primary_key.columns]

    assert pk == ["corrida_id", "sucursal_id", "clase"]


def test_corrida_resumen_percentage_is_nullable():
    cols = CorridaResumen.__table__.c

    assert cols.porcentaje_peso.nullable is True
    assert _escala(cols.valor) == (16, 2)


def test_corrida_carga_pk_and_index():
    tabla = CorridaCarga.__table__

    assert [c.name for c in tabla.primary_key.columns] == [
        "corrida_id", "carga_id",
    ]
    assert _indices(tabla)["ix_corrida_carga_carga_id"] == ["carga_id"]
    assert tabla.c.tipo.nullable is False


def test_children_cascade_when_the_corrida_is_deleted():
    for modelo in (CorridaSucursal, CorridaLinea, CorridaResumen,
                   CorridaCarga):
        fk = next(
            f for f in modelo.__table__.foreign_keys
            if f.parent.name == "corrida_id"
        )
        assert fk.ondelete == "CASCADE", modelo.__tablename__


# ---------------------------------------------------------------------------
# corrida_linea
# ---------------------------------------------------------------------------


def test_corrida_linea_id_is_a_bigint_identity():
    col = CorridaLinea.__table__.c.id

    assert isinstance(col.type, BigInteger)
    assert col.identity is not None


def test_corrida_linea_is_unique_per_corrida_sucursal_referencia():
    assert {"corrida_id", "sucursal_id", "referencia_id"} in _uniques(
        CorridaLinea.__table__
    )


def test_corrida_linea_indexes_match_adr3():
    indices = _indices(CorridaLinea.__table__)

    assert indices["ix_corrida_linea_corrida_sucursal_orden_abc"] == [
        "corrida_id", "sucursal_id", "orden_abc",
    ]
    assert indices["ix_corrida_linea_corrida_referencia"] == [
        "corrida_id", "referencia_id",
    ]
    assert indices["ix_corrida_linea_corrida_estado_quiebre"] == [
        "corrida_id", "estado_quiebre",
    ]


def test_corrida_linea_has_the_raw_input_columns():
    cols = CorridaLinea.__table__.c
    meses = [f"venta_m{i}" for i in range(0, 7)]
    perdidas = [f"perdida_m{i}" for i in range(0, 7)]

    for nombre in (*meses, *perdidas, "precio", "unidad_empaque",
                   "inventario", "transito", "backorder", "ajuste"):
        assert nombre in cols, nombre


def test_corrida_linea_m0_columns_are_nullable():
    cols = CorridaLinea.__table__.c

    for nombre in ("venta_m0", "perdida_m0", "venta_m0_proyectada",
                   "precio"):
        assert cols[nombre].nullable is True, nombre


def test_corrida_linea_closed_month_inputs_are_not_nullable():
    cols = CorridaLinea.__table__.c

    for i in range(1, 7):
        assert cols[f"venta_m{i}"].nullable is False
        assert cols[f"perdida_m{i}"].nullable is False


def test_corrida_linea_has_the_output_columns():
    cols = CorridaLinea.__table__.c

    for nombre in ("demanda_perdida", "demanda_perdida_mensualizada",
                   "demanda_prom_simple", "demanda_ponderada", "peso_pct",
                   "peso_acum_pct", "orden_abc", "clase_abc", "clase_fms",
                   "clase", "meses_con_venta", "meses_cobertura",
                   "inventario_final", "y_recibido", "stock_objetivo",
                   "pedido_sugerido", "pedido_final", "valor_pedido",
                   "cobertura_final", "cobertura_actual", "punto_minimo",
                   "punto_maximo", "estado_quiebre", "motivo_exclusion",
                   "sustituta_final_id", "banderas",
                   "detalle_consolidacion", "ultima_fecha_entrada"):
        assert nombre in cols, nombre


def test_corrida_linea_storage_scales_follow_adr1():
    cols = CorridaLinea.__table__.c
    escalas = {
        "venta_m3": (14, 2), "perdida_m3": (14, 2), "precio": (14, 2),
        "inventario": (14, 2), "transito": (14, 2), "backorder": (14, 2),
        "ajuste": (14, 2),
        "demanda_ponderada": (18, 6), "stock_objetivo": (18, 6),
        "venta_m0_proyectada": (18, 6), "punto_minimo": (18, 6),
        "punto_maximo": (18, 6),
        "peso_pct": (14, 10), "peso_acum_pct": (14, 10),
        "cobertura_final": (12, 6), "cobertura_actual": (12, 6),
        "meses_cobertura": (12, 6),
        "pedido_sugerido": (14, 2), "pedido_final": (14, 2),
        "valor_pedido": (16, 2),
    }

    for nombre, esperada in escalas.items():
        assert isinstance(cols[nombre].type, Numeric), nombre
        assert _escala(cols[nombre]) == esperada, nombre


def test_corrida_linea_substitute_link_points_to_referencia():
    fk = next(
        f for f in CorridaLinea.__table__.foreign_keys
        if f.parent.name == "sustituta_final_id"
    )

    assert fk.column.table.name == "referencia"


def test_corrida_linea_banderas_is_a_non_null_array():
    col = CorridaLinea.__table__.c.banderas

    assert col.type.__class__.__name__ == "ARRAY"
    assert col.nullable is False


# ---------------------------------------------------------------------------
# parametro_metodologia.sucursal_id
# ---------------------------------------------------------------------------


def test_parametro_metodologia_gains_a_nullable_sucursal_fk():
    col = ParametroMetodologia.__table__.c.sucursal_id

    assert col.nullable is True
    assert [f.column.table.name for f in col.foreign_keys] == ["sucursal"]


def test_parametro_metodologia_has_clave_sucursal_vigente_index():
    indices = _indices(ParametroMetodologia.__table__)

    assert indices["ix_parametro_metodologia_clave_sucursal_vigente"] == [
        "clave", "sucursal_id", "vigente_desde",
    ]
