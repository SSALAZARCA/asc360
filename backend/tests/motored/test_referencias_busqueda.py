"""
Referencias: server-side pagination, search and filters
(`odd/tasks/motored-referencias-paginacion.md`, T1).

`GET /maestros/referencias` (the generic `list_maestro`) keeps returning the
full unpaginated list for backward compatibility. The Referencias tab moves
to three dedicated read endpoints:

- `GET /maestros/referencias/buscar`: `{items, total, page, page_size}`,
  one COUNT plus one page query, filtered in SQL (never in memory).
- `GET /maestros/referencias/lineas-comerciales`: distinct non-empty values.
- `GET /maestros/referencias/sustitutas`: type-ahead for the sustituta
  picker (same proveedor, excluding the row itself, at most 20 results).

Same fake-session approach as `test_sucursal_scoping.py`: the first queue
slot is `get_motored_db_or_503`'s `SELECT 1` probe. SQL shape is asserted by
compiling the captured statements with the Postgres dialect.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.main import app
from app.motored.models.referencia import Referencia
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

BASE = "/api/motored/maestros/referencias"
PROVEEDOR_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "referencias-busqueda-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "referencias-busqueda-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _referencia(codigo, **extra):
    fields = dict(
        id=uuid.uuid4(), codigo=codigo, proveedor_id=PROVEEDOR_ID, unidad_empaque=1,
        unidad_empaque_advertencia=False, activa=True, homologados=[],
    )
    fields.update(extra)
    return Referencia(**fields)


def _client(execute_queue, role="COMPRAS"):
    session = FakeAsyncSession(execute_queue=[[], *execute_queue])
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))
    override_motored_db(session)
    return TestClient(app), session


def _sql(stmt) -> str:
    compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return " ".join(str(compiled).split())


def _business_sql(session) -> list:
    """Every statement after the `SELECT 1` probe, compiled."""
    return [_sql(stmt) for stmt in session.executed_statements[1:]]


def _like_patterns(session) -> list:
    """Bound ILIKE patterns of each business statement (literal rendering
    would double the `%` signs, so the raw bind values are compared)."""
    patrones = []
    for stmt in session.executed_statements[1:]:
        params = stmt.compile(dialect=postgresql.dialect()).params
        patrones.append(sorted(v for k, v in params.items() if k.startswith(("codigo_", "nombre_"))))
    return patrones


# --- /buscar: envelope, defaults, paging -----------------------------------


class TestBuscarPaginado:
    def test_default_page_returns_the_envelope_with_items_and_total(self):
        rows = [(_referencia("A-1"), None), (_referencia("A-2"), "A-1")]
        client, _ = _client([[137], rows])

        response = client.get(f"{BASE}/buscar")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 137
        assert body["page"] == 1
        assert body["page_size"] == 50
        assert [item["codigo"] for item in body["items"]] == ["A-1", "A-2"]

    def test_each_item_carries_the_sustituta_codigo_resolved_in_the_same_query(self):
        client, _ = _client([[1], [(_referencia("NUEVA", sustituida_por=uuid.uuid4()), "VIEJA")]])

        item = client.get(f"{BASE}/buscar").json()["items"][0]

        assert item["sustituta_codigo"] == "VIEJA"
        assert item["homologados"] == []

    def test_issues_exactly_one_count_and_one_page_query(self):
        client, session = _client([[0], []])

        client.get(f"{BASE}/buscar")

        count_sql, page_sql = _business_sql(session)
        assert "count(" in count_sql.lower()
        assert "LIMIT 50 OFFSET 0" in page_sql

    def test_orders_by_codigo_then_id_for_a_stable_order(self):
        client, session = _client([[0], []])

        client.get(f"{BASE}/buscar")

        page_sql = _business_sql(session)[1]
        assert "ORDER BY referencia.codigo, referencia.id" in page_sql

    def test_page_and_page_size_translate_to_limit_and_offset(self):
        client, session = _client([[0], []])

        response = client.get(f"{BASE}/buscar", params={"page": 3, "page_size": 20})

        assert response.json()["page"] == 3
        assert response.json()["page_size"] == 20
        assert "LIMIT 20 OFFSET 40" in _business_sql(session)[1]

    @pytest.mark.parametrize("params", [{"page_size": 201}, {"page_size": 0}, {"page": 0}])
    def test_rejects_out_of_range_paging(self, params):
        client, _ = _client([])

        assert client.get(f"{BASE}/buscar", params=params).status_code == 422

    def test_accepts_the_maximum_page_size(self):
        client, session = _client([[0], []])

        assert client.get(f"{BASE}/buscar", params={"page_size": 200}).status_code == 200
        assert "LIMIT 200" in _business_sql(session)[1]

    def test_is_not_swallowed_by_the_generic_get_by_id_route(self):
        client, _ = _client([[0], []])

        assert client.get(f"{BASE}/buscar").status_code == 200


# --- /buscar: filters are SQL, applied to BOTH queries ---------------------


class TestBuscarFiltros:
    def test_q_searches_codigo_or_nombre_case_insensitively_in_both_queries(self):
        client, session = _client([[0], []])

        client.get(f"{BASE}/buscar", params={"q": "  filtro "})

        for sql in _business_sql(session):
            assert "referencia.codigo ILIKE" in sql
            assert "referencia.nombre ILIKE" in sql
            assert " OR " in sql
        assert _like_patterns(session) == [["%filtro%", "%filtro%"]] * 2

    def test_q_escapes_like_wildcards_so_they_match_literally(self):
        client, session = _client([[0], []])

        client.get(f"{BASE}/buscar", params={"q": "50%_x"})

        assert _like_patterns(session)[0] == ["%50\\%\\_x%"] * 2
        assert "ESCAPE" in _business_sql(session)[0]

    def test_blank_q_adds_no_filter(self):
        client, session = _client([[0], []])

        client.get(f"{BASE}/buscar", params={"q": "   "})

        assert "ILIKE" not in _business_sql(session)[0]

    def test_linea_activa_and_proveedor_filters_apply_to_both_queries(self):
        client, session = _client([[0], []])

        client.get(
            f"{BASE}/buscar",
            params={"linea_comercial": "REPUESTOS", "activa": "false", "proveedor_id": str(PROVEEDOR_ID)},
        )

        for sql in _business_sql(session):
            assert "referencia.linea_comercial = 'REPUESTOS'" in sql
            assert "referencia.activa = false" in sql
            assert f"referencia.proveedor_id = '{PROVEEDOR_ID}'" in sql

    def test_without_filters_there_is_no_where_clause(self):
        client, session = _client([[0], []])

        client.get(f"{BASE}/buscar")

        assert "WHERE" not in _business_sql(session)[0]

    def test_returns_the_rows_the_query_returned_without_filtering_in_memory(self):
        inactiva = _referencia("B-1", activa=False)
        client, _ = _client([[1], [(inactiva, None)]])

        body = client.get(f"{BASE}/buscar", params={"activa": "true"}).json()

        assert [item["codigo"] for item in body["items"]] == ["B-1"]


# --- auth: same read gate as list_maestro -----------------------------------


class TestLecturaRoles:
    @pytest.mark.parametrize("role", ["ADMIN", "COMPRAS", "CONSULTA", "SUCURSAL"])
    def test_every_read_role_can_search(self, role):
        client, _ = _client([[0], []], role=role)

        assert client.get(f"{BASE}/buscar").status_code == 200

    @pytest.mark.parametrize("path", ["buscar", "lineas-comerciales", f"sustitutas?proveedor_id={PROVEEDOR_ID}"])
    def test_requires_an_authenticated_motored_user(self, path):
        override_motored_db(FakeAsyncSession(execute_queue=[[]]))

        assert TestClient(app).get(f"{BASE}/{path}").status_code == 401


# --- /lineas-comerciales ------------------------------------------------------


class TestLineasComerciales:
    def test_returns_the_distinct_values_from_the_query(self):
        client, _ = _client([["ACCESORIOS", "REPUESTOS"]])

        response = client.get(f"{BASE}/lineas-comerciales")

        assert response.status_code == 200
        assert response.json() == ["ACCESORIOS", "REPUESTOS"]

    def test_is_a_sorted_sql_distinct_that_skips_null_and_blank(self):
        client, session = _client([[]])

        client.get(f"{BASE}/lineas-comerciales")

        (sql,) = _business_sql(session)
        assert "SELECT DISTINCT referencia.linea_comercial" in sql
        assert "referencia.linea_comercial IS NOT NULL" in sql
        assert "referencia.linea_comercial != ''" in sql
        assert "ORDER BY referencia.linea_comercial" in sql


# --- /sustitutas --------------------------------------------------------------


class TestSustitutas:
    def test_returns_only_id_codigo_and_nombre(self):
        ref = _referencia("S-1", nombre="Sustituta")
        client, _ = _client([[ref]])

        response = client.get(f"{BASE}/sustitutas", params={"proveedor_id": str(PROVEEDOR_ID), "q": "S"})

        assert response.status_code == 200
        assert response.json() == [{"id": str(ref.id), "codigo": "S-1", "nombre": "Sustituta"}]

    def test_requires_proveedor_id(self):
        client, _ = _client([])

        assert client.get(f"{BASE}/sustitutas", params={"q": "S"}).status_code == 422

    def test_filters_same_proveedor_excludes_self_searches_and_caps_at_20(self):
        excluded = uuid.uuid4()
        client, session = _client([[]])

        client.get(
            f"{BASE}/sustitutas",
            params={"proveedor_id": str(PROVEEDOR_ID), "exclude_id": str(excluded), "q": "abc"},
        )

        (sql,) = _business_sql(session)
        assert f"referencia.proveedor_id = '{PROVEEDOR_ID}'" in sql
        assert f"referencia.id != '{excluded}'" in sql
        assert "referencia.codigo ILIKE" in sql
        assert _like_patterns(session) == [["%abc%", "%abc%"]]
        assert "ORDER BY referencia.codigo, referencia.id" in sql
        assert "LIMIT 20" in sql

    def test_without_exclude_id_or_q_only_the_proveedor_filter_applies(self):
        client, session = _client([[]])

        client.get(f"{BASE}/sustitutas", params={"proveedor_id": str(PROVEEDOR_ID)})

        (sql,) = _business_sql(session)
        assert "referencia.id !=" not in sql
        assert "ILIKE" not in sql


# --- backward compatibility ---------------------------------------------------


def test_generic_list_endpoint_still_returns_the_plain_unpaginated_list():
    client, _ = _client([[_referencia("A-1"), _referencia("A-2")]])

    body = client.get(BASE).json()

    assert isinstance(body, list)
    assert [item["codigo"] for item in body] == ["A-1", "A-2"]
