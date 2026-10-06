"""
Sucursal store code "C.O." (centro de operación).

Each store has an ERP code: one region letter plus two digits (E05, C06).
A different C.O. is a different store, so the code is unique across stores.
It is stored trimmed and upper-cased, validated with one named pattern, and
checked in the CRUD forms and in the Sucursales upload, where it is the
store's key and is required on every row (`test_sucursal_clave_co.py`
covers renames). An Excel number never reaches the database as a
number.
"""
import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import settings
from app.main import app
from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import (
    CODIGO_CO_PATRON,
    SucursalCreate,
    SucursalRead,
    SucursalUpdate,
)
from app.motored.services import maestros, salud
from app.motored.services.sucursal_grupo import FILA_SUCURSAL_ID
from app.motored.services.carga_excel import column_labels, parse_excel_rows
from app.motored.services.validators import validate_rows
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession,
    override_motored_db,
    override_motored_user,
)

USER_ID = uuid.uuid4()
CALI_ID = uuid.uuid4()
SUCURSALES_URL = "/api/motored/maestros/sucursales"


def _xlsx(*rows):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _sucursal(nombre="CALI", codigo_co=None, activa=True, sic="S1"):
    return Sucursal(
        id=uuid.uuid4(), nombre=nombre, codigo_co=codigo_co,
        activa=activa, sic=sic,
    )


def _motivos(errores):
    return [(e["fila"], e["motivo"]) for e in errores]


class TestFormat:
    @pytest.mark.parametrize(
        "valor, esperado",
        [("E05", "E05"), (" c06 ", "C06"), ("a16", "A16"), ("B08", "B08")],
    )
    def test_valid_codes_are_trimmed_and_upper_cased(self, valor, esperado):
        assert SucursalCreate(nombre="X", codigo_co=valor).codigo_co == (
            esperado
        )
        assert SucursalUpdate(codigo_co=valor).codigo_co == esperado

    @pytest.mark.parametrize(
        "valor", ["E5", "E055", "05E", "EE5", "123", "E-05", 5]
    )
    def test_invalid_codes_are_rejected(self, valor):
        with pytest.raises(ValidationError, match="Código C.O."):
            SucursalCreate(nombre="X", codigo_co=valor)

    @pytest.mark.parametrize("valor", [None, "", "   "])
    def test_blank_is_no_code(self, valor):
        assert SucursalCreate(nombre="X", codigo_co=valor).codigo_co is None

    def test_the_rule_is_one_named_pattern(self):
        assert CODIGO_CO_PATRON.pattern == r"^[A-Z][0-9]{2}$"

    def test_read_schema_returns_the_code(self):
        leida = SucursalRead.model_validate(
            Sucursal(
                id=uuid.uuid4(), nombre="CALI", codigo_co="E05",
                activa=True, dias_seguridad=2.5,
            )
        )

        assert leida.codigo_co == "E05"


class TestColumn:
    def test_template_puts_the_column_first_before_the_name(self):
        assert column_labels("sucursal")[:2] == ["Código C.O.", "Nombre"]

    @pytest.mark.parametrize(
        "header",
        [
            "Código C.O.", "Codigo CO", "C.O.", "CO",
            "Centro de operación",
        ],
    )
    def test_aliases(self, header):
        filas = parse_excel_rows(
            "sucursal", "s.xlsx", _xlsx(["Nombre", header], ["A", "e05"])
        )

        assert filas[0]["codigo_co"] == "e05"

    def test_parser_keeps_the_code_as_text(self):
        filas = parse_excel_rows(
            "sucursal", "s.xlsx",
            _xlsx(["Nombre", "C.O."], ["A", "E05"], ["B", 5], ["C", None]),
        )

        assert [f["codigo_co"] for f in filas] == ["E05", "5", ""]


