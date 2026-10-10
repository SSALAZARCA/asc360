"""
Referencias: download the master as Excel
(`odd/tasks/motored-referencias-descarga-excel.md`, T1).

`GET /maestros/referencias/exportar.xlsx` returns the whole master (or
only what matches the same filters as `/buscar`) in the upload template's
layout plus a trailing "Estado" column, so the owner can edit the file and
re-upload it with the existing bulk load.

Same fake-session approach as `test_referencias_busqueda.py`: the first
queue slot is `get_motored_db_or_503`'s `SELECT 1` probe.
"""
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.api import referencias_busqueda as api_busqueda
from app.motored.services import referencias_excel
from app.motored.services.auth import MotoredUser
from app.motored.services.carga import _row_to_schema
from app.motored.services.carga_excel import column_labels, parse_excel_rows
from app.motored.services.reloj import hoy_bogota
from app.motored.services.validators import validate_rows
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

BASE = "/api/motored/maestros/referencias"
EXPORT = f"{BASE}/exportar.xlsx"
PROVEEDOR_ID = uuid.uuid4()
LABELS = [
    "Código", "Código del proveedor", "Nombre", "Línea comercial",
    "Unidad de empaque", "Precio Normal antes de IVA",
    "Precio Público antes de IVA", "Código de referencia sustituta",
    "Homologados otras marcas", "Estado",
]


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(
        settings, "MOTORED_SECRET_KEY", "referencias-excel-test-motored")
    monkeypatch.setattr(
        settings, "SECRET_KEY", "referencias-excel-test-asc360")
    monkeypatch.setattr(
        api_busqueda, "hoy_bogota", lambda: date(2026, 10, 10))
    # A fixed "today" for the endpoint; `nombre_archivo` takes the day.
    yield
    app.dependency_overrides.clear()


def _fila(codigo, **extra):
    """One export row, in the query's column order."""
    valores = dict(
        codigo=codigo, proveedor_codigo="HMCL", nombre=f"Nombre {codigo}",
        linea_comercial="REPUESTOS", unidad_empaque=1,
        precio_normal=None, precio_publico=None, sustituta_codigo=None,
        homologados=[], activa=True,
    )
    valores.update(extra)
    return tuple(valores.values())


def _client(execute_queue, role="COMPRAS"):
    session = FakeAsyncSession(execute_queue=[[], *execute_queue])
    override_motored_user(
        MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(session)
    return TestClient(app), session


def _sql(stmt) -> str:
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return " ".join(str(compiled).split())


def _business_sql(session) -> list:
    return [_sql(stmt) for stmt in session.executed_statements[1:]]


def _hoja(contenido: bytes):
    libro = openpyxl.load_workbook(io.BytesIO(contenido))
    return libro.active


def _valores(contenido: bytes) -> list:
    return [list(fila) for fila in _hoja(contenido).iter_rows(
        values_only=True)]


# --- layout ------------------------------------------------------------------


class TestLayout:
    def test_headers_are_the_upload_template_plus_estado_in_order(self):
        client, _ = _client([[]])

        response = client.get(EXPORT)

        assert response.status_code == 200
        assert _valores(response.content)[0] == LABELS

    def test_headers_follow_the_upload_parser_labels(self):
        assert referencias_excel.COLUMNAS == (
            *column_labels("referencia"), "Estado")

    def test_each_row_carries_the_values_in_the_header_order(self):
        fila = _fila(
            "A-1", precio_normal=Decimal("12345.67"),
            precio_publico=Decimal("15000.00"), unidad_empaque=4,
            sustituta_codigo="A-0", homologados=["FZ 150", "CB 190R"],
            activa=False)
        client, _ = _client([[fila]])

        datos = _valores(client.get(EXPORT).content)[1]

        assert datos == [
            "A-1", "HMCL", "Nombre A-1", "REPUESTOS", 4, 12345.67, 15000,
            "A-0", "FZ 150, CB 190R", "Inactiva"]

    def test_blank_values_stay_blank_and_active_reads_activa(self):
        fila = _fila("B-1", nombre=None, linea_comercial=None)
        client, _ = _client([[fila]])

        datos = _valores(client.get(EXPORT).content)[1]

        assert datos == [
            "B-1", "HMCL", None, None, 1, None, None, None, None, "Activa"]

    def test_codes_are_text_cells_and_prices_have_a_number_format(self):
        fila = _fila("00123", precio_normal=Decimal("10"))
        client, _ = _client([[fila]])

        hoja = _hoja(client.get(EXPORT).content)

        assert hoja["A2"].value == "00123"
        assert hoja["A2"].number_format == "@"
        assert hoja["F2"].number_format == referencias_excel.FORMATO_PRECIO


# --- file and response -------------------------------------------------------


class TestArchivo:
    def test_is_an_xlsx_attachment_named_with_the_bogota_date(self):
        client, _ = _client([[]])

        response = client.get(EXPORT)

        assert response.headers["content-type"] == referencias_excel.XLSX
        disposicion = response.headers["content-disposition"]
        assert disposicion.startswith("attachment;")
        assert 'filename="referencias_2026-10-10.xlsx"' in disposicion

    def test_file_name_uses_the_bogota_day_not_utc(self):
        # 03:00 UTC on Oct 11 is still Oct 10 in Bogotá (UTC-5).
        instante = datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)

        nombre = referencias_excel.nombre_archivo(hoy_bogota(instante))

        assert nombre == "referencias_2026-10-10.xlsx"


