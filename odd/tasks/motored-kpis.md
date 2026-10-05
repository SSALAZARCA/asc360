# Motored: KPI's section (Ventas, Tiendas, Asesores with budget compliance)

Engram mirror: `odd/motored-kpis/tasks` (project asc360).
Design reference: Artifact https://claude.ai/artifact/WXrhmmeVMircjCyRRPYEXN (tabs Ventas, Tiendas, Asesores).
Exploration: Engram decision `motored/kpis/decisiones`; the mapping report (2026-10-04) is summarized below.

## Objective
Replace "Tablero asesores" with a graphical **KPI's** section: tabs Ventas, Tiendas and Asesores, using real data and including budget compliance (cumplimiento). Comisiones, Inventario and Pedidos are later work.

## Why
The user designed the dashboard in the artifact and approved it. The budgets master and the Configuración keys are already on main, so compliance no longer waits on anything.

## Business rules
**Confirmed by the user**
- Cumplimiento = venta CON HMCL ÷ presupuesto, per `cumplimiento_base`.
- Budgets are per asesor per month. Store budget = the sum of its assigned asesores.
- The rules come from Configuración via `vigente_en`/`leer_valores`: `hmcl_nits`, `grupo_por_cargo`, `lineas_comerciales`, `kpi_semaforo_cortes`, `cumplimiento_base`.
- Brand manual colors: data teal/ámbar/violeta, categories in a blue scale, red for the brand only, Manrope 500/700.
- Charts are hand-made SVG/HTML. No chart library.

