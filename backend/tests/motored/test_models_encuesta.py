"""
Motored satisfaction survey, slice T2 -- model-structure tests for the five
new tables (`encuesta_carga`, `encuesta_registro`, `encuesta_respuesta`,
`caso_detractor`, `caso_detractor_accion`). Same convention as
`test_models_bot.py`: models are schema, not behavior; no live DB.
"""
from sqlalchemy import CheckConstraint, Identity, SmallInteger, UniqueConstraint

from app.motored.database import MotoredBase
from app.motored.models import (
    CasoDetractor,
    CasoDetractorAccion,
    EncuestaCarga,
    EncuestaRegistro,
    EncuestaRespuesta,
)

MATRIX_COLUMNS = [
    "p_explicacion_tecnica",
    "p_confianza_reparacion",
    "p_servicio_taller",
    "p_calidad_mecanicos",
    "p_claridad_cobros",
    "p_originalidad_repuestos",
]


def _checks(model) -> dict:
    return {
        c.name: str(c.sqltext)
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint)
    }


def _uniques(model) -> dict:
    return {
        c.name: [col.name for col in c.columns]
        for c in model.__table__.constraints
        if isinstance(c, UniqueConstraint)
    }


def _fk_targets(model) -> dict:
    return {
        fk.parent.name: fk.target_fullname for fk in model.__table__.foreign_keys
    }


def test_all_five_tables_registered_in_metadata():
    for name in (
        "encuesta_carga",
        "encuesta_registro",
        "encuesta_respuesta",
        "caso_detractor",
        "caso_detractor_accion",
    ):
        assert name in MotoredBase.metadata.tables


def test_encuesta_carga_columns():
    cols = EncuestaCarga.__table__.c
    assert cols.nombre_archivo.nullable is False
    assert cols.total_registros.nullable is False
    assert _fk_targets(EncuestaCarga) == {"usuario_id": "usuario.id"}
    assert cols.usuario_id.nullable is False


def test_encuesta_registro_structure():
    cols = EncuestaRegistro.__table__.c
    assert _fk_targets(EncuestaRegistro) == {"carga_id": "encuesta_carga.id"}
    for name in ("carga_id", "tipo", "nombre", "cedula", "placa"):
        assert cols[name].nullable is False
    for name in ("celular", "linea", "sic", "centro_servicio"):
        assert cols[name].nullable is True
    assert _uniques(EncuestaRegistro) == {
        "uq_encuesta_registro_carga_cedula_placa_tipo": [
            "carga_id", "cedula", "placa", "tipo",
        ]
    }
    assert "SERVICIO_TALLER" in _checks(EncuestaRegistro)["ck_encuesta_registro_tipo"]
    assert "VENTA" in _checks(EncuestaRegistro)["ck_encuesta_registro_tipo"]
    index_cols = {
        tuple(c.name for c in ix.columns)
        for ix in EncuestaRegistro.__table__.indexes
    }
    assert ("cedula",) in index_cols


def test_encuesta_respuesta_required_and_matrix_nullability():
    cols = EncuestaRespuesta.__table__.c
    assert cols.satisfaccion_general.nullable is False
    assert isinstance(cols.satisfaccion_general.type, SmallInteger)
    for name in MATRIX_COLUMNS:
        assert cols[name].nullable is True, name
        assert isinstance(cols[name].type, SmallInteger)
    assert cols.observaciones.nullable is True
    assert cols.autoriza_datos.nullable is False


def test_encuesta_respuesta_one_per_registro_and_checks():
    assert _fk_targets(EncuestaRespuesta) == {"registro_id": "encuesta_registro.id"}
    assert _uniques(EncuestaRespuesta) == {
        "uq_encuesta_respuesta_registro_id": ["registro_id"]
    }
    checks = _checks(EncuestaRespuesta)
    assert "BETWEEN 1 AND 5" in checks["ck_encuesta_respuesta_satisfaccion_general"]
    for name in MATRIX_COLUMNS:
        expr = checks[f"ck_encuesta_respuesta_{name}"]
        assert "IS NULL" in expr and "BETWEEN 1 AND 5" in expr


def test_caso_detractor_structure():
    cols = CasoDetractor.__table__.c
    assert _fk_targets(CasoDetractor) == {
        "respuesta_id": "encuesta_respuesta.id",
        "asignado_a": "usuario.id",
    }
    assert cols.asignado_a.nullable is True
    assert cols.resultado.nullable is True
    assert cols.cerrado_at.nullable is True
    assert cols.estado.nullable is False
    assert cols.numero.nullable is False
    assert isinstance(cols.numero.identity, Identity)
    uniques = _uniques(CasoDetractor)
    assert uniques["uq_caso_detractor_respuesta_id"] == ["respuesta_id"]
    assert uniques["uq_caso_detractor_numero"] == ["numero"]


def test_caso_detractor_checks():
    checks = _checks(CasoDetractor)
    for value in ("ABIERTO", "EN_GESTION", "CERRADO"):
        assert value in checks["ck_caso_detractor_estado"]
    for value in ("RECUPERADO", "NO_RECUPERADO", "NO_CONTACTABLE"):
        assert value in checks["ck_caso_detractor_resultado"]
    iff = checks["ck_caso_detractor_resultado_iff_cerrado"]
    assert "estado = 'CERRADO'" in iff and "resultado IS NOT NULL" in iff
    assert "resultado IS NULL" in iff


def test_caso_detractor_accion_structure():
    cols = CasoDetractorAccion.__table__.c
    assert _fk_targets(CasoDetractorAccion) == {
        "caso_id": "caso_detractor.id",
        "usuario_id": "usuario.id",
    }
    assert cols.usuario_id.nullable is True  # NULL = system action
    assert cols.descripcion.nullable is False
    assert cols.tipo.nullable is False
    assert cols.estado_anterior.nullable is True
    assert cols.estado_nuevo.nullable is True
    tipo = _checks(CasoDetractorAccion)["ck_caso_detractor_accion_tipo"]
    for value in (
        "APERTURA", "LLAMADA", "WHATSAPP", "NOTA",
        "CAMBIO_ESTADO", "COMPENSACION", "CORRECCION",
    ):
        assert value in tipo
