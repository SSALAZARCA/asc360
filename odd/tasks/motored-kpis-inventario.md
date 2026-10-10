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
- [x] T3 (2026-10-10, delegated writer; user: first task of the day) The whole tab reads from KPI summary tables like the other tabs, with the same live fallback (`usar_resumen` false = off / dirty / never built) and the same `frescura` header. Outputs are identical live vs summary (pg_real equivalence). Commits: `feat(motored): summarize closing inventory cuts and monthly cost of sales per referencia` (models, migration `c4e8a2d6f931`, builder) and `feat(motored): serve the Inventario tab from the KPI summaries` (readers + wiring).

### T3 decision note
- **Inventory of the queries and where each one went** (cost measured on a synthetic 1M `venta_detalle` + 600k `inventario_detalle` world, local):

  | Input | Before | Now |
  |---|---|---|
  | cortes list | `DISTINCT` over `inventario_detalle` | `kpi_inventario_corte` (closing cuts) |
  | value per corte x store (+ current corte) | 2 scans of `inventario_detalle` (0.12 s) | `kpi_inventario_corte` (1 ms) |
  | pairs with stock at the corte + pairs of each trend corte | 2 scans of `inventario_detalle` (0.62 s + the 0.15 s pairs) | `kpi_inventario_par`, ONE query (0.33 s for 600k pair rows) |
  | cost of sales per month x store x line x referencia | scan of `venta_detalle` (0.95 s) | `kpi_costo_mes_referencia` (0.04-0.08 s) |
  | sales per pair, first sales month | `venta_mensual` (already a monthly aggregate: 3 ms-0.1 s) | LIVE (no raw table) |
  | lost sales per pair | `demanda_perdida` filtered to a 3-month window | LIVE (windowed, indexed by date) |
  | transit per pair | `factura_proveedor_linea` + `ingreso_factura` (2 statements) | LIVE: it needs a dirty mark on FACTURAS_PROVEEDOR / INGRESOS loads, and those load paths are outside this task's edit surface |
  | pending invoices value/count | `ingresos_pendientes.pendientes` (8 statements) | LIVE: it depends on today's date (overdue/threshold) and on user confirmations, so it cannot be baked |
  | reference labels, store names | by id, tiny | LIVE (one statement for both top lists now) |
- **Closing cuts only.** The tab only ever shows the corte (= the latest), the latest cut of each month of the trend and the previous month's close, so the builder keeps just `max(fecha_corte)` per calendar month (non-annulled). `kpi_inventario_corte` therefore holds every closing cut now (it used to hold only the latest); `lectura.cortes` answers that subset when the summary answers and the payload is the same.
- **Raw store + read-time rollup.** Both new tables store the RAW `sucursal_id`; the principal rollup, the store filter, the lines (`_lineas_por_referencia`) and everything configurable are applied when reading, exactly as the other summaries do. `kpi_inventario_par` has no FK on `referencia_id` (the live valuation keeps lines whose referencia is missing from the master); units sold are not stored because the tab reads them from `venta_mensual`.
- **Rebuild path.** `reconstruir_todo` / `reconstruir_costos` fill both tables; `refrescar_periodos` (ventas load/annul/purge) deletes and re-derives `kpi_costo_mes_referencia` for the touched (store, month) keys; an inventory load/annul marks the summaries dirty (existing call sites) and the background job rebuilds. The migration flags the state dirty because the new tables start empty.
- **Dirty-marking audit.** Covered: inventory apply (`ingesta/inventario.py`), annul of INVENTARIO and VENTAS (`api/cargas.py`), ventas apply/purge (`ingesta/ventas.py`), `linea_comercial` change and Tecnired list (`maestros.py`), Configuracion changes (`parametros.py`). GAPS (files outside this task's surface, to fix next): (1) `services/retencion.py` purges `inventario_detalle` without marking dirty, so purged cortes stay in the summary until the next rebuild; (2) `maestros.py` marks dirty only when `linea_comercial` changes, not when `precio_normal` changes, although `precio_normal` is the fallback cost/valuation baked into `kpi_costo_referencia`, `kpi_inventario_*` and `kpi_venta_mes` (pre-existing gap, now also affects this tab).
- **Query count.** 24 statements per request (including the 2 of `cargar_filtro`), live 25 before this task's reference-label merge and 24 now; with the summary on it is also 24 (the state row +1, the two pair queries -1; asserted <= 24 in pg_real, live cap 25 kept). The target of <= 10 was NOT reached: 8 are `pendientes`, 2 transit and 2 parameter reads that stay live; what moved is the weight (no scan of `venta_detalle` or `inventario_detalle` when the summary answers; asserted in pg_real).

### T3 evidence
- RED observed first: the migration test (4 failures: no revision), the builder tests (KeyError / assertion: only the latest cut was kept, no cost table), the reader tests (AttributeError) and the raw-table assertion (summary mode still scanned `inventario_detalle`).
- Unit `pytest tests/motored` (no `MOTORED_DATABASE_URL`): 7554 passed. pg_real (Postgres 18) `-k "inventario or resumen or golden or kpi"`: 207 passed; 1 failure in `test_conteos_snapshot_pg` (ADMIN as snapshot leader) that does not touch KPI code. Alembic: one head `c4e8a2d6f931`. `compileall` OK (Python 3.11).
- Golden file (`kpis_golden.json`) does not cover the Inventario tab: not refreshed.
- Synthetic benchmark (1M sale lines, 600k inventory rows, 45 stores, 6000 referencias; local socket, so no network latency): tab 3.0 s live -> 1.5 s from the summaries (statement time 2.1 s -> 0.47 s); the rest is Python over ~600k pair rows. Full rebuild of every summary on that world: 14 s.