**Defaults chosen** (follow the Excel where it defines the rule; the user may override)
1. **Multi-month selection:** the Configuración values in effect for the LAST selected month apply.
2. **Asesor cumplimiento:** the asesor's sales (con HMCL) in the selected months ÷ the sum of their budgets in the same months. Months without a budget are excluded from both numerator and denominator. An asesor with no budget in any selected month shows "Sin presupuesto".
3. **Store cumplimiento** (as in the Excel's CUMPLIMIENTO sheet): the sum of the sales of the asesores assigned to that store in the budget ÷ the store budget (the sum of those asesores). An asesor's sales count toward the store of their budget assignment.
4. **"Cumple":** cumplimiento ≥ `kpi_semaforo_cortes.verde_desde` (90%). The semáforo cuts come from Configuración.
5. **Tiendas sales views** (ranking, mix, heatmap): ALL sales of the store, including RESTO and COMERCIALES. Only cumplimiento uses the asesor-only rule above.
6. **Growth (crece/cae):** the last 3 calendar months ending at the last selected month vs the 3 before them, as in the Excel's "VAR % 3M VS 3M". A store with `fecha_apertura` within the last 6 months, or with no sales in that window, is "nueva".
7. **Días de inventario per store:** inventory at cost (latest `fecha_corte`) ÷ the daily cost of sales over the last 3 months.
8. **Max selection:** 12 months, as today.
9. **Asesores without a cédula** in the master cannot match a budget. Show "Sin presupuesto" plus a warning count.

## Scope
**In scope**
- Backend: rules from Configuración; a month-list and store filter; a per-store cube dimension; accumulators for month×line and Tecnired by month and line; budget join and cumplimiento; Tecnired clients and top-5 queries; inventory days per store; per-tab endpoints.
- Frontend: chart primitives, header filters, the three tabs, sidebar rename to "KPI's", and removal of the old table.

**Out of scope**
- The Comisiones tab (next feature).
- Inventario and Pedidos tabs.
- Editable permissions.

## Constraints
**Access**
- Roles: ADMIN, COMPRAS, GERENCIA (TABLERO_ROLES).
- GERENCIA is confined server-side to `/auth`, `/presupuestos` and `/tablero-asesores`. Keep the endpoints under `/tablero-asesores`, or update `deps.py` and its tests.

**Shared files**
- Session -22 may touch shared files (sidebar, parametros). Rebase before every push.
- `permisosPorRol.js` drift tests must stay green: update the matrix when the sidebar changes.

**Queries**
- Keep the `venta_detalle` index usable: filter by date ranges joined with OR, never `date_trunc` in the WHERE.
- Cumplimiento needs venta con HMCL even when the HMCL selector is excluir/solo. Query the cube with `incluir` and apply the HMCL mode in Python. Facturas and clientes stay filtered in SQL.
- Normalize cédulas with `limpiar_cedula` on both sides when joining budgets.

**Frontend**
- No backticks in CSS comments inside the `themeCss` template literal.
- Every `<option>` needs an explicit style.
- Tooltips on non-obvious fields.
- Tablet 768–1024 px.
- Labels as HTML overlays, not dynamic SVG `<text>` (the design taught us that).

**Runtime:** production runs Python 3.11 (the venv is 3.11.16).

## Test-first
- **Backend:** `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`.
- **pg_real:** the tablero queries are only covered there. Use a throwaway PG 18 from `/usr/lib/postgresql/18/bin` (`initdb --auth=trust`) with `MOTORED_TEST_PG_URL` plus dummy env vars, and run `-m pg_real tests/motored`. Never run it concurrently with the unit suite.
- **Frontend:** `cd frontend && npx jest`. Compile-check with `npx next dev --webpack`.

## Delivery
- **Repo policy:** commit and push to main per work unit (Coolify deploys main). There are no PRs.
- **Native review:** on each work-unit range. Park `.gga`/`AGENTS.md` only during review, and restore them before any commit.
- **Forecast:** ~5,000 authored lines over 12 tasks. Each task is reviewed and pushed separately.

## Tasks
- [x] **B1 Rules from Configuración.** A `Reglas` object read once with `parametros.leer_valores` (fecha = last selected month), passed to `_expr_clave`, `_expr_es_hmcl`, `_lineas_por_referencia`, `_indicadores` and `construir_tablero`. pg_real tests.
- [x] **B2 Filter object.** Explicit month list (consecutive months merged into OR ranges), `sucursal_ids`, API params `meses` and `sucursales`. Cube always `incluir`, with the HMCL mode applied in Python.
- [x] **B3 Store dimension + accumulators.** A cube key parameter (asesor/sucursal/total), facturas and clientes per dimension, `por_mes_linea`, Tecnired by month and by line, growth 3M and nueva classification.
- [x] **B4 Budgets + cumplimiento.** Join `presupuesto_por_asesor`/`presupuesto_por_sucursal` (min/max then filter), per-asesor and per-store cumplimiento per the rules above, semáforo, rows for budgeted asesores without sales, "sin presupuesto".
- [x] **B5 New queries.** Distinct Tecnired clients, top-5 Tecnired clients with `razon_social`, días de inventario per store.
- [x] **B6 Per-tab endpoints.** `/tablero-asesores/kpis/{ventas|tiendas|asesores}` (stays inside the GERENCIA prefix), plus the store list for the filter.
- [x] **F1 Chart primitives.** Gauge, donut, strip (zones), bars with value inside, stacked area, heatmap, treemap, scatter, segmented toggle. Plus color tokens in `layout.js`.
- [x] **F2 Header + shell.** Period popover (año corrido / multi-month), store multi-select with search, HMCL popover, tabs, data hook with a per-tab cache, sidebar rename "KPI's", permisos matrix update.
- [x] **F3 Ventas tab.**
- [x] **F4 Tiendas tab.**
- [x] **F5 Asesores tab.**
- [x] **F6 Cleanup.** Remove the old TableroTable/columnas/fixtures and update the sidebar/gate tests.

## Progress / evidence
**B1 + B2, done.** Route: one delegated writer (multi-file backend) with two commits, rebased onto 1b6e094.
- **Implementation**
  - `Reglas` (NamedTuple; `REGLAS_POR_DEFECTO` equals the old constants) is loaded by `cargar_reglas(db, fecha)` via `leer_valores`.
  - Cargos and NITs are bound params; lines outside `reglas.lineas` count as `venta_sin_linea`.
  - The response echoes `reglas` (semaforo, cumplimiento_base, vigencia).
  - `Filtro` holds month ranges as OR date ranges, `sucursal_ids` and the HMCL mode. The cube is always HMCL-included, with `filtrar_cubo_por_hmcl` in Python (a pg_real test proves it equals the old SQL filter); facturas, clientes and personas filter in SQL.
  - API: `meses` CSV and `sucursales` CSV UUIDs. Combining `meses` with `desde`/`hasta` returns 422.
  - `calcular_tablero(db, desde, hasta, modo_hmcl)` stays as a compat wrapper for `test_gerencia_role.py`; the new path is `calcular_tablero_por_meses`.
- **TDD evidence:** RED by stashing the source: B1 11 failed; B2 17 failed + 32 errors + 11 pg_real failed.
- **Checks**
  - Unit suite: 5110 passed.
  - Tablero pg_real: 33 passed.
  - Full pg_real: 476 passed / 2 skipped / 2 failed. The failures are `test_pedido_tienda_pg::test_the_retention_keeps_corridas_whose_pedido_is_history` and `test_supervisor_corridas_pg::test_the_retention_purges_only_old_annulled_failed_or_draft`; the second also fails at bef8792, before B1, so they are not caused by this work (session -22's retention area).
  - After the rebase, the parent ran the tablero/gerencia unit tests: 133 passed.
- **Carried to B3:** `variacion_3m` still uses the last 3 vs previous 3 LIST entries; it must use calendar months.

- **Delivery:** commits 4c11010 and 792e39a, pushed to main.
- **Native review:** risk medium (988 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories, carried to B3 to investigate and fix**
  - R3-grupo-arbitrario (consultas:85-86).
  - R3-lineas-no-normalizadas: Configuración line names are not normalized like referencia lines (consultas:114).
  - R3-reglas-tipos: loaded values are not type-checked (consultas:346-352).
  - The dedupe test has no assertion.
- **Coordination:** the 2 failing retention pg_real tests were reported to session -c4.

**Fix + B3 + B4, done.** Route: one delegated writer, three commits.
- **Commit 95967dc, fix:**
  - An unknown group now maps to OTROS.
  - Configuración lines are normalized on both sides. This was a real bug: lowercase or accented lines never matched.
  - `reglas_desde_valores` falls back per key to the default and logs a warning.
  - The dedupe test now asserts.
- **Commit c63f2b3, B3:**
  - Cube dimension `DIM_ASESOR|DIM_SUCURSAL|DIM_TOTAL`; the vendor join is skipped for store and total.
  - New accumulators: `por_mes_linea`, `tecnired_por_mes`, `tecnired_por_linea`.
  - Growth comes from a separate `consultar_ventana_mensual` query (6 calendar months ending at the last selected month) with `crecimiento_3m`.
  - `nueva` = `fecha_apertura` ≥ the window start, or no sales in the first 3 months of the window.
  - New `services/tablero_kpis.py` with `calcular_kpis_ventas`, `calcular_kpis_tiendas` and `calcular_kpis_asesores`.
- **Commit 38184e6, B4:**
  - Compliance per asesor and per store follows defaults 2–4, with `limpiar_cedula` on both sides.
  - Fields: `semaforo` is verde/ambar/violeta; `estado` is cumple/en_camino/atrasado/sin_presupuesto; `cumplimiento_pct` is a fraction, compared in Decimal so exactly 90% is green.
  - Budgeted asesores without sales are included.
  - Warnings: `personas_sin_cedula` and `venta_sin_cedula`.
  - The store filter limits budgets by the budget's store.
- **Deviation:** the Asesores `tendencia` keeps the list-position 3M, because an existing test pins it. Calendar-month growth applies only to stores. A small follow-up can change it if wanted.
- **Checks**
  - Unit suite: 5167 passed.
  - pg_real: 491 passed / 2 skipped / 2 known retention failures.
  - After the rebase, the parent ran the KPI and tablero unit tests: 96 passed.
- **TDD note:** RED evidence came from removing the source after implementing (collection errors), not strict RED-first.

- **Delivery:** commits 95967dc, c63f2b3 and a7d4fe0, pushed to main.
- **Native review:** risk medium (1,711 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories, carried to B5**
  - R3-semaforo-nan (WARNING): NaN semáforo cuts may pass validation (`tablero_asesores.py:112-127`).
  - R3-meses-orden (suggestion, `:360`).

**Fix + B5 + B6, done.** Route: one delegated writer, three commits.
- **Commit 8ceab58, fix:** NaN or infinite semáforo cuts fall back to the default; `filtro_de_meses` sorts and de-duplicates.
- **Commit f8b832b, B5:**
  - New `services/tablero_kpis_consultas.py`.
  - Tecnired: distinct clients, clients per month, `venta_por_cliente`, and top-5 with `razon_social`.
  - Días de inventario: inventory at the latest corte (lines with null/≤0 cost excluded and counted) ÷ daily cost of sales over the 3 calendar months ending at the last selected month, using the same median cost per referencia as margin. A store appears only if it has inventory loaded.
- **Commit 1915a78, B6:** router `api/tablero_kpis.py` under `/api/motored/tablero-asesores/kpis`:
  - `GET /ventas|/tiendas|/asesores` with `meses` (required), `sucursales` and `hmcl`.
  - `GET /opciones` returns `meses_disponibles`, `ultimo_mes` and the active `tiendas`.
  - Roles: ADMIN, COMPRAS and GERENCIA. GERENCIA is covered by the existing prefix confinement, which matches on segment boundaries.
- **TDD evidence:** RED for commit 0 (5 failed); B5 failed at collection on an ImportError; B6 API had 48 errors and 1 failure. The pg_real end-to-end tests were written after the implementation.
- **Checks**
  - Unit suite: 5235 passed.
  - pg_real: 503 passed / 2 skipped / 2 known retention failures.
  - After the rebase, the parent ran the KPI API, B5, tablero API and gerencia tests: 121 passed.
- **Follow-up:** `tablero_kpis_consultas.py` calls private helpers of `tablero_asesores_consultas` (a gga note).

- **Delivery:** commits 8ceab58, f8b832b and 724231d, pushed to main.
- **Native review:** risk medium (900 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories, carried to the next writer as a backend commit 0**
  - R3-inventario-corte-global (WARNING): inventory uses the GLOBAL latest `fecha_corte`, so a store whose latest corte is older is dropped. **User decision (2026-10-04): keep the current behavior.** They load all stores in a single file per day, so a store missing from the latest file should not appear. Document it in the code; no change.
  - R3-pg-tests-global-state (WARNING): `test_tablero_kpis_b5_pg.py:181-187` depends on global DB state.
  - R3-costo-venta-hmcl (suggestion): the cost of sales includes HMCL (line 114). Fine, since days of inventory measure all outflow; document it.

**Test fix + F1, done.** Route: one delegated writer, two commits.
- **Commit 1969be1 (`test`):** the inventory-days pg tests are isolated to their own stores. Comments document that cost of sales includes HMCL and that inventory uses the global latest corte, both by design. The per-store-corte change was implemented and then reverted per the user's decision.
- **Commit b5b7c57, F1:**
  - `components/motored/kpis/`: `format.js`, `tokens.js`, and `charts/` with Gauge, Donut, ZoneStrip, BarList, DivergingBars, StackedArea, ShareTiles, StackedBar100, Heatmap, Treemap, Scatter, SegmentedToggle, KpiMiniGrid, TrafficLightGrid, plus Chip, RankBadge, geometry and the index.
  - Brand tokens in the `layout.js` themeCss.
  - Size: ~1,900 lines, one cohesive set.
- **TDD evidence:** RED: 2 suites failed on missing modules.
- **Checks**
  - Full jest: 168 suites / 1770 tests (before a `heatLevel` NaN guard; the chart suites re-ran afterwards, 60 passed).
  - pg_real `-k tablero_kpis`: 27 passed.
  - `/motored/maestros` returned 200 with the tokens present (`--webpack`).
  - After the rebase, the parent re-ran the charts and layout suites: 77 passed.
- **Open for F2:** Manrope is not loaded yet. `--motored-font-kpi` falls back to Mulish, and loading Manrope needs `layout.js` `next/font` plus an update to `motored-layout-metadata.test.jsx`.

- **Delivery:** commits 1969be1 and 846fe8e, pushed to main.
- **Native review:** risk medium (1,573 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories, carried to F2**
  - Gauge: numeric-string coercion mismatch (`Gauge.js:10-12`).
  - Scatter: a degenerate domain is not handled.
  - `stackLevels`: bucket boundary (`geometry.js:71-78`).

**Fix + F2 + F3, done.** Route: one delegated writer, three commits.
- **Commit 34d35da, fix:** Gauge coercion, Scatter degenerate domain, and the `stackLevels` edge.
- **Commit 0905388, F2:**
  - `kpisApi.js`, `useKpis` (per-tab cache and stale guard), `useKpiFiltros`, and the header with Período/Punto de venta/HMCL popovers.
  - KpiTabs; the sidebar and permisos label is now "KPI's"; Manrope is loaded via `next/font`.
  - The route stays `/motored/tablero-asesores`.
  - Temporary tabs: Tiendas shows "Próximamente"; Asesores shows the legacy table, `embedded`.
- **Commit 7c5ee5b, F3:** the Ventas tab per the design:
  - gauge + 6 KPIs;
  - zone strip;
  - semáforo/barras card;
  - stacked area by line + share tiles;
  - Tecnired donut, monthly bars, line mix and top 5.
- **Deviations:** the stacked area is taller; the Tecnired cards wrap on tablet; the Barras right column is 96px.
- **Checks**
  - Full jest: 172 suites / 1820 tests.
  - Webpack compile: 200.
  - Screenshots at 1440 and 1024 (synthetic fixture), copied to the user's `Documents\Motored\capturas_kpis`. The user approved the push.
- **Notes from gga:** `VentaPorLinea` has a duplicate import; `VentasTab` has an unused `filtros` prop.

- **Delivery:** commits 34d35da, 0905388 and aa6d750, pushed to main.
- **Native review:** risk medium (1,816 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories, carried to F4**
  - The period filter: unavailable months can get stuck selected (`PeriodoFilter.js:33-37`).
  - `useKpis` can fire duplicate in-flight requests (suggestion).

**Fix + F4 + F5 + F6 + label fix, done.** Route: delegated writers; five commits, rebased onto 88906e4.
- **Commit 7a4fbea, fix:** unavailable months are no longer stuck; `useKpis` dedupes in-flight requests; gga cleanups.
- **Commit 4fc8fcc, F4 Tiendas:**
  - tendencia donut + 6 KPIs (including días de inventario);
  - zone strip;
  - ranking with Venta, Crecimiento and Mezcla views;
  - heatmap vs the store's own average;
  - venta vs margen scatter.
- **Commit fae8e27, F5 Asesores:**
  - donut of who meets the target + 6 KPIs;
  - zone strip;
  - Top 10 by venta and Bottom 10 by cumplimiento, with Venta and Mezcla views;
  - Tecnired treemap + % bars;
  - venta por grupo (4 groups).
- **Commit bb8b512, F6:** the legacy tablero UI is removed; the backend endpoint is kept.
- **Commit 66b85ff, label fix:**
  - Scatter: `placeLabels` avoids collisions with other labels, the corner captions and dots, skipping a label that doesn't fit (the tooltip stays).
  - BarList: `valuePlacement` puts the text inside, outside or on the sub-line, so "venta / presupuesto" stays readable.
- **Deviations:** see the writer report. Highlights:
  - `globals.css` forces `td` centering, so names are wrapped in a block;
  - scatter domains are data-driven;
  - best/growth KPIs exclude tiny or new stores;
  - group sales show 4 groups.
- **Checks**
  - Full jest: 173 suites / 1830 tests.
  - Webpack compile: 200.
  - Screenshots, retaken by the parent after the label fix (synthetic fixtures): 0px horizontal overflow at 1440 and 1024. The user approved the push.
  - After the rebase, the parent re-ran the affected suites: 336 passed.

## Next step
Native review + push. Then a new feature: precomputed KPI summary tables (Ventas takes over 10 s in production; inventory is loaded weekly).
