"""
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra" (sdd/motored-
pedidos-ingesta, task 3.4) — `services/ingesta/resolucion.py` (ADR-8).

`construir_cache` hace UN lote fijo de queries (sucursal, bodega,
sucursal_alias, referencia) y nunca más -- `resolver_sucursal`/
`resolver_referencia` son lookups puros en memoria después de eso (ADR-8:
"per-row DB lookups are forbidden"). Usa `FakeAsyncSession` de
`tests/motored/conftest.py`, mismo patrón que el resto de la suite (sin
Postgres real).
"""
import uuid

from tests.motored.conftest import FakeAsyncSession

from app.motored.models.bodega import Bodega
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.services.ingesta import resolucion


def _make_session(sucursales=(), bodegas=(), alias=(), referencias=()):
    return FakeAsyncSession(execute_queue=[list(sucursales), list(bodegas), list(alias), list(referencias)])


async def test_construir_cache_issues_exactly_four_queries():
    session = _make_session()

    await resolucion.construir_cache(session)

    assert len(session.executed_statements) == 4


async def test_resolver_sucursal_matches_by_trimmed_case_insensitive_name():
    sucursal_id = uuid.uuid4()
    session = _make_session(sucursales=[(sucursal_id, "Cali Norte")])

    cache = await resolucion.construir_cache(session)

    assert resolucion.resolver_sucursal(cache, "CALI NORTE   ") == sucursal_id


async def test_resolver_sucursal_falls_back_to_alias_when_no_direct_name_matches():
    sucursal_id = uuid.uuid4()
    session = _make_session(alias=[("BUCARAMANGA LA 27", sucursal_id)])

    cache = await resolucion.construir_cache(session)

    assert resolucion.resolver_sucursal(cache, "MR bucaramanga la 27  ") == sucursal_id


async def test_resolver_sucursal_returns_none_when_nothing_matches():
    session = _make_session()

    cache = await resolucion.construir_cache(session)

    assert resolucion.resolver_sucursal(cache, "no existe") is None


async def test_bodega_secundaria_resolves_to_bodega_principal_sucursal():
    # design scenario: BA066 reports stock, bodega_principal is BA061 ->
    # the consolidated row is keyed to BA061's sucursal.
    sucursal_ba061 = uuid.uuid4()
    session = _make_session(
        bodegas=[
            ("BA066", None, "BA061"),
            ("BA061", sucursal_ba061, None),
        ],
    )

    cache = await resolucion.construir_cache(session)

    assert resolucion.resolver_sucursal(cache, "BA066") == sucursal_ba061
    assert resolucion.resolver_sucursal(cache, "BA061") == sucursal_ba061


async def test_resolver_referencia_matches_by_codigo_and_proveedor():
    proveedor_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    session = _make_session(referencias=[("REF1", proveedor_id, referencia_id)])

    cache = await resolucion.construir_cache(session)

    assert resolucion.resolver_referencia(cache, "REF1", proveedor_id) == referencia_id


async def test_resolver_referencia_is_scoped_by_proveedor():
    referencia_id = uuid.uuid4()
    proveedor_a = uuid.uuid4()
    proveedor_b = uuid.uuid4()
    session = _make_session(referencias=[("REF1", proveedor_a, referencia_id)])

    cache = await resolucion.construir_cache(session)

    assert resolucion.resolver_referencia(cache, "REF1", proveedor_b) is None


async def test_resolvers_never_touch_the_session_after_cache_is_built():
    sucursal_id = uuid.uuid4()
    referencia_id = uuid.uuid4()
    proveedor_id = uuid.uuid4()
    session = _make_session(
        sucursales=[(sucursal_id, "Cali Norte")],
        referencias=[("REF1", proveedor_id, referencia_id)],
    )

    cache = await resolucion.construir_cache(session)
    queries_after_cache = len(session.executed_statements)

    for _ in range(500):
        resolucion.resolver_sucursal(cache, "Cali Norte")
        resolucion.resolver_referencia(cache, "REF1", proveedor_id)

    assert len(session.executed_statements) == queries_after_cache


def test_normalizar_texto_sucursal_strips_mr_prefix_accents_and_spaces():
    assert resolucion.normalizar_texto_sucursal("MR bucaramanga la 27  ") == "BUCARAMANGA LA 27"
    assert resolucion.normalizar_texto_sucursal("  Cali   Norte  ") == "CALI NORTE"
    assert resolucion.normalizar_texto_sucursal("Bogotá") == "BOGOTA"
