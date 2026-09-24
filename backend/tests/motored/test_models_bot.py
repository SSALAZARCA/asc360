"""
Phase 1 "Schema" (sdd/motored-ventas-perdidas-bot, design D2) — model-structure
tests for the bot-captura schema additions, mirroring `test_models_movimientos
.py`'s established convention: models are schema, not behavior; no live DB.

Covers `Usuario` (telegram/status/resolution columns), `CargaArchivo` (`origen`
discriminator + nullable file columns), `DemandaPerdida` (`origen` + widened
unique key) and the new `DemandaPerdidaBotLinea` ledger table (migration
`lore_bot_schema`, and `lore_role_enum` for the `ASESOR_MOSTRADOR` role value).
"""
from sqlalchemy import BigInteger, CheckConstraint, UniqueConstraint

from app.motored.database import MotoredBase
from app.motored.models import CargaArchivo, DemandaPerdida, MotoredRole, Usuario
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea


def _check_constraints(model) -> dict:
    return {
        c.name: str(c.sqltext)
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint)
    }


# ---------------------------------------------------------------------------
# MotoredRole / Usuario
# ---------------------------------------------------------------------------


def test_motored_role_has_asesor_mostrador():
    assert MotoredRole.ASESOR_MOSTRADOR.value == "ASESOR_MOSTRADOR"


def test_usuario_has_telegram_and_bot_registration_columns():
    cols = Usuario.__table__.c
    assert isinstance(cols.telegram_id.type, BigInteger)
    assert cols.telegram_id.nullable is True
    assert cols.phone.nullable is True
    assert cols.status.nullable is False
    assert cols.resuelto_por.nullable is True
    assert cols.resuelto_en.nullable is True
    assert cols.codigo_vinculacion_hash.nullable is True
    assert cols.codigo_vinculacion_expira.nullable is True


def test_usuario_telegram_id_is_unique():
    constraints = [
        c for c in Usuario.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [c for c in constraints if {col.name for col in c.columns} == {"telegram_id"}]
    assert len(match) == 1


def test_usuario_email_and_hashed_password_are_now_nullable():
    # Advisors (ASESOR_MOSTRADOR) have no web credentials at all.
    cols = Usuario.__table__.c
    assert cols.email.nullable is True
    assert cols.hashed_password.nullable is True


def test_usuario_has_status_and_credenciales_web_checks():
    checks = _check_constraints(Usuario)
    assert "pending" in checks["ck_usuario_status"]
    assert "approved" in checks["ck_usuario_status"]
    assert "rejected" in checks["ck_usuario_status"]
    assert "ASESOR_MOSTRADOR" in checks["ck_usuario_credenciales_web"]


# ---------------------------------------------------------------------------
# CargaArchivo
# ---------------------------------------------------------------------------


def test_carga_archivo_has_origen_discriminator():
    col = CargaArchivo.__table__.c.origen
    assert col.nullable is False


def test_carga_archivo_file_columns_are_nullable_for_bot_rows():
    cols = CargaArchivo.__table__.c
    for name in ("nombre_archivo", "hash_sha256", "ruta_objeto", "bytes"):
        assert cols[name].nullable is True


def test_carga_archivo_has_origen_and_bot_tipo_checks():
    checks = _check_constraints(CargaArchivo)
    assert "EXCEL" in checks["ck_carga_archivo_origen"]
    assert "BOT" in checks["ck_carga_archivo_origen"]
    assert "DEMANDA_PERDIDA" in checks["ck_carga_archivo_bot_tipo"]


def test_carga_archivo_has_origen_tipo_created_at_index():
    indexes = CargaArchivo.__table__.indexes
    match = [
        ix for ix in indexes
        if [col.name for col in ix.columns] == ["origen", "tipo", "created_at"]
    ]
    assert len(match) == 1


# ---------------------------------------------------------------------------
# DemandaPerdida
# ---------------------------------------------------------------------------


def test_demanda_perdida_has_origen_discriminator():
    assert DemandaPerdida.__table__.c.origen.nullable is False


def test_demanda_perdida_unique_key_is_widened_to_include_origen():
    constraints = [
        c for c in DemandaPerdida.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints
        if {col.name for col in c.columns} == {"fecha", "sucursal_id", "referencia_id", "origen"}
    ]
    assert len(match) == 1
    # The old 3-column key must be gone, not merely joined by a new one.
    stale = [
        c for c in constraints
        if {col.name for col in c.columns} == {"fecha", "sucursal_id", "referencia_id"}
    ]
    assert len(stale) == 0


# ---------------------------------------------------------------------------
# DemandaPerdidaBotLinea (new table)
# ---------------------------------------------------------------------------


def test_demanda_perdida_bot_linea_is_registered_on_motored_base():
    assert "demanda_perdida_bot_linea" in MotoredBase.metadata.tables


def test_demanda_perdida_bot_linea_does_not_use_asc360_base():
    from app.database import Base as Asc360Base

    assert DemandaPerdidaBotLinea.metadata is MotoredBase.metadata
    assert DemandaPerdidaBotLinea.metadata is not Asc360Base.metadata


def test_demanda_perdida_bot_linea_has_expected_columns():
    cols = DemandaPerdidaBotLinea.__table__.c
    for name in (
        "id", "carga_id", "usuario_id", "fecha", "sucursal_id",
        "referencia_id", "cantidad", "estado", "created_at", "updated_at",
    ):
        assert name in cols
    assert cols.cantidad.nullable is False
    assert cols.estado.nullable is False


def test_demanda_perdida_bot_linea_has_unique_carga_referencia():
    constraints = [
        c for c in DemandaPerdidaBotLinea.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]
    match = [
        c for c in constraints
        if {col.name for col in c.columns} == {"carga_id", "referencia_id"}
    ]
    assert len(match) == 1


def test_demanda_perdida_bot_linea_has_usuario_and_sucursal_fecha_indexes():
    indexes = DemandaPerdidaBotLinea.__table__.indexes
    assert any({col.name for col in ix.columns} == {"usuario_id", "fecha"} for ix in indexes)
    assert any({col.name for col in ix.columns} == {"sucursal_id", "fecha"} for ix in indexes)


def test_demanda_perdida_bot_linea_has_cantidad_and_estado_checks():
    checks = _check_constraints(DemandaPerdidaBotLinea)
    assert "cantidad > 0" in checks.values()
    assert any("ACTIVA" in text and "ANULADA" in text for text in checks.values())
