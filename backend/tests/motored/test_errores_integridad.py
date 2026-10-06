"""
`services/errores_integridad`: an IntegrityError becomes a readable
Spanish message naming what really failed, and is logged with its
constraint. Only a real race on a natural key keeps "Otra carga
modificó...". Covers the helper itself, the upload handlers
(`services/carga.py`) and the maestros CRUD (`api/maestros.py`). The
real asyncpg errors live in `pg_real/test_errores_integridad_pg.py`.
"""
import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.sucursal import Sucursal
from app.motored.services import (
    bodegas_secundarias,
    carga,
    errores_integridad,
)
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

USER_ID = uuid.uuid4()
SUCURSALES_URL = "/api/motored/maestros/sucursales"
INTERNO_FK = (
    "No se pudo guardar por un error interno (restricción "
    "bodega_sucursal_id_fkey). Avise a soporte; reintentar no lo "
    "soluciona."
)


class _ErrorAsyncpg(Exception):
    """asyncpg's error: `sqlstate` and `constraint_name` attributes."""

    def __init__(self, sqlstate, constraint_name):
        super().__init__(f"violates constraint {constraint_name}")
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name


def _error_asyncpg(sqlstate, restriccion):
    """SQLAlchemy's asyncpg adapter keeps the driver error as
    `__cause__` of `exc.orig`."""
    orig = Exception("IntegrityError")
    orig.__cause__ = _ErrorAsyncpg(sqlstate, restriccion)
    return IntegrityError("COMMIT", {}, orig)


def _error_psycopg(sqlstate, restriccion):
    orig = Exception("IntegrityError")
    orig.sqlstate = sqlstate
    orig.diag = SimpleNamespace(constraint_name=restriccion)
    return IntegrityError("COMMIT", {}, orig)


async def _sin_filas(db, filas, usuario_id):
    return 0, 0, []


class TestDescribir:
    def test_reads_the_asyncpg_cause(self):
        violacion = errores_integridad.describir(
            _error_asyncpg("23503", "bodega_sucursal_id_fkey"), "prueba"
        )

        assert violacion == ("23503", "bodega_sucursal_id_fkey")

    def test_reads_the_psycopg_diag(self):
        violacion = errores_integridad.describir(
            _error_psycopg("23505", "sucursal_nombre_key"), "prueba"
        )

        assert violacion == ("23505", "sucursal_nombre_key")

    def test_falls_back_to_the_message_text(self):
        error = IntegrityError("COMMIT", {}, Exception(
            'insert or update on table "bodega" violates foreign key '
            'constraint "bodega_sucursal_id_fkey"'
        ))

        violacion = errores_integridad.describir(error, "prueba")

        assert violacion == ("23503", "bodega_sucursal_id_fkey")

    def test_an_unreadable_error_is_unknown(self):
        error = IntegrityError("COMMIT", {}, Exception("boom"))

        assert errores_integridad.describir(error, "prueba") == (None, None)

    def test_logs_the_constraint(self, caplog):
        with caplog.at_level(logging.WARNING):
            errores_integridad.describir(
                _error_asyncpg("23505", "uq_sucursal_codigo_co"), "carga"
            )

        assert "uq_sucursal_codigo_co" in caplog.text
        assert "23505" in caplog.text


class TestRespuesta:
    @pytest.mark.parametrize("restriccion,mensaje", [
        ("sucursal_nombre_key",
         "Dos sucursales quedarían con el mismo nombre."),
        ("uq_sucursal_codigo_co", "El Código C.O. ya es de otra sucursal."),
        ("bodega_codigo_key", "La bodega ya existe."),
    ])
    def test_known_constraints_have_their_own_message(
        self, restriccion, mensaje
    ):
        respuesta = errores_integridad.respuesta(
            errores_integridad.Violacion("23505", restriccion)
        )

        assert (respuesta.status_code, respuesta.detail) == (409, mensaje)

    def test_a_foreign_key_is_an_internal_error_naming_it(self):
        respuesta = errores_integridad.respuesta(
            errores_integridad.Violacion("23503", "bodega_sucursal_id_fkey")
        )

        assert (respuesta.status_code, respuesta.detail) == (500, INTERNO_FK)

    def test_another_unique_key_is_a_race(self):
        respuesta = errores_integridad.respuesta(
            errores_integridad.Violacion("23505", "uq_bodega_otra")
        )

        assert respuesta.status_code == 409
        assert respuesta.detail == errores_integridad.MENSAJE_CARRERA

    def test_a_race_may_bring_its_own_message(self):
        respuesta = errores_integridad.respuesta(
            errores_integridad.Violacion("23505", None), "Otra lista."
        )

        assert respuesta.detail == "Otra lista."

    def test_anything_else_is_internal(self):
        respuesta = errores_integridad.respuesta(
            errores_integridad.Violacion("23514", "ck_algo")
        )

        assert respuesta.status_code == 500
        assert "(restricción ck_algo)" in respuesta.detail


