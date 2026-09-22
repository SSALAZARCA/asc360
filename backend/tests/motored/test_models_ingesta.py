"""
Phase 1 "Staging Schema" (sdd/motored-pedidos-ingesta) — model-structure
tests, mirroring `test_models.py`'s established convention: models are
schema, not behavior. These assert each new table/column exists with the
right type/constraint; no live DB, no service logic.

Covers the 4 new staging tables (`carga_archivo`, `carga_error`,
`carga_fila_staging`, `retencion_ejecucion`) from design doc §Schema, plus
the `sucursal_alias` UNIQUE(texto_normalizado) correction (H11 prereq,
migration `fase2_alias_unique`).
"""
from sqlalchemy import UniqueConstraint

from app.motored.database import MotoredBase
from app.motored.models import (
    CargaArchivo,
    CargaError,
    CargaFilaStaging,
    RetencionEjecucion,
    SucursalAlias,
)


def test_four_staging_tables_are_registered_on_motored_base():
    expected = {
        "carga_archivo",
        "carga_error",
        "carga_fila_staging",
        "retencion_ejecucion",
    }
    assert expected.issubset(set(MotoredBase.metadata.tables.keys()))


def test_ingesta_models_do_not_use_asc360_base():
    from app.database import Base as Asc360Base

    for model in (CargaArchivo, CargaError, CargaFilaStaging, RetencionEjecucion):
        assert model.metadata is MotoredBase.metadata
        assert model.metadata is not Asc360Base.metadata


# ---------------------------------------------------------------------------
# carga_archivo
# ---------------------------------------------------------------------------


def test_carga_archivo_has_no_job_id_column():
    # ADR-1b: replaced by `latido_en` (heartbeat sweep), never a job queue id.
    assert "job_id" not in CargaArchivo.__table__.c


def test_carga_archivo_has_latido_en_column():
    col = CargaArchivo.__table__.c.latido_en
    assert col.nullable is True


def test_carga_archivo_periodo_columns_are_nullable_dates():
    from sqlalchemy import Date

    for name in ("periodo_desde", "periodo_hasta"):
        col = CargaArchivo.__table__.c[name]
        assert col.nullable is True
        assert isinstance(col.type, Date)


def test_carga_archivo_tipo_is_nullable():
    # tipo starts NULL until server-side detection resolves it (ADR-9 gate).
    assert CargaArchivo.__table__.c.tipo.nullable is True


def test_carga_archivo_hash_sha256_index_is_not_unique():
    indexes = {ix.name: ix for ix in CargaArchivo.__table__.indexes}
    hash_indexes = [ix for ix in indexes.values() if {c.name for c in ix.columns} == {"hash_sha256"}]
    assert len(hash_indexes) == 1
    assert hash_indexes[0].unique is False


def test_carga_archivo_has_composite_index_tipo_estado_created_at():
    indexes = CargaArchivo.__table__.indexes
    composite = [ix for ix in indexes if {c.name for c in ix.columns} == {"tipo", "estado", "created_at"}]
    assert len(composite) == 1


def test_carga_archivo_log_is_jsonb():
    from sqlalchemy.dialects.postgresql import JSONB

    assert isinstance(CargaArchivo.__table__.c.log.type, JSONB)


# ---------------------------------------------------------------------------
# carga_error
# ---------------------------------------------------------------------------


def test_carga_error_carga_id_cascades_on_delete():
    fk = next(iter(CargaError.__table__.c.carga_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_carga_error_has_index_carga_id_codigo_error():
    indexes = CargaError.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"carga_id", "codigo_error"}]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# carga_fila_staging
# ---------------------------------------------------------------------------


def test_carga_fila_staging_has_unique_carga_id_fila():
    constraints = [c for c in CargaFilaStaging.__table__.constraints if isinstance(c, UniqueConstraint)]
    composite = [c for c in constraints if {col.name for col in c.columns} == {"carga_id", "fila"}]
    assert len(composite) == 1


def test_carga_fila_staging_has_index_carga_id_lote():
    indexes = CargaFilaStaging.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"carga_id", "lote"}]
    assert len(match) == 1


def test_carga_fila_staging_resolved_keys_are_nullable():
    # ADR-2: NULL where resolution failed at dry-run; `Aplicar` re-resolves
    # only the NULLs against current masters.
    for name in ("sucursal_id", "referencia_id"):
        assert CargaFilaStaging.__table__.c[name].nullable is True


def test_carga_fila_staging_payload_is_jsonb():
    from sqlalchemy.dialects.postgresql import JSONB

    assert isinstance(CargaFilaStaging.__table__.c.payload.type, JSONB)


# ---------------------------------------------------------------------------
# retencion_ejecucion
# ---------------------------------------------------------------------------


def test_retencion_ejecucion_has_index_tabla_ejecutado_en():
    indexes = RetencionEjecucion.__table__.indexes
    match = [ix for ix in indexes if {c.name for c in ix.columns} == {"tabla", "ejecutado_en"}]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# sucursal_alias correction (migration `fase2_alias_unique`, H11 prereq)
# ---------------------------------------------------------------------------


def test_sucursal_alias_texto_normalizado_is_unique():
    col = SucursalAlias.__table__.c.texto_normalizado
    assert col.unique is True
