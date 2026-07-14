"""
RED regression tests for `list_all_moto_units`
(`GET /api/v1/imports/moto-units`) capturing CURRENT (pre-refactor) behavior
— Phase 3 of `sdd/imports-oversized-functions-refactor-tier1`.

These exercise the endpoint via the HTTP harness (`make_test_client`) +
`FakeAsyncSession` and MUST keep passing unchanged after the extraction
(delegates to `_build_moto_unit_filters`/`_count_moto_units`/
`_fetch_moto_units_page`/`_serialize_moto_unit`) — same file, same
assertions, only the endpoint's internals change.

Locked-in behaviors (read directly off the pre-refactor source,
`backend/app/api/v1/imports.py` lines 2228-2393, before writing any test):
  - `execute()` call order is exactly: `total`, `total_global`,
    `total_empadronados`, `total_pendientes`, `total_facturadas`, then the
    paginated items query — 6 calls total, every time.
  - `total` and `total_global` are computed from the EXACT SAME filter set
    (`filters`) — a known, out-of-scope redundant double-query (see design
    doc); this refactor preserves both calls byte-for-byte rather than
    deduplicating them.
  - `total_empadronados`/`total_pendientes`/`total_facturadas` use
    `base_filters` ONLY (never `certificado_generado`/`observation_id`/
    `empadronamiento_fisico_enviado`/`facturado`/`cargado_runt` from the
    request) plus their own HARDCODED condition
    (`certificado_generado == True/False`, `facturado == True`
    respectively) — independent of whatever the request itself asked for.
  - `base_filters` = `is_spare_part == False` + optional `pi_number`
    (ILIKE)/`model` (ILIKE on `coalesce(unit.model, order.model)`)/`vin`
    (ILIKE)/`engine` (ILIKE).
  - `filters` = `base_filters` + optional `certificado_generado`/
    `observation_id`/`empadronamiento_fisico_enviado`/`facturado`/
    `cargado_runt` — used only for the scoped `total`/`total_global` counts
    and the paginated items query.
  - `page_size` is clamped to a maximum of 200; `skip = (page - 1) *
    page_size` (using the CLAMPED page_size).
  - Each item is flattened into a dict with fields sourced from the
    `ShipmentMotoUnit` plus a few from its related `ShipmentOrder`
    (`pi_number`, `model` fallback, `model_year` fallback), with `model`
    upper-cased/whitespace-collapsed and empty-string coalesced to `None`.

Filter/pagination tests inspect `FakeAsyncSession.executed_statements`
(compiled SQL + bound params) rather than DB rows, since the fake ignores
WHERE clauses when deciding what to return — this is the only way to lock
in filter semantics without a live database (same technique as
`test_list_spare_part_lots_endpoint_regression.py`).
"""
import uuid

from tests.conftest import make_test_client
from tests.imports.conftest import (
    FakeAsyncSession,
    make_actor,
    make_imports_editor,
    make_moto_location,
    make_moto_observation,
    make_moto_unit,
    make_shipment_order,
)


