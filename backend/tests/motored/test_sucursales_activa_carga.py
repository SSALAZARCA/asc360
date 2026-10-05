"""
Sucursales upload: the strict "Activa" column.

Closed stores must load as inactive in the same file. The column only takes
yes/no words (case- and accent-insensitive); any other text is a row error
that names the column, never a silent False. A blank cell keeps the stored
value, and a new store without a value is created active. Changing the flag
through the upload leaves the same audit trail as the deactivate/reactivate
buttons.
"""
import io
import uuid

import openpyxl
import pytest

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.sucursal import SucursalCreate
from app.motored.services import maestros
from app.motored.services.carga_excel import column_labels, parse_excel_rows
from app.motored.services.validators import validate_rows
from tests.motored.conftest import FakeAsyncSession

USER_ID = uuid.uuid4()
SI = ["Sí", "si", "SI", "s", "Yes", "y", "TRUE", "1", "x", " Sí "]
NO = ["No", "no", "N", "n", "False", "0", "NÓ"]


def _xlsx(*rows):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _sucursal(activa=True):
    return Sucursal(
        id=uuid.uuid4(), nombre="CALI", bodega_principal="BA061",
        activa=activa,
    )


def _auditorias(db):
    return [
        (a.accion, a.campo) for a in db.added_of_type(AuditoriaMaestro)
    ]


class TestColumn:
    def test_template_and_parser_know_the_column(self):
        assert "Activa" in column_labels("sucursal")

    def test_parser_keeps_the_raw_text_for_strict_validation(self):
        content = _xlsx(
            ["Nombre", "Activa"], ["A", "Sí"], ["B", "tal vez"],
            ["C", None], ["D", 1], ["E", True],
        )

        filas = parse_excel_rows("sucursal", "s.xlsx", content)

        assert [f["activa"] for f in filas] == [
            "Sí", "tal vez", "", "1", "True",
        ]

    @pytest.mark.parametrize("header", ["Activo", "estado activa"])
    def test_aliases(self, header):
        filas = parse_excel_rows(
            "sucursal", "s.xlsx", _xlsx(["Nombre", header], ["A", "No"])
        )

        assert filas[0]["activa"] == "No"


class TestValidation:
    @pytest.mark.parametrize("valor", SI)
    def test_yes_words_are_true(self, valor):
        validas, errores = validate_rows(
            "sucursal", [{"nombre": "A", "activa": valor}]
        )

        assert errores == []
        assert validas[0]["activa"] is True

    @pytest.mark.parametrize("valor", NO)
    def test_no_words_are_false(self, valor):
        validas, errores = validate_rows(
            "sucursal", [{"nombre": "A", "activa": valor}]
        )

        assert errores == []
        assert validas[0]["activa"] is False

    @pytest.mark.parametrize("valor", [True, False])
    def test_a_json_boolean_passes_through(self, valor):
        validas, _ = validate_rows(
            "sucursal", [{"nombre": "A", "activa": valor}]
        )

        assert validas[0]["activa"] is valor

    @pytest.mark.parametrize("valor", ["tal vez", "cerrada", "2", "sii"])
    def test_any_other_text_is_a_row_error_naming_the_column(self, valor):
        validas, errores = validate_rows(
            "sucursal",
            [
                {"nombre": "A", "activa": "Sí"},
                {"nombre": "B", "activa": valor},
            ],
        )

        assert len(validas) == 1
        assert [e["fila"] for e in errores] == [2]
        assert "Activa" in errores[0]["motivo"]
        assert valor in errores[0]["motivo"]

    def test_blank_cell_means_not_provided(self):
        validas, errores = validate_rows(
            "sucursal", [{"nombre": "A", "activa": "  "}]
        )

        assert errores == []
        assert "activa" not in validas[0]


class TestService:
    async def test_new_store_defaults_to_active(self):
        db = FakeAsyncSession(execute_queue=[[]])

        sucursal, _, _ = await maestros.upsert_sucursal(
            db, SucursalCreate(nombre="CALI")
        )

        assert sucursal.activa is True

    async def test_new_store_can_be_created_inactive(self):
        db = FakeAsyncSession(execute_queue=[[]])

        sucursal, _, _ = await maestros.upsert_sucursal(
            db, SucursalCreate(nombre="CALI", activa=False), USER_ID
        )

        assert sucursal.activa is False
        assert _auditorias(db) == [("create", None), ("deactivate", "activa")]

    async def test_upsert_deactivates_with_the_deactivate_audit(self):
        existente = _sucursal(activa=True)
        db = FakeAsyncSession(execute_queue=[[existente]])

        await maestros.upsert_sucursal(
            db, SucursalCreate(nombre="CALI", activa=False), USER_ID
        )

        assert existente.activa is False
        assert _auditorias(db) == [("deactivate", "activa")]

    async def test_upsert_reactivates_with_the_reactivate_audit(self):
        existente = _sucursal(activa=False)
        db = FakeAsyncSession(execute_queue=[[existente]])

        await maestros.upsert_sucursal(
            db, SucursalCreate(nombre="CALI", activa=True), USER_ID
        )

        assert existente.activa is True
        assert _auditorias(db) == [("reactivate", "activa")]

    async def test_unchanged_flag_writes_no_audit(self):
        existente = _sucursal(activa=False)
        db = FakeAsyncSession(execute_queue=[[existente]])

        await maestros.upsert_sucursal(
            db, SucursalCreate(nombre="CALI", activa=False), USER_ID
        )

        assert existente.activa is False
        assert _auditorias(db) == []

    async def test_unset_flag_keeps_the_stored_value(self):
        existente = _sucursal(activa=False)
        db = FakeAsyncSession(execute_queue=[[existente]])

        await maestros.upsert_sucursal(
            db, SucursalCreate(nombre="CALI", ciudad="Cali"), USER_ID
        )

        assert existente.activa is False


class TestUpload:
    async def test_upload_deactivates_an_existing_store(self):
        existente = _sucursal(activa=True)
        db = FakeAsyncSession(execute_queue=[[existente]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [{"nombre": "CALI", "activa": "No"}], USER_ID
        )

        assert resultado.ok is True
        assert existente.activa is False
        assert db.committed is True

    async def test_blank_cell_keeps_an_inactive_store_inactive(self):
        existente = _sucursal(activa=False)
        db = FakeAsyncSession(execute_queue=[[existente]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "CALI", "activa": "", "ciudad": "Cali"}], USER_ID,
        )

        assert resultado.ok is True
        assert existente.activa is False

    async def test_unknown_text_rejects_the_whole_file(self):
        db = FakeAsyncSession(execute_queue=[])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "CALI", "activa": "No"},
             {"nombre": "PASTO", "activa": "cerrada"}],
            USER_ID,
        )

        assert resultado.ok is False
        assert [e.fila for e in resultado.errores] == [2]
        assert "Activa" in resultado.errores[0].motivo
        assert db.added == []
        assert db.committed is False