# --- filters: identical to /buscar -------------------------------------------


def _where(sql: str) -> str:
    return sql.split(" WHERE ", 1)[1].split(" ORDER BY", 1)[0]


class TestFiltros:
    PARAMS = {
        "q": " filtro ", "linea_comercial": "REPUESTOS",
        "activa": "false", "proveedor_id": str(PROVEEDOR_ID),
    }

    def test_applies_the_same_where_clause_as_buscar(self):
        client, session = _client([[]])
        client.get(EXPORT, params=self.PARAMS)
        (export_sql,) = _business_sql(session)

        client, session = _client([[0], []])
        client.get(f"{BASE}/buscar", params=self.PARAMS)
        buscar_page_sql = _business_sql(session)[1]

        assert _where(export_sql) == _where(buscar_page_sql)

    def test_without_filters_exports_the_whole_master_in_one_query(self):
        client, session = _client([[]])

        client.get(EXPORT)

        (sql,) = _business_sql(session)
        assert " WHERE " not in sql
        assert "LIMIT" not in sql
        assert "OFFSET" not in sql

    def test_resolves_proveedor_and_sustituta_in_the_same_query(self):
        client, session = _client([[]])

        client.get(EXPORT)

        (sql,) = _business_sql(session)
        assert "JOIN proveedor" in sql
        assert "LEFT OUTER JOIN referencia AS" in sql
        assert "ORDER BY referencia.codigo, referencia.id" in sql

    @pytest.mark.parametrize("params", [
        {"activa": "quizas"}, {"proveedor_id": "no-es-uuid"}])
    def test_rejects_invalid_filters_like_buscar(self, params):
        client, _ = _client([])

        assert client.get(EXPORT, params=params).status_code == 422


# --- permissions: same read gate as /buscar ----------------------------------


class TestPermisos:
    @pytest.mark.parametrize(
        "role", ["ADMIN", "COMPRAS", "CONSULTA", "SUCURSAL"])
    def test_every_role_that_can_search_can_export(self, role):
        client, _ = _client([[]], role=role)

        assert client.get(EXPORT).status_code == 200

    def test_requires_an_authenticated_motored_user(self):
        override_motored_db(FakeAsyncSession(execute_queue=[[]]))

        assert TestClient(app).get(EXPORT).status_code == 401

    def test_is_not_swallowed_by_the_generic_get_by_id_route(self):
        """The generic `/maestros/{entidad}/{entity_id}` would answer 422
        ("exportar.xlsx" is not a uuid) if it matched first."""
        client, _ = _client([[]])

        response = client.get(EXPORT)

        assert response.status_code == 200
        assert response.headers["content-type"] == referencias_excel.XLSX


# --- round trip through the upload parser ------------------------------------


def _como_carga(filas: list) -> list:
    """What `api/carga.py` adds before validating: the proveedor id. The
    sustituta code is resolved there too, so it is dropped here."""
    resultado = []
    for fila in filas:
        fila = dict(fila)
        fila.pop("sustituida_por_codigo")
        fila["proveedor_id"] = str(PROVEEDOR_ID)
        resultado.append(fila)
    return resultado


class TestIdaYVuelta:
    def test_reuploading_the_download_unchanged_reads_the_same_values(self):
        filas = [
            _fila("00123", precio_normal=Decimal("12345.67"),
                  precio_publico=Decimal("15000.00"), unidad_empaque=6,
                  sustituta_codigo="00122", homologados=["FZ 150", "NS 200"],
                  activa=False),
            _fila("98765", nombre=None, linea_comercial=None),
        ]
        contenido = referencias_excel.libro(filas)

        parseadas = parse_excel_rows("referencia", "r.xlsx", contenido)

        assert [f["codigo"] for f in parseadas] == ["00123", "98765"]
        assert [f["proveedor_codigo"] for f in parseadas] == ["HMCL"] * 2
        assert parseadas[0]["sustituida_por_codigo"] == "00122"
        assert "estado" not in parseadas[0]
        validas, errores = validate_rows("referencia", _como_carga(parseadas))
        assert errores == []
        # What the upsert persists: the schema built from each valid row.
        primera, segunda = (
            _row_to_schema("referencia", fila).model_dump(exclude_unset=True)
            for fila in validas)
        assert primera["precio_normal"] == Decimal("12345.67")
        assert primera["precio_publico"] == Decimal("15000.00")
        assert primera["unidad_empaque"] == 6
        assert primera["nombre"] == "Nombre 00123"
        assert primera["homologados"] == ["FZ 150", "NS 200"]
        for vacio in ("nombre", "linea_comercial", "precio_normal",
                      "precio_publico", "homologados"):
            assert vacio not in segunda