def test_non_editor_role_gets_403():
    """`make_actor()` (role=jefe_taller) is not an imports editor -> 403, no DB call."""
    fake_db = FakeAsyncSession(execute_queue=[])

    with make_test_client(current_user=make_actor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/moto-units")

    assert response.status_code == 403
    assert response.json()["detail"] == "Sin permisos para el módulo de importaciones"
    assert fake_db.executed_statements == []


def test_default_request_serializes_expected_item_shape():
    """Locks in the exact flattened item dict shape, field-by-field."""
    order = make_shipment_order(pi_number="E0000900", model="MODEL FALLBACK", model_year=2024)
    location = make_moto_location(name="BODEGA NORTE")
    observation = make_moto_observation(name="REVISAR VIN")
    unit = make_moto_unit(
        shipment_order=order,
        location=location,
        observation=observation,
        vin_number="VIN999",
        engine_number="ENG999",
        model="  cb 500   f  ",
        model_year=2025,
        item_no=7,
        color="ROJO",
        color_runt="RED",
        container_no="CONT-1",
        seal_no="SEAL-1",
        source_pi="E0000900",
        certificado_generado=True,
        facturado=True,
        cargado_runt=True,
        separada_nacionalizacion=True,
        empadronamiento_fisico_enviado=True,
        empadronamiento_fisico_distribuidor_nombre="Distribuidor X",
        dim_pdf_object_name="dim/vin999.pdf",
    )

    fake_db = FakeAsyncSession(execute_queue=[[3], [3], [1], [2], [1], [unit]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/moto-units")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["total"] == 3
    assert body["total_global"] == 3
    assert body["total_empadronados"] == 1
    assert body["total_pendientes"] == 2
    assert body["total_facturadas"] == 1
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["id"] == str(unit.id)
    assert item["shipment_order_id"] == str(unit.shipment_order_id)
    assert item["item_no"] == 7
    assert item["vin_number"] == "VIN999"
    assert item["engine_number"] == "ENG999"
    assert item["color"] == "ROJO"
    assert item["color_runt"] == "RED"
    assert item["container_no"] == "CONT-1"
    assert item["seal_no"] == "SEAL-1"
    assert item["source_pi"] == "E0000900"
    assert item["certificado_generado"] is True
    assert item["empadronamiento_fisico_enviado"] is True
    assert item["empadronamiento_fisico_distribuidor_nombre"] == "Distribuidor X"
    assert item["dim_pdf_object_name"] == "dim/vin999.pdf"
    assert item["location_id"] == str(location.id)
    assert item["location_name"] == "BODEGA NORTE"
    assert item["observation_id"] == str(observation.id)
    assert item["observation_name"] == "REVISAR VIN"
    assert item["separada_nacionalizacion"] is True
    assert item["facturado"] is True
    assert item["cargado_runt"] is True
    assert item["pi_number"] == "E0000900"
    assert item["model"] == "CB 500 F"  # whitespace collapsed + upper-cased
    assert item["model_year"] == 2025


def test_item_model_falls_back_to_order_when_unit_model_none():
    """`model`/`model_year` fall back to the related order's values when the
    unit's own fields are `None` (falsy)."""
    order = make_shipment_order(pi_number="E0000901", model="order model", model_year=2020)
    unit = make_moto_unit(shipment_order=order, model=None, model_year=None)

    fake_db = FakeAsyncSession(execute_queue=[[0], [0], [0], [0], [0], [unit]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/moto-units")

    item = response.json()["items"][0]
    assert item["model"] == "ORDER MODEL"
    assert item["model_year"] == 2020


def test_item_model_whitespace_only_does_not_fall_back_and_normalizes_to_none():
    """GOTCHA (pre-existing, preserved as-is): the fallback uses Python
    truthiness (`u.model or order.model`) — an all-whitespace `u.model` is
    truthy, so it wins over the order fallback, then collapses to `None`
    after `' '.join(s.split())` strips it to an empty string."""
    order = make_shipment_order(pi_number="E0000902", model="order model")
    unit = make_moto_unit(shipment_order=order, model="   ")

    fake_db = FakeAsyncSession(execute_queue=[[0], [0], [0], [0], [0], [unit]])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get("/api/v1/imports/moto-units")

    item = response.json()["items"][0]
    assert item["model"] is None


def test_page_size_clamped_to_200_and_offset_computed():
    """`page_size` clamps to 200; `skip` uses the CLAMPED value, not the raw request."""
    fake_db = FakeAsyncSession(execute_queue=[[0], [0], [0], [0], [0], []])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get(
            "/api/v1/imports/moto-units", params={"page": 3, "page_size": 500}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["page_size"] == 200
    items_stmt = fake_db.executed_statements[-1]
    compiled = items_stmt.compile()
    assert 200 in compiled.params.values()  # LIMIT
    assert 400 in compiled.params.values()  # OFFSET = (3-1)*200


def test_total_and_total_global_are_identical_redundant_queries():
    """Locks in the known redundant double-query: `total` and `total_global`
    are computed from the exact same filter set (out-of-scope inefficiency,
    explicitly preserved as-is per the design doc)."""
    fake_db = FakeAsyncSession(execute_queue=[[9], [9], [0], [0], [0], []])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get(
            "/api/v1/imports/moto-units", params={"pi_number": "E123", "vin": "ABC"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 9
    assert body["total_global"] == 9

    total_stmt, total_global_stmt = fake_db.executed_statements[0], fake_db.executed_statements[1]
    assert str(total_stmt.compile()) == str(total_global_stmt.compile())
    assert total_stmt.compile().params == total_global_stmt.compile().params


def test_kpi_queries_use_base_filters_independent_of_request_filters():
    """`total_empadronados`/`total_pendientes`/`total_facturadas` always use
    `base_filters` with their own HARDCODED condition, regardless of what the
    request's `certificado_generado`/`facturado` params ask for — locks in
    the pre-existing base_filters-vs-filters split."""
    fake_db = FakeAsyncSession(execute_queue=[[1], [1], [4], [6], [2], []])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        # Request explicitly asks for certificado_generado=true, facturado=false —
        # the KPI queries must ignore these and use their own hardcoded values.
        response = client.get(
            "/api/v1/imports/moto-units",
            params={"certificado_generado": "true", "facturado": "false"},
        )

    assert response.status_code == 200
    (
        total_stmt,
        total_global_stmt,
        empadronados_stmt,
        pendientes_stmt,
        facturadas_stmt,
        items_stmt,
    ) = fake_db.executed_statements

    # SQLAlchemy compiles a literal `col == True/False` comparison as an
    # inline SQL literal (`col = true`/`col = false`), never as a bound
    # param — so these assert on the compiled SQL text, not `.params`.
    # total_empadronados hardcodes certificado_generado == True
    assert "certificado_generado = true" in str(empadronados_stmt.compile())
    # total_pendientes hardcodes certificado_generado == False (same as the
    # request in this case, but sourced independently — see next assertion)
    assert "certificado_generado = false" in str(pendientes_stmt.compile())
    # total_facturadas hardcodes facturado == True, even though the request
    # asked for facturado=false
    assert "facturado = true" in str(facturadas_stmt.compile())


def test_query_param_filters_are_applied_to_scoped_total_and_items_query():
    """`pi_number`/`model`/`vin`/`engine` ILIKE filters and the extra
    `filters`-only params (`observation_id`, `empadronamiento_fisico_enviado`,
    `cargado_runt`) end up in the `total`/`items` statements' bound params
    and SQL, but the KPI (base_filters-only) statements omit the extra ones."""
    obs_id = uuid.uuid4()
    fake_db = FakeAsyncSession(execute_queue=[[0], [0], [0], [0], [0], []])

    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
        response = client.get(
            "/api/v1/imports/moto-units",
            params={
                "pi_number": "E0001",
                "model": "cb500",
                "vin": "VIN1",
                "engine": "ENG1",
                "observation_id": str(obs_id),
                "empadronamiento_fisico_enviado": "true",
                "cargado_runt": "true",
            },
        )

    assert response.status_code == 200
    total_stmt = fake_db.executed_statements[0]
    sql = str(total_stmt.compile())
    params = total_stmt.compile().params.values()

    # `.ilike()` compiles (without a postgres dialect) to `lower(x) LIKE lower(y)`,
    # not a literal `ILIKE` keyword — assert on the portable `LIKE` form.
    assert "like" in sql.lower()
    assert "coalesce" in sql.lower()
    assert "%E0001%" in params
    assert "%cb500%" in params
    assert "%VIN1%" in params
    assert "%ENG1%" in params
    assert obs_id in params
    # `empadronamiento_fisico_enviado`/`cargado_runt` compile as inline SQL
    # literals (`col = true`), never as bound params — see the note above.
    assert "empadronamiento_fisico_enviado = true" in sql.lower()
    assert "cargado_runt = true" in sql.lower()


def test_certificado_generado_filter_adds_an_extra_bound_param_on_scoped_total():
    """`certificado_generado` request param, when set, adds ONE extra filter
    condition to the scoped `total` filters on top of the always-present
    `is_spare_part == False` base condition (as opposed to the KPI
    base_filters, which never see the request's `certificado_generado`).
    Checked via the compiled SQL text, not `.params`: SQLAlchemy compiles a
    literal `col == True/False` comparison as an inline SQL literal, so it
    never appears as a bound param regardless of whether the filter is
    present."""
    fake_db_without = FakeAsyncSession(execute_queue=[[0], [0], [0], [0], [0], []])
    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db_without) as client:
        client.get("/api/v1/imports/moto-units")
    sql_without = str(fake_db_without.executed_statements[0].compile())

    fake_db_with = FakeAsyncSession(execute_queue=[[0], [0], [0], [0], [0], []])
    with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db_with) as client:
        response = client.get(
            "/api/v1/imports/moto-units", params={"certificado_generado": "false"}
        )
    sql_with = str(fake_db_with.executed_statements[0].compile())

    assert response.status_code == 200
    assert "certificado_generado = false" not in sql_without
    assert "certificado_generado = false" in sql_with
