"""
Motored Pedidos — Fase 2 "Ingesta", Phase 11 "Perf Gates" (PR11)
(sdd/motored-pedidos-ingesta, tasks 11.1/11.2; design ADR-8 + Testing
Strategy "Perf tier 1/tier 2"; design-addendum "Correction 2").

Scope, deliberately narrow: exercises ONLY the two units ADR-8 governs --
`services/ingesta/resolucion.py` (cache-first key resolution) and one
movement transform per tier (`inventario.py` tier 1, `ventas.py` tier 2) --
never the full `orquestador.py` pipeline (streaming file read from MinIO,
per-lote staging writes to Postgres, `carga_archivo` state machine), which
is Phase 9's own already-shipped and already-tested surface
(`test_ingesta_orquestador.py`). `procesar_fila` in both transforms is a
PURE function that NEVER touches `session` (only `resolucion.
construir_cache` and each transform's `aplicar` do) -- so the honest,
exact query-count ceiling for this scope is 4 (cache, ADR-8) + 1 (the
final set-based upsert) = 5, independent of row count BY CONSTRUCTION, not
by a chosen threshold. That is exactly the regression class ADR-8 exists to
prevent: if `procesar_fila` were ever changed to resolve sucursal/
referencia against `session` per row instead of the cache, this ceiling
would jump from 5 to tens of thousands on the very first CI run.

Tier 1 (no marker, runs in the default suite on every push): a ~56 500-row
INVENTARIO fixture -- the corrected sizing from design-addendum
"Correction 2" (INVENTARIO, weekly, is the largest RECURRING load, not
VENTAS).

Tier 2 (`@pytest.mark.lento`, registered in `pytest.ini`, excluded from the
default run via `addopts = -m "not lento"`): a ~305 901-row VENTAS fixture
-- the real onboarding-seed size (design "Load Sizing"). Adds a
`tracemalloc` peak-memory ceiling tier 1's smaller fixture cannot exercise
meaningfully.

No live Postgres anywhere in this file -- same `FakeAsyncSession`
convention as the rest of `tests/motored/` (see `test_ingesta_resolucion.py`
for the isolated ADR-8 cache test this file reuses at volume).
"""
from __future__ import annotations

import time
import tracemalloc
import uuid
from datetime import date
from typing import Iterator, List, Sequence, Tuple

import pytest

from tests.motored.conftest import FakeAsyncSession

from app.motored.services.ingesta import inventario, periodo, resolucion, ventas

CARGA_ID = uuid.uuid4()
PROVEEDOR_ID = uuid.uuid4()

# ADR-8's own docstring sizes the real HMCL masters cache at "≈13 200 + ~100
# entries" -- reproduced here (not a round number) so the cache-build step
# is realistically SHAPED, not just realistically sized.
N_SUCURSALES = 100
N_REFERENCIAS = 13200

LOTE = 2000  # `MOTORED_INGESTA_LOTE` default -- only used to stamp a
# realistic `lote` number on each generated row; neither transform's
# `procesar_fila` touches `session` per lote, so this has no effect on the
# query-count ceiling, only on how faithfully the fixture mirrors
# production bookkeeping.


def _sucursales_seed() -> List[Tuple[uuid.UUID, str, None]]:
    return [(uuid.uuid4(), f"SUCURSAL {i:04d}", None) for i in range(N_SUCURSALES)]


def _referencias_seed() -> List[Tuple[str, uuid.UUID, uuid.UUID]]:
    return [(f"REF{i:06d}", PROVEEDOR_ID, uuid.uuid4()) for i in range(N_REFERENCIAS)]


async def _construir_cache(
    sucursales: Sequence[tuple], referencias: Sequence[tuple]
) -> Tuple[FakeAsyncSession, "resolucion.CacheResolucion"]:
    """Mismo camino real que `test_ingesta_resolucion.py` ya prueba en
    aislamiento (`resolucion.construir_cache` contra un `FakeAsyncSession`
    con `execute_queue=[sucursales, bodegas, alias, referencias]`) --
    reutilizado acá a escala. Retorna también `session` para que el caller
    siga contando queries después de este punto."""
    session = FakeAsyncSession(
        # Los primeros 4 resultados son el cache (ADR-8); el 5to es para el
        # ÚNICO `session.execute()` adicional que cada tier ejecuta después
        # (el upsert set-based de `aplicar`/`aplicar_con_periodo`) -- su
        # valor de retorno no se usa (ninguno de los dos transforms lee el
        # resultado del upsert), así que una lista vacía alcanza.
        execute_queue=[list(sucursales), [], [], list(referencias), []]
    )
    cache = await resolucion.construir_cache(session)
    return session, cache


# ---------------------------------------------------------------------------
# Tier 1 (task 11.1) — CI gate: ~56 500-row INVENTARIO fixture
# ---------------------------------------------------------------------------

