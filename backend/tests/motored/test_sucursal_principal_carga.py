"""
Sucursales upload: the "Sucursal principal" column.

The cell names the principal store BY NAME (same normalization as store
names), against existing stores and stores created in the same file. A
blank cell keeps the stored value; "Ninguna" (or "-") dissociates. The
depth-1 rules are checked on the state the whole file leaves together with
the database, and the file is rejected as a whole on any violation.
"""
import io
import uuid

import openpyxl
import pytest

from app.motored.api.carga import _resolver_y_procesar_carga
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.sucursal import Sucursal
from app.motored.services import sucursal_grupo
from app.motored.services.carga_excel import column_labels, parse_excel_rows
from tests.motored.conftest import FakeAsyncSession

USER_ID = uuid.uuid4()
LA33, EXPO1, CENTRO = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _xlsx(*rows):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _fila(nombre, principal):
    return {"nombre": nombre, "sucursal_principal": principal}


def _db_rows(*extra):
    """`(id, nombre, principal_id)` of the stores already saved."""
    return [
        (LA33, "MEDELLIN LA 33", None),
        (CENTRO, "CENTRO", None),
        *extra,
    ]


async def _resolver(filas, db_rows=None):
    db = FakeAsyncSession(
        execute_queue=[db_rows if db_rows is not None else _db_rows()]
    )
    return await sucursal_grupo.resolver_filas(db, filas)


def _motivos(errores):
    return [(e["fila"], e["motivo"]) for e in errores]


class TestColumn:
    def test_template_and_parser_know_the_column(self):
        assert "Sucursal principal" in column_labels("sucursal")

    @pytest.mark.parametrize(
        "header", ["Sucursal principal", "Tienda principal", "Principal"]
    )
    def test_aliases(self, header):
        filas = parse_excel_rows(
            "sucursal", "s.xlsx",
            _xlsx(["Nombre", header], ["EXPO 2", "Medellín la 33"]),
        )

        assert filas[0]["sucursal_principal"] == "Medellín la 33"


class TestResolver:
    async def test_without_the_column_nothing_is_queried(self):
        db = FakeAsyncSession(execute_queue=[])

        filas, errores = await sucursal_grupo.resolver_filas(
            db, [{"nombre": "A"}]
        )

        assert errores == []
        assert sucursal_grupo.FILA_CLAVE not in filas[0]

    async def test_blank_cell_keeps_the_stored_value(self):
        db = FakeAsyncSession(execute_queue=[])

        filas, errores = await sucursal_grupo.resolver_filas(
            db, [_fila("EXPO 2", "  ")]
        )

        assert errores == []
        assert sucursal_grupo.FILA_CLAVE not in filas[0]
        assert "sucursal_principal" not in filas[0]

    async def test_resolves_an_existing_store_by_normalized_name(self):
        filas, errores = await _resolver(
            [_fila("EXPO 2", "  medellín  la 33 ")]
        )

        assert errores == []
        pedida = filas[0][sucursal_grupo.FILA_CLAVE]
        assert pedida.sucursal_id == LA33

    @pytest.mark.parametrize("texto", ["Ninguna", "ninguna", "-"])
    async def test_ninguna_dissociates(self, texto):
        filas, errores = await _resolver([_fila("EXPO 2", texto)])

        assert errores == []
        assert filas[0][sucursal_grupo.FILA_CLAVE].clave is None

    async def test_unknown_name_is_a_row_error(self):
        _, errores = await _resolver([_fila("EXPO 2", "NO EXISTE")])

        assert errores[0]["fila"] == 1
        assert "'NO EXISTE'" in errores[0]["motivo"]
        assert "Sucursal principal" in errores[0]["motivo"]

    async def test_self_reference_is_a_row_error(self):
        _, errores = await _resolver([_fila("CENTRO", "centro")])

        assert "su propia tienda principal" in errores[0]["motivo"]

    async def test_principal_created_in_the_same_file(self):
        filas, errores = await _resolver(
            [_fila("EXPO 2", "NUEVA"), {"nombre": "NUEVA"}]
        )

        assert errores == []
        pedida = filas[0][sucursal_grupo.FILA_CLAVE]
        assert pedida.sucursal_id is None
        assert pedida.clave == "NUEVA"

    async def test_target_associated_in_the_database_is_rejected(self):
        db_rows = _db_rows((EXPO1, "EXPO 1", LA33))

        _, errores = await _resolver([_fila("EXPO 2", "EXPO 1")], db_rows)

        assert len(errores) == 1
        assert "'EXPO 1'" in errores[0]["motivo"]
        assert "MEDELLIN LA 33" in errores[0]["motivo"]

    async def test_store_with_associated_stores_in_db_is_rejected(self):
        db_rows = _db_rows((EXPO1, "EXPO 1", LA33))

        _, errores = await _resolver(
            [_fila("MEDELLIN LA 33", "CENTRO")], db_rows
        )

        assert len(errores) == 1
        assert "EXPO 1" in errores[0]["motivo"]

    async def test_chain_built_inside_the_file_is_rejected(self):
        _, errores = await _resolver(
            [_fila("EXPO 2", "EXPO 1"), _fila("EXPO 1", "MEDELLIN LA 33")]
        )

        # Both rows are part of the chain: 1 points at an associated
        # store, and 2 is associated while it already has an associate.
        assert [fila for fila, _ in _motivos(errores)] == [1, 2]

    async def test_clearing_in_the_same_file_allows_the_new_link(self):
        db_rows = _db_rows((EXPO1, "EXPO 1", LA33))

        _, errores = await _resolver(
            [_fila("EXPO 2", "EXPO 1"), _fila("EXPO 1", "Ninguna")],
            db_rows,
        )

        assert errores == []