class TestRowValidation:
    def test_valid_code_is_normalized(self):
        validas, errores = validate_rows(
            "sucursal", [{"nombre": "CALI", "codigo_co": " e05 "}]
        )

        assert errores == []
        assert validas[0]["codigo_co"] == "E05"

    def test_invalid_code_is_a_row_error_naming_the_column(self):
        _, errores = validate_rows(
            "sucursal",
            [{"nombre": "CALI", "codigo_co": "E05"},
             {"nombre": "PASTO", "codigo_co": "5"}],
        )

        assert [e["fila"] for e in errores] == [2]
        assert "Código C.O." in errores[0]["motivo"]
        assert "'5'" in errores[0]["motivo"]

    def test_blank_cell_is_not_provided(self):
        validas, errores = validate_rows(
            "sucursal", [{"nombre": "CALI", "codigo_co": "  "}]
        )

        assert errores == []
        assert "codigo_co" not in validas[0]


class TestUploadUniqueness:
    async def test_without_codes_nothing_is_queried(self):
        db = FakeAsyncSession(execute_queue=[])

        _, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "A"}, {"nombre": "B", "codigo_co": " "}]
        )

        assert [e["fila"] for e in errores] == [1, 2]
        assert all("obligatorio" in e["motivo"] for e in errores)

    async def test_duplicate_in_the_file_is_an_error_on_both_rows(self):
        db = FakeAsyncSession(execute_queue=[[]])

        _, errores = await maestros.resolver_sucursales_carga(
            db,
            [{"nombre": "A", "codigo_co": "E05"},
             {"nombre": "B", "codigo_co": "C06"},
             {"nombre": "C", "codigo_co": " e05"}],
        )

        assert [e["fila"] for e in errores] == [1, 3]
        assert all("'E05'" in e["motivo"] for e in errores)
        assert all("filas 1 y 3" in e["motivo"] for e in errores)

    async def test_code_of_a_saved_store_matches_that_store(self):
        db = FakeAsyncSession(
            execute_queue=[[(CALI_ID, "CALI NORTE", "E05")]]
        )

        filas, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "PASTO", "codigo_co": "E05"}]
        )

        assert errores == []
        assert filas[0][FILA_SUCURSAL_ID] == CALI_ID

    async def test_same_store_keeping_its_code_is_fine(self):
        db = FakeAsyncSession(execute_queue=[[(CALI_ID, "CALI", "E05")]])

        filas, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": " CALI ", "codigo_co": "E05"}]
        )

        assert errores == []
        assert filas[0][FILA_SUCURSAL_ID] == CALI_ID

    async def test_two_stores_can_swap_names_in_one_file(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        db = FakeAsyncSession(
            execute_queue=[[(a, "A", "E05"), (b, "B", "C06")]]
        )

        _, errores = await maestros.resolver_sucursales_carga(
            db,
            [{"nombre": "A", "codigo_co": "C06"},
             {"nombre": "B", "codigo_co": "E05"}],
        )

        assert errores == []

    async def test_invalid_format_is_left_to_row_validation(self):
        db = FakeAsyncSession(execute_queue=[])

        _, errores = await maestros.resolver_sucursales_carga(
            db, [{"nombre": "A", "codigo_co": "5"}]
        )

        assert errores == []


class TestUpload:
    async def test_blank_cell_rejects_the_file(self):
        existente = _sucursal(codigo_co="E05")
        db = FakeAsyncSession(execute_queue=[])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "CALI", "codigo_co": "", "ciudad": "Cali"}],
            USER_ID,
        )

        assert resultado.ok is False
        assert "obligatorio" in resultado.errores[0].motivo
        assert existente.codigo_co == "E05"

    async def test_a_name_taken_by_another_store_rejects_the_file(self):
        db = FakeAsyncSession(execute_queue=[[
            (CALI_ID, "CALI NORTE", "E05"), (uuid.uuid4(), "PASTO", "C06"),
        ]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "PASTO", "codigo_co": "E05"}], USER_ID,
        )

        assert resultado.ok is False
        assert "'C06'" in resultado.errores[0].motivo
        assert db.committed is False


