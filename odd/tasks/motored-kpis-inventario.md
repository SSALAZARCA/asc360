# Motored — KPI's "Inventario" tab

Locator: `odd/tasks/motored-kpis-inventario.md` · Engram topic `odd/motored-kpis-inventario/tasks`
Design (approved 2026-10-09): Artifact https://claude.ai/artifact/WXrhmmeVMircjCyRRPYEXN, board "Propuesta · Inventario" (`project/Inventario.dc.html`).

## Objective
Build the approved Inventario tab of KPI's with real data: six KPI cards, month-end inventory value trend, age of inventory, by line, by store, top idle references, and stockouts with demand covered by transit.

## Data facts (explorer, 2026-10-09)
- Valued inventory (`inventario_detalle`, per bodega with `costo_unitario`) exists only from 2026-10-01; cortes accumulate (each load keeps its `fecha_corte`) unless `retencion_inventario_habilitada` is on. Value rule = `_valoracion_inventario` (cost > 0, else `precio_normal`, else 0 counted `sin_costo`); readers exclude ANULADO loads; principal-store rollup via `principal_expr`.
- Sales history starts ~2026-01; no `(sucursal, referencia, fecha)` index on `venta_detalle`; `venta_mensual` gives last month with sales (filter `unidades > 0`).
- Lost sales: `demanda_perdida.cantidad_solicitada` (EXCEL + BOT), filter `origen='BOT' OR carga.estado != 'ANULADO'`.
- Transit per (sucursal, referencia): `corridas/transito_corte.cargar_transito_corte(...).w` with params as in `corridas/servicio.py:331-346`, rolled up to principal.

## Decisions (user)
- Trend option A (2026-10-09): only months that have a valued corte (latest corte on or before each month end, last 12 months); fills month by month; past month-end files can be loaded later and appear automatically.
- Demand for stockouts = units sold + lost sales, last 3 months; coverage = units in transit vs that demand.
- Assumptions shown on the design and accepted: target días 60, color cuts ≤60 green / ≤90 amber / >90 violet, idle threshold 180 days — all configurable in Configuración (section indicadores).
- Age of inventory measured from the last month with sales (`venta_mensual`); references never sold since history start fall in the oldest band reachable; ">365" stays empty until history is long enough (explained in a tooltip).

## Tasks
- [x] T1 Backend: Configuración keys; `calcular_kpis_inventario` (cards, trend, age bands, by line, by store, top idle, stockouts with demand/transit); `GET /tablero-asesores/kpis/inventario` + Excel; tests (unit + pg_real).
- [x] T2 Frontend: Inventario tab exactly as the approved board (tablet + phone), store click filters the tab, Excel button; jest tests.

## Route
Delegated direct (multi-file per task).

## Progress / evidence
- Base: main `88216fe`.
- T1 done (2026-10-09, delegated writer). Commits: `6120083` Configuración keys (`kpi_inventario_dias_meta` 60, `kpi_inventario_dias_cortes` {verde_hasta 60, ambar_hasta 90}, `kpi_inventario_sin_movimiento_dias` 180); `002c053` queries + payload (`tablero_kpis_inventario.py`, `tablero_kpis_inventario_consultas.py`); `e6430cb` endpoints `GET /tablero-asesores/kpis/inventario` and `/inventario/excel` (`tablero_inventario_excel.py`).
- Evidence: `pytest tests/motored` 7366 passed; pg_real (Postgres 18) `-k tablero_kpis` 48 passed + inventory file 17 passed; `compileall` OK (Python 3.11). One request = 22 queries (bounded, asserted <= 24 in pg_real).
- Choices: trend = a point only for months with a corte inside the month (latest of that month); card/lines/trend days use the cost of the stores that have inventory at that corte (same rule as the Tiendas tab); `pct` values are fractions; never-sold pairs age from the first DAY of the first sales-history month; HMCL mode does not alter inventory or cost of sales.
- T2 done (2026-10-09, delegated writer). Commit `c1c0702`: tab in `components/motored/kpis/inventario/` (InventarioTab container + Tarjetas, Tendencia, Antiguedad, PorLinea, PorTienda, SinMovimiento, AgotadasConDemanda, datos.js, estilos.js), plumbing in KpiTabs/KpisContent/useKpis/kpisApi (`getInventario`, `descargarInventarioExcel`); store click uses `onChange({sucursales:[id]})` (KpisContent now passes `onChange` to every tab).
- Evidence: `npx jest --silent` 226 suites / 2615 tests passed; `next dev --webpack` compiles `/motored/tablero-asesores` (200).
- 2026-10-09 (user request, delegated writer): each month bar of "Valor del inventario por mes" is split into green / amber / violet by days of inventory. Backend: `tendencia[].bandas = [{banda: verde|ambar|violeta, valor, pct}]` (pct is a fraction, `null` when the point has no stocked pairs). Per (principal store, referencia) pair with stock > 0 at that corte: days = pair value / (pair cost of sales in the same 3-month window / window days); <= `verde_hasta` green, <= `ambar_hasta` amber, else violet; no/zero/negative cost of sales in the window = violet. Bands sum the stocked pairs (excludes negative-stock lines that the month `valor` nets) and each value is rounded to cents, so the sum can differ from `valor` by cents or by those lines. Queries: the cost query now also groups by referencia (one query feeds both the line/store cost and the per-pair cost) plus one pairs-by-corte query: 24 per request (cap 24). Frontend: stacked bar with tooltips, shares row above the days chip, legend text, fallback to the single bar without `bandas`. Excel unchanged.
- 2026-10-09 (user decision): the whole Inventario tab ignores the Período filter. Backend (`4abd729`): corte = latest valued non-ANULADO corte; cost window = 3 months ending at the last month with sales (fallback: corte month); previous value = latest corte on or before the end of the month before the corte's month; trend = last 12 months ending at the corte's month; `elegir_corte` removed (dead). Query cap in the pg_real test raised 24 -> 25: one scalar query for the last month with sales (`lectura.meses`). Excel follows (same `calcular_inventario`). Frontend: `KpiHeader` takes `ocultarPeriodo` + `etiquetaPeriodo` ("Inventario al dd/mm/aaaa"), `KpisContent` passes them for the inventario tab, and `claveKpis('inventario', ...)` omits the months so changing the Período does not refetch.
- Pending (2026-10-09, user: first task on 2026-10-10): the tab still runs ~25 live queries per open; only the current-corte value comes from the summary. Extend the KPI summary tables (background rebuild, `usar_resumen`/`frescura`) so the whole tab reads from them like the other tabs, with live fallback and pg_real live==summary tests.
