# Motored: precomputed KPI summary tables

Engram mirror: `odd/motored-kpis-resumenes/tasks` (project asc360).
Builds on: `odd/tasks/motored-kpis.md` (complete). Design exploration: 2026-10-04 (summarized below).

## Objective
Make the KPI's tabs load in ≤2 s (today Ventas takes over 10 s in production with "Año corrido"). KPI endpoints should read small precomputed summary tables, refreshed automatically when their inputs change, with identical results to the live queries.

## Why
Each tab scans `venta_detalle` (~1M rows Jan–Sep) 6–8 times per request, with regexp client normalization and a percentile cost CTE repeated on every request. The per-session cache only helps repeat visits by the same viewer.

## Decisions
**Confirmed by the user**
- Summaries refresh automatically, with no manual step for the user.
- Inventory with cost is loaded **weekly**, before each pedido. A full background rebuild of the cost summaries on each inventory upload is fine.
- Safety nets:
  - a nightly full rebuild;
  - an ADMIN "Recalcular" action;
  - an "actualizado a las HH:MM" timestamp shown on the KPI's page.

**Defaults** (from the exploration; the user may override)
1. **Store raw dimensions** that don't depend on Configuración (`vendedor_norm`, `linea_norm`, `nit_especial`) and apply Configuración (`lineas_comerciales`, `hmcl_nits`, `grupo_por_cargo`, semáforo) at read time. This keeps the "last selected month" vigencia rule correct.
2. **Incremental refresh** of the affected (sucursal, año, mes) keys runs inside the same transaction as the VENTAS carga apply, and synchronously on carga anular.
3. **Full async rebuild**, marked dirty and done by a background loop, when any of these change:
   - a referencia's `linea_comercial` (single edit or the Excel replace);
   - the cliente_tecnired list;
   - `hmcl_nits` or `lineas_comerciales` parameter writes;
   - an inventory carga apply or anular.

   A delay of up to a few minutes after these changes is acceptable.
4. **No rebuild** for vendedores, sucursales, bodegas or presupuestos: they are resolved or read at query time.
5. **Feature flag and fallback:** the live queries stay as the fallback when summaries were never built, or are dirty and have never finished.
6. **Facturas** use a per-invoice "line signature" summary, so `pct_con_linea`, `pct_multilinea` and `items_por_factura` stay exact. If invoices turn out to span months or clients in a way that breaks it, use one row per invoice instead.
7. **Distinct clients** come from a (mes, sucursal, vendedor_norm, cliente_norm, linea_norm) table with venta, and are counted with `COUNT(DISTINCT)` at read time. This is exact, not an estimate.

## Proposed tables (alembic_motored; the head today is `d7a2f4b8c915`, re-check at write time)
- **`kpi_venta_mes`**
  - Keys: (`anio_mes`, `sucursal_id`, `vendedor_norm`, `linea_norm`, `nit_especial`, `es_mostrador`, `con_costo`).
  - Measures: venta, bruto, descuentos, cantidad, lineas, costo.
- **`kpi_factura_firma`**
  - Keys: (`anio_mes`, `sucursal_id`, `vendedor_norm`, `nit_especial`, `firma` text[] of sorted distinct `linea_norm`).
  - Measure: `n_facturas`.
- **`kpi_cliente_mes`**
  - Keys: (`anio_mes`, `sucursal_id`, `vendedor_norm`, `cliente_norm`, `linea_norm`).
  - Measure: venta.
- **`kpi_costo_referencia`:** (`fecha_corte`, `referencia_id`, `costo_unitario` median of positive costs).
- **`kpi_inventario_corte`:** (`fecha_corte`, `sucursal_id`, valor, `lineas_sin_costo`).
- **`kpi_resumen_estado`:** a single row with `sucio`, `actualizado_en`, `reconstruyendo`, `ultima_reconstruccion_total`.

## Scope
**In scope**
- The tables, the build/refresh service, the triggers, the read paths for the ventas/tiendas/asesores/opciones endpoints, the nightly loop, the ADMIN recalcular endpoint, `actualizado_en` in the responses, and the UI timestamp plus button.
- Equivalence tests (summary vs live) on pg_real.

**Out of scope**
- New KPIs or UI changes beyond the timestamp and the Recalcular button.

## Constraints
- **Coordination:** session -c4 owns ingesta (`bodegas_excluidas` on main), presupuestos (the Año/Mes columns change in progress) and CI (`.github/`). Hooking triggers into `services/ingesta/ventas.py` `aplicar_detalle`, `api/cargas.py` anular, `services/maestros.py`, `services/reemplazo_referencias.py` and `services/parametros.py` touches shared files, so tell -c4 before that task and rebase before every push.
- **CI gate:** once it is on, a red CI blocks deploys for both sessions. Keep unit, pg_real and jest green.
- **Write-path audit:** list every write path with rg BEFORE wiring triggers (project memory: enumerate before editing shared state).
- **Runtime:** Python 3.11. Keep the unit and pg_real suites in separate envs.
- **Indexes:** never use `date_trunc` in a WHERE on `venta_detalle`; summary tables get their own indexes on (`anio_mes`, `sucursal_id`).

