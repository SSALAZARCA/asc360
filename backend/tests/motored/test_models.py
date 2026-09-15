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