class TestUpload:
    async def test_principal_created_later_in_the_file_is_linked(self):
        db = FakeAsyncSession(execute_queue=[_db_rows(), [], []])
        filas = [
            _fila("EXPO 2", "NUEVA"),
            {"nombre": "NUEVA", "sucursal_principal": ""},
        ]

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", filas, USER_ID
        )

        assert resultado.ok is True
        expo, nueva = db.added_of_type(Sucursal)
        assert expo.principal_id == nueva.id
        assert nueva.principal_id is None
        assert db.committed is True

    async def test_existing_store_is_associated_and_audited(self):
        expo = Sucursal(id=EXPO1, nombre="EXPO 1", activa=True)
        db = FakeAsyncSession(execute_queue=[_db_rows(), [expo]])

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("EXPO 1", "MEDELLIN LA 33")], USER_ID
        )

        assert resultado.ok is True
        assert expo.principal_id == LA33
        campos = [
            (a.campo, a.valor_nuevo)
            for a in db.added_of_type(AuditoriaMaestro)
        ]
        assert ("principal_id", str(LA33)) in campos

    async def test_ninguna_dissociates_an_existing_store(self):
        expo = Sucursal(
            id=EXPO1, nombre="EXPO 1", activa=True, principal_id=LA33
        )
        db = FakeAsyncSession(
            execute_queue=[_db_rows((EXPO1, "EXPO 1", LA33)), [expo]]
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal", [_fila("EXPO 1", "Ninguna")], USER_ID
        )

        assert resultado.ok is True
        assert expo.principal_id is None

    async def test_a_chain_rejects_the_whole_file(self):
        db = FakeAsyncSession(
            execute_queue=[_db_rows((EXPO1, "EXPO 1", LA33))]
        )

        resultado = await _resolver_y_procesar_carga(
            db, "sucursal",
            [{"nombre": "OTRA"}, _fila("EXPO 2", "EXPO 1")], USER_ID,
        )

        assert resultado.ok is False
        assert [e.fila for e in resultado.errores] == [2]
        assert db.added == []
        assert db.committed is False