## Test-first
- Backend: `cd backend && env -u MOTORED_TEST_PG_URL -u MOTORED_DATABASE_URL .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`.
- pg_real: throwaway PG 18, run separately.
- Frontend: `npx jest`.
- Equivalence tests are the acceptance criterion for every read path.

## Delivery
- Each task becomes a work-unit commit, gets native review, and is pushed to main.
- Forecast: ~3,000 authored lines over 8 tasks.

## Cost rule (user decision 2026-10-04)
**Unit cost per referencia** = the median positive `costo_unitario` from the latest non-annulled inventory corte. When the referencia is absent from that inventory, or its cost is null/≤0, the cost falls back to `referencia.precio_normal` (if > 0). Otherwise it has no cost.
- Track the source (`inventario` | `maestro`) so the UI can show how much of the margin is estimated.
- Inventory valuation for días de inventario uses the same fallback for inventory lines without a cost.
- Apply the rule in BOTH the live queries and the summaries, so the equivalence tests hold.

## Tasks
- [ ] **C1 Cost fallback in the live path** (before R3). `_subconsulta_costos` and the TKC inventory/cost-of-sales queries fall back to `precio_normal`. Expose `venta_costo_maestro` / `pct_costo_estimado` in the margin block. In the UI, add a margin tooltip showing the estimated %. Tests.
- [x] **R1 Tables + models + migration.** The 6 tables, indexes and models. The migration only creates tables; the backfill is done by the rebuild.
- [x] **R2 Build/refresh service** `services/kpi_resumen.py`: full build and per-(sucursal, año, mes) refresh from `venta_detalle` (non-annulled cargas), a costs build, the estado row, and an advisory lock. pg_real tests: a summary built from a seeded world equals the raw aggregates.
- [ ] **R3 Read path for `kpi_venta_mes`.** Cube (all dimensions), growth window, cost of sales, months available, personas venta. Behind the flag, with a fallback to live. Equivalence tests.
- [ ] **R4 Read path for facturas (firma) + clientes (`kpi_cliente_mes`)**, including Tecnired clients and top-5. Equivalence tests incl. HMCL modes, store filter and a Configuración change.
- [ ] **R5 Costs + inventory summaries** and their use in margin and días de inventario. Equivalence tests.
- [ ] **R6 VENTAS carga triggers.** Incremental refresh inside apply, sync refresh on anular. Write-path audit first; coordinate with -c4.
- [ ] **R7 Full rebuild orchestration.** Dirty flag set by referencias/linea, Tecnired, `hmcl_nits`/`lineas_comerciales` and inventory triggers; a `supervisor_kpis` loop (nightly plus dirty); ADMIN `POST /tablero-asesores/kpis/recalcular`; `actualizado_en` in the responses.
- [ ] **R8 Frontend + perf verification.** "Datos actualizados a las HH:MM" and an ADMIN "Recalcular" button on the KPI's page. Measure endpoint timings (before/after) on a large synthetic dataset in pg_real and record them.

## Progress / evidence
**R1 + R2, done.** Route: one delegated writer, two commits, rebased onto 8b1823b.
- **Commit fa60d5b, R1:** migration `e3b7d1a94c26_kpi_resumen` (down `d7a2f4b8c915`) creates the 6 tables.
  - `vendedor_norm` is NOT NULL; nullable `linea_norm`/`nit_especial` use unique `COALESCE(col,'')` expression indexes.
  - Each table has a surrogate bigint identity PK.
- **Commit 99147d6, R2:** `services/kpi_resumen.py` provides `refrescar_periodos`, `reconstruir_todo`, `reconstruir_costos`, `marcar_sucio` and `estado`.
  - One `pg_advisory_xact_lock(LOCK_KEY)` serializes all rebuilds; DELETE (not TRUNCATE) keeps readers on the old rows until commit.
  - `linea_norm` and `nit_especial` collapse against the union of all historical config values (+ defaults) and `cliente_tecnired`.
  - Only the latest inventory corte is kept.
  - Cost fallback to `precio_normal`: `kpi_costo_referencia.fuente` ('inventario'/'maestro'), `kpi_venta_mes.costo_estimado`, and `kpi_inventario_corte.lineas_costo_maestro`.
  - Invoice `firma` may be empty (unrecognized lines only); R4 must intersect it with the current lines and drop empty ones.
  - `reconstruyendo` is unused until R7.
- **TDD evidence:** RED on the migration chain/create/downgrade and head asserts; import errors before the service existed.
- **Checks**
  - Unit suite: 5295 passed.
  - pg_real: 522 passed / 2 skipped.
  - After the rebase, the parent re-ran the summary/migration unit tests: 23 passed.

## Next step
Native review + push of R1/R2, then C1 (cost fallback in the live path) + R3.