INVENTARIO_MAPA_COLUMNAS = {"Referencia": 0, "Bodega": 1, "Desc.bodega": 2, "Existencia": 3}
INVENTARIO_ROWS = 56500


def _generar_filas_inventario(n: int, sucursales: Sequence[tuple]) -> Iterator[tuple]:
    """Generador -- NUNCA una lista materializada de `n` filas -- mismo
    shape que `inventario.COLUMNAS_ESPERADAS`. La ÚLTIMA fila trae una
    `Referencia` no vacía pero irresoluble a propósito (proposal: "A load
    with 1 rejected row out of 305 901 ... is the whole point of the
    phase", reproducido acá a escala de INVENTARIO) para probar que el
    camino tolerante-por-fila sigue funcionando a volumen real, no solo en
    el caso 100% feliz."""
    for i in range(n - 1):
        _, nombre_sucursal, _ = sucursales[i % len(sucursales)]
        referencia_codigo = f"REF{i % N_REFERENCIAS:06d}"
        yield (referencia_codigo, "BA061", nombre_sucursal, "10.5")
    yield ("REF-NO-EXISTE", "BA061", sucursales[0][1], "1")


async def test_inventario_56500_rows_es_cache_first_con_queries_y_latencia_acotadas():
    sucursales = _sucursales_seed()
    referencias = _referencias_seed()
    session, cache = await _construir_cache(sucursales, referencias)
    assert len(session.executed_statements) == 4  # ADR-8: el cache, una única vez

    fecha_corte = date(2026, 9, 15)
    staged = []
    errores_totales = []

    inicio = time.perf_counter()
    for numero_fila, fila_raw in enumerate(
        _generar_filas_inventario(INVENTARIO_ROWS, sucursales), start=2
    ):
        fila_staging, errores_fila = inventario.procesar_fila(
            fila_raw,
            numero_fila=numero_fila,
            lote=(numero_fila // LOTE) + 1,
            mapa_columnas=INVENTARIO_MAPA_COLUMNAS,
            cache=cache,
            carga_id=CARGA_ID,
            proveedor_id=PROVEEDOR_ID,
        )
        if fila_staging is not None:
            staged.append(fila_staging)
        errores_totales.extend(errores_fila)

    consolidado = inventario.consolidar_existencias(staged)
    await inventario.aplicar(session, consolidado, fecha_corte, CARGA_ID)
    duracion = time.perf_counter() - inicio

    # --- Comportamiento (no solo performance): las 56 500 filas se
    # procesaron tolerando UNA fila irresoluble, sin abortar el archivo.
    assert len(staged) == INVENTARIO_ROWS
    assert len(errores_totales) == 1
    assert errores_totales[0].codigo_error == "REFERENCIA_NO_ENCONTRADA"
    assert len(consolidado) > 0

    # --- Query-count ceiling (ADR-8): 4 del cache + 1 del upsert final de
    # `aplicar` -- NUNCA escala con el número de filas. Si `procesar_fila`
    # alguna vez volviera a tocar `session` por fila, este assert saltaría
    # de 5 a decenas de miles en el primer push a CI.
    assert len(session.executed_statements) == 5
    # Ninguno de los dos módulos hace commit -- es responsabilidad
    # exclusiva del caller (docstring de `aplicar` en ambos transforms).
    assert session.committed is False

    # --- Latency ceiling: generoso pero real. ~56 500 filas de puro Python
    # (dict lookups O(1) contra el cache + `Decimal`) corren en un puñado
    # de décimas de segundo; un regresión que reintroduzca un lookup
    # O(n)/O(n²) por fila en vez de O(1) contra el cache se nota acá.
    assert duracion < 5.0, (
        f"INVENTARIO de {INVENTARIO_ROWS} filas tardó {duracion:.2f}s (budget: 5s; "
        f"medido localmente ~1s -- un regresión que reintroduzca un lookup por fila "
        f"contra la base, o un O(n²) en vez de O(1) contra el cache, se nota acá)"
    )


# ---------------------------------------------------------------------------
# Tier 2 (task 11.2) — opt-in: ~305 901-row VENTAS seed (`@pytest.mark.lento`)
# ---------------------------------------------------------------------------

VENTAS_MAPA_COLUMNAS = {
    "Estado": 0,
    "Módulo": 1,
    "Fecha": 2,
    "Cantidad inv.": 3,
    "Tipo inventario": 4,
    "Desc.bodega": 5,
    "Bodega": 6,
    "Referencia": 7,
}
VENTAS_ROWS = 305901
VENTAS_MESES = 6  # design "Load Sizing": el seed real cubre 6 meses, ~51 000/mes


def _generar_filas_ventas(n: int, sucursales: Sequence[tuple]) -> Iterator[tuple]:
    """Mismo criterio de generador que `_generar_filas_inventario`, más la
    dimensión de fecha/mes: distribuye las filas en los 6 meses declarados
    (design edge case E4, "seed multi-mes soportado de primera clase") para
    que el veredicto ADR-9 (`ventas.aplicar_con_periodo`) se ejercite de
    punta a punta, no solo el resolver. La ÚLTIMA fila repite el mismo
    truco de `Referencia` irresoluble que Tier 1."""
    filas_por_mes = n // VENTAS_MESES
    for i in range(n - 1):
        mes = 1 + min(i // filas_por_mes, VENTAS_MESES - 1)
        _, nombre_sucursal, _ = sucursales[i % len(sucursales)]
        referencia_codigo = f"REF{i % N_REFERENCIAS:06d}"
        modulo = "MOSTRADOR" if i % 2 == 0 else "TALLER"
        yield (
            "Aprobada", modulo, date(2026, mes, 15), "1", "0002 - REPUESTOS",
            nombre_sucursal, "BA061", referencia_codigo,
        )
    yield (
        "Aprobada", "MOSTRADOR", date(2026, 1, 15), "1", "0002 - REPUESTOS",
        sucursales[0][1], "BA061", "REF-NO-EXISTE",
    )


@pytest.mark.lento
async def test_ventas_305901_rows_seed_es_cache_first_con_queries_latencia_y_memoria_acotadas():
    sucursales = _sucursales_seed()
    referencias = _referencias_seed()
    session, cache = await _construir_cache(sucursales, referencias)
    assert len(session.executed_statements) == 4  # ADR-8: el cache, una única vez

    periodo_desde = date(2026, 1, 1)
    periodo_hasta = date(2026, 6, 30)

    tracemalloc.start()
    inicio = time.perf_counter()

    staged = []
    errores_totales = []
    for numero_fila, fila_raw in enumerate(
        _generar_filas_ventas(VENTAS_ROWS, sucursales), start=2
    ):
        fila_staging, errores_fila = ventas.procesar_fila(
            fila_raw,
            numero_fila=numero_fila,
            lote=(numero_fila // LOTE) + 1,
            mapa_columnas=VENTAS_MAPA_COLUMNAS,
            cache=cache,
            carga_id=CARGA_ID,
            proveedor_id=PROVEEDOR_ID,
            tipos_inventario_incluidos=["0002 - REPUESTOS"],
        )
        if fila_staging is not None:
            staged.append(fila_staging)
        errores_totales.extend(errores_fila)

    veredicto = await ventas.aplicar_con_periodo(
        session, staged, periodo_desde, periodo_hasta, CARGA_ID
    )
    duracion = time.perf_counter() - inicio
    _, pico_memoria = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # --- Comportamiento: el seed completo de 305 901 filas se agregó y
    # aplicó con el período declarado ACEPTADO (todas las filas caen dentro
    # de enero-junio 2026), tolerando UNA fila con referencia irresoluble.
    assert len(staged) == VENTAS_ROWS
    assert len(errores_totales) == 1
    assert errores_totales[0].codigo_error == "REFERENCIA_NO_ENCONTRADA"
    assert veredicto.tipo == periodo.TipoVeredictoPeriodo.ACEPTADO

    # --- Query-count ceiling (idéntico razonamiento que Tier 1, ADR-8): 4
    # del cache + 1 del upsert final -- independiente de que acá haya 5.4x
    # más filas que en Tier 1.
    assert len(session.executed_statements) == 5
    assert session.committed is False

    # --- Latency ceiling: generoso -- esta corrida es opt-in (`lento`), no
    # bloquea el push normal a CI, así que el presupuesto puede ser más
    # laxo que en Tier 1 sin dejar de detectar una regresión real.
    assert duracion < 60.0, (
        f"VENTAS seed de {VENTAS_ROWS} filas tardó {duracion:.4f}s (budget: 60s; "
        f"medido localmente ~5.4x el tiempo de Tier 1 -- una regresión que "
        f"reintroduzca un lookup por fila contra la base, o un O(n²) en vez de "
        f"O(1) contra el cache, se nota acá)"
    )

    # --- Memory ceiling: lo único que Tier 1 no puede ejercitar de forma
    # significativa a su escala menor. ~305 901 objetos `CargaFilaStaging`
    # en memoria simultánea es exactamente el patrón que `orquestador.
    # ejecutar_aplicar` ya reproduce en producción real (`result.scalars().
    # all()` trae TODO el staging de una carga a memoria antes de agregar
    # -- design "Memory headroom ... the tier-2 perf test is the only thing
    # that actually validates the ceiling"). Presupuesto con margen sobre lo
    # medido localmente, generoso frente al límite real del contenedor
    # (2 GB, compartido con el resto de Motored).
    presupuesto_bytes = 750 * 1024 * 1024
    assert pico_memoria < presupuesto_bytes, (
        f"Pico de memoria {pico_memoria / (1024 * 1024):.1f}MB "
        f"supera el presupuesto de {presupuesto_bytes / (1024 * 1024):.0f}MB"
    )
