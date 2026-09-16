"""
Phase 3 "Models/Schemas/Services" — task 3.1 (sdd/motored-pedidos-cimientos).

Proves the 9 masters/auth models exist on `MotoredBase` (not on asc360's
`app.database.Base`), with the constraints locked by the proposal/spec:
`referencia` UNIQUE(codigo, proveedor_id), `sucursal.nombre` UNIQUE,
`bodega.codigo` UNIQUE, `proveedor.codigo` UNIQUE.
"""
from sqlalchemy import UniqueConstraint

from app.motored.database import MotoredBase
from app.motored.models import (
    AuditoriaMaestro,
    Bodega,
    ParametroMetodologia,
    Proveedor,
    Referencia,
    Sucursal,
    SucursalAlias,
    Usuario,
    UsuarioSucursal,
)


def test_all_nine_tables_are_registered_on_motored_base():
    expected = {
        "usuario",
        "proveedor",
        "sucursal",
        "bodega",
        "referencia",
        "parametro_metodologia",
        "sucursal_alias",
        "usuario_sucursal",
        "auditoria_maestro",
    }
    assert expected.issubset(set(MotoredBase.metadata.tables.keys()))


def test_models_do_not_use_asc360_base():
    from app.database import Base as Asc360Base

    for model in (
        Usuario,
        Proveedor,
        Sucursal,
        Bodega,
        Referencia,
        ParametroMetodologia,
        SucursalAlias,
        UsuarioSucursal,
        AuditoriaMaestro,
    ):
        assert model.metadata is MotoredBase.metadata
        assert model.metadata is not Asc360Base.metadata


def test_proveedor_codigo_is_unique():
    col = Proveedor.__table__.c.codigo
    assert col.unique is True


def test_sucursal_nombre_is_unique():
    col = Sucursal.__table__.c.nombre
    assert col.unique is True


def test_bodega_codigo_is_unique():
    col = Bodega.__table__.c.codigo
    assert col.unique is True


def test_referencia_has_composite_unique_codigo_proveedor():
    constraints = [
        c for c in Referencia.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    composite = [c for c in constraints if {col.name for col in c.columns} == {"codigo", "proveedor_id"}]
    assert len(composite) == 1


def test_referencia_unidad_empaque_defaults_to_one():
    assert Referencia.__table__.c.unidad_empaque.default.arg == 1


def test_parametro_metodologia_has_no_updated_at_column():
    # Insert-only versioning: no row is ever updated in place, so there is
    # no `updated_at` to track (spec: "a change creates a new row ... the
    # prior row is left completely unmodified").
    assert "updated_at" not in ParametroMetodologia.__table__.c


# ---------------------------------------------------------------------------
# Post-archive correction (sdd/motored-pedidos-cimientos): 4 masters models
# were missing fields the source spec (ESPECIFICACION_MOTORED_PEDIDOS.md
# §4.1) requires. See sdd/motored-pedidos-cimientos/apply-progress for the
# full audit/fix narrative.
# ---------------------------------------------------------------------------


def test_sucursal_has_the_six_spec_fields_added_by_the_correction():
    columns = Sucursal.__table__.c
    for name in (
        "dias_empaque",
        "dias_transito",
        "bodega_principal",
        "departamento",
        "ciudad",
        "fecha_apertura",
    ):
        assert name in columns, f"sucursal.{name} missing (spec §4.1)"
        assert columns[name].nullable is True


def test_proveedor_has_dias_seguridad_default():
    col = Proveedor.__table__.c.dias_seguridad_default
    assert col.nullable is True
    assert float(col.default.arg) == 2.5


def test_referencia_field_is_named_nombre_not_descripcion():
    columns = Referencia.__table__.c
    assert "nombre" in columns, "spec §4.1 names this field 'nombre', not 'descripcion'"
    assert "descripcion" not in columns


def test_referencia_has_linea_comercial():
    col = Referencia.__table__.c.linea_comercial
    assert col.nullable is True


def test_bodega_has_descripcion():
    col = Bodega.__table__.c.descripcion
    assert col.nullable is True


def test_bodega_activa_is_untouched_owner_decision_3():
    # Not a spec §4.1 literal field, but required by owner decision #3
    # (masters are never hard-deleted) -- explicitly NOT part of this
    # correction's scope, kept here as a regression guard.
    assert "activa" in Bodega.__table__.c