class TestCarga:
    async def test_a_foreign_key_in_the_upload_is_not_a_race(
        self, monkeypatch
    ):
        async def boom(db, entradas, usuario_id):
            raise _error_asyncpg("23503", "bodega_sucursal_id_fkey")

        monkeypatch.setattr(bodegas_secundarias, "aplicar", boom)
        db = FakeAsyncSession(execute_queue=[[], [], [], []])

        with pytest.raises(HTTPException) as exc:
            await _resolver_y_procesar_carga(db, "sucursal", [{
                "nombre": "CALI", "codigo_co": "E05",
                "bodega_principal": "BA061",
                "bodegas_secundarias": "BA066",
            }], USER_ID)

        assert (exc.value.status_code, exc.value.detail) == (500, INTERNO_FK)
        assert db.rolled_back is True

    async def test_a_store_name_collision_says_so(self):
        db = FakeAsyncSession(
            execute_queue=[[]],
            raise_integrity_error=_error_asyncpg(
                "23505", "sucursal_nombre_key"
            ),
        )

        with pytest.raises(HTTPException) as exc:
            await carga.procesar_carga(
                db, "sucursal", [{"nombre": "CALI", "codigo_co": "E05"}]
            )

        assert exc.value.status_code == 409
        assert exc.value.detail == (
            "Dos sucursales quedarían con el mismo nombre."
        )

    async def test_the_list_replacement_keeps_its_race_message(
        self, monkeypatch
    ):
        db = FakeAsyncSession(
            raise_integrity_error=_error_asyncpg("23505", "uq_algo"),
        )
        monkeypatch.setitem(
            carga._REEMPLAZO_POR_ENTIDAD, "cliente_tecnired", _sin_filas
        )

        with pytest.raises(HTTPException) as exc:
            await carga._reemplazar_lista(
                db, "cliente_tecnired", [], USER_ID
            )

        assert exc.value.status_code == 409
        assert "reemplazando esta lista" in exc.value.detail

    async def test_the_list_replacement_reports_an_internal_error(
        self, monkeypatch
    ):
        db = FakeAsyncSession(
            raise_integrity_error=_error_asyncpg("23503", "fk_algo"),
        )
        monkeypatch.setitem(
            carga._REEMPLAZO_POR_ENTIDAD, "cliente_tecnired", _sin_filas
        )

        with pytest.raises(HTTPException) as exc:
            await carga._reemplazar_lista(
                db, "cliente_tecnired", [], USER_ID
            )

        assert exc.value.status_code == 500
        assert "(restricción fk_algo)" in exc.value.detail


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "clave-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "clave-asc360")
    override_motored_user(MotoredUser(user_id=str(USER_ID), role="ADMIN"))
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _cali():
    return Sucursal(
        id=uuid.uuid4(), nombre="CALI", codigo_co="E05", activa=True,
        sic="S1", dias_seguridad=2.5,
    )


class TestCrud:
    def test_a_store_name_collision_says_so(self, api):
        cali = _cali()
        override_motored_db(FakeAsyncSession(
            execute_queue=[[], [cali], [], []],
            raise_integrity_error=_error_asyncpg(
                "23505", "sucursal_nombre_key"
            ),
        ))

        respuesta = api.patch(
            f"{SUCURSALES_URL}/{cali.id}", json={"nombre": "PASTO"}
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["detail"] == (
            "Dos sucursales quedarían con el mismo nombre."
        )

    def test_a_foreign_key_of_a_store_save_is_internal(self, api):
        cali = _cali()
        override_motored_db(FakeAsyncSession(
            execute_queue=[[], [cali], [], []],
            raise_integrity_error=_error_asyncpg(
                "23503", "bodega_sucursal_id_fkey"
            ),
        ))

        respuesta = api.patch(
            f"{SUCURSALES_URL}/{cali.id}", json={"ciudad": "Cali"}
        )

        assert respuesta.status_code == 500
        assert respuesta.json()["detail"] == INTERNO_FK

    def test_a_maestros_conflict_is_logged(self, api, caplog):
        cali = _cali()
        override_motored_db(FakeAsyncSession(
            execute_queue=[[], [cali], [], []],
            raise_integrity_error=_error_asyncpg(
                "23505", "uq_sucursal_codigo_co"
            ),
        ))

        with caplog.at_level(logging.WARNING):
            api.patch(f"{SUCURSALES_URL}/{cali.id}", json={"ciudad": "C"})

        assert "uq_sucursal_codigo_co" in caplog.text