class TestCrud:
    async def test_create_stores_the_normalized_code(self):
        db = FakeAsyncSession(execute_queue=[[]])

        creada = await maestros.create_sucursal(
            db, SucursalCreate(nombre="CALI", codigo_co=" e05 "), USER_ID
        )

        assert creada.codigo_co == "E05"

    async def test_create_with_a_used_code_names_the_other_store(self):
        db = FakeAsyncSession(execute_queue=[[(CALI_ID, "CALI NORTE")]])

        with pytest.raises(maestros.CodigoCoEnUsoError) as exc:
            await maestros.create_sucursal(
                db, SucursalCreate(nombre="PASTO", codigo_co="E05"), USER_ID
            )

        assert str(exc.value) == (
            "El Código C.O. 'E05' ya es de la sucursal 'CALI NORTE'. "
            "Cada C.O. es una tienda distinta."
        )
        assert db.added == []

    async def test_create_without_a_code_never_queries(self):
        db = FakeAsyncSession(execute_queue=[])

        with pytest.raises(maestros.CodigoCoRequeridoError):
            await maestros.create_sucursal(
                db, SucursalCreate(nombre="CALI"), USER_ID
            )

        assert db.added == []

    async def test_update_to_a_used_code_is_rejected(self):
        sucursal = _sucursal(nombre="PASTO")
        db = FakeAsyncSession(execute_queue=[[(CALI_ID, "CALI NORTE")]])

        with pytest.raises(maestros.CodigoCoEnUsoError, match="CALI NORTE"):
            await maestros.update_sucursal(
                db, sucursal, SucursalUpdate(codigo_co="E05"), USER_ID
            )

        assert sucursal.codigo_co is None

    async def test_update_with_the_same_code_skips_the_query(self):
        sucursal = _sucursal(codigo_co="E05")
        db = FakeAsyncSession(execute_queue=[])

        await maestros.update_sucursal(
            db, sucursal, SucursalUpdate(codigo_co="e05"), USER_ID
        )

        assert sucursal.codigo_co == "E05"

    async def test_update_to_a_free_code_is_saved(self):
        sucursal = _sucursal(codigo_co="E05")
        db = FakeAsyncSession(execute_queue=[[]])

        await maestros.update_sucursal(
            db, sucursal, SucursalUpdate(codigo_co="C06"), USER_ID
        )

        assert sucursal.codigo_co == "C06"

    async def test_explicit_null_cannot_clear_the_code(self):
        sucursal = _sucursal(codigo_co="E05")
        db = FakeAsyncSession(execute_queue=[])

        with pytest.raises(maestros.CodigoCoRequeridoError):
            await maestros.update_sucursal(
                db, sucursal, SucursalUpdate(codigo_co=None), USER_ID
            )

        assert sucursal.codigo_co == "E05"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "co-test-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "co-test-asc360")
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN")
    )
    yield
    app.dependency_overrides.clear()


class TestCrudApi:
    def test_invalid_format_is_a_422_with_the_rule(self, api):
        override_motored_db(FakeAsyncSession(execute_queue=[[]]))

        with TestClient(app) as client:
            response = client.post(
                SUCURSALES_URL, json={"nombre": "CALI", "codigo_co": "5"}
            )

        assert response.status_code == 422
        assert "Código C.O." in str(response.json()["detail"])

    def test_used_code_is_a_422_naming_the_store(self, api):
        session = FakeAsyncSession(
            execute_queue=[[], [(CALI_ID, "CALI NORTE")]]
        )
        override_motored_db(session)

        with TestClient(app) as client:
            response = client.post(
                SUCURSALES_URL, json={"nombre": "PASTO", "codigo_co": "E05"}
            )

        assert response.status_code == 422
        assert "'CALI NORTE'" in response.json()["detail"]
        assert session.committed is False

    def test_create_returns_the_code(self, api):
        override_motored_db(FakeAsyncSession(execute_queue=[[], []]))

        with TestClient(app) as client:
            response = client.post(
                SUCURSALES_URL, json={"nombre": "CALI", "codigo_co": "e05"}
            )

        assert response.status_code == 201
        assert response.json()["codigo_co"] == "E05"


def _avisos_co(resultado):
    return [
        h for h in resultado.hallazgos if h.tipo == "sucursal_sin_codigo_co"
    ]


class TestHealth:
    async def test_a_missing_code_is_no_longer_a_health_check(self):
        """The column is NOT NULL (migration c6e1f8a2d953): a store
        always has its code, so the health board never checks it."""
        db = FakeAsyncSession(execute_queue=[[
            _sucursal(nombre="CALI"),
            _sucursal(nombre="PASTO", codigo_co="E05"),
        ], [], [], []])

        resultado = await salud.evaluar_salud(db)

        assert _avisos_co(resultado) == []
        assert resultado.estado == "verde"
