# Motored: advisor dashboard (TABLERO ASESORES) and its data sources

## Objective
Replicate in Motored the user's Excel advisor dashboard (sheet TABLERO ASESORES). The analysis lives in Engram `motored/tablero-asesores-analysis` and `motored/tablero-asesores-data-plan`.

The dashboard needs four data sources beyond `venta_detalle`, which is already done in feature `motored-ventas-detalle`:
- cost per referencia,
- line per referencia,
- the Tecnired client list,
- the salesperson-to-advisor mapping.

## Problem / why
Today the indicators live in a 135 MB Excel that is rebuilt by hand. Motored already receives the sales and inventory uploads, so it can compute them.

## Decisions (user, 2026-10-01)
- **Inventory cost is REQUIRED.** The INVENTARIO header must include "Costo prom. uni." (the ERP export name).
- **One INVENTARIO upload feeds two tables,** mirroring venta_detalle:
  - `inventario_snapshot`: unchanged aggregate, read by the engine.
  - `inventario_detalle` (new): one row per file line, per bodega, with the cost.
- **Dashboard cost per referencia:** the median of positive costs across bodegas, as in the Excel's COSTO REFERENCIA sheet. It is computed by the reader from `inventario_detalle`.
- **Row-level cost problems never reject an inventory row.** A blank or negative cost still lets the existencia reach `inventario_snapshot`; the row is only excluded from cost statistics.
- **Line per referencia:** the user will reload `referencia.linea_comercial` with the 7 dashboard lines (REPUESTOS, ACCESORIOS, LLANTAS, LUBRICANTES, BATERIAS, GPS, CASCOS).
- **Advisors** are Motored users, linked through an explicit ERP-vendedor → Usuario mapping, with a "sin asignar" bucket and no fuzzy auto-matching.
- **CLIENTES TECNIRED** is a new upload in Maestros.

## Constraints (F3/F4 agent impact checks, 2026-09-30 and 2026-10-01)
- `inventario_snapshot` columns, its upsert and `consolidar_existencias` stay byte-for-byte unchanged. The engine reads only `sum(existencias)` by referencia.
- `inventario_detalle` rules:
  - Written in the same transaction as the snapshot upsert, set-based (no row-by-row insert).
  - Keyed by the resolved `sucursal_id` PLUS the raw bodega code. It keeps `existencia`.
  - Re-upload replaces by (fecha_corte, sucursal_id).
  - Anulación never deletes; readers filter ANULADO through `carga_id`.
  - Indexes: (fecha_corte, sucursal_id) and (referencia_id, fecha_corte).
- **Retention.** Purge `inventario_detalle` in the SAME job as `inventario_snapshot`, with the SAME `fecha_limite` (`services/retencion.py`). Purge the detail first, or in the same chunk transaction, and keep the `hay_job_activo` guard covering it.
- **Required test:** an INVENTARIO row with a blank cost still reaches `inventario_snapshot` with its existencia.
- **Detection.** INVENTARIO goes from 4 to 5 expected columns.
  - An old 4-column file scores 0.8: detected, then rejected for the missing column.
  - A VENTAS file declared as INVENTARIO scores 3/5 = 0.6 and still passes `verificar_tipo`. The dry-run rejects it for the missing Existencia/Costo, so keep a test for that.
- **CLIENTES TECNIRED** follows the 4-maestros pattern (`api/carga.py`, all-or-nothing). It stays out of the `vigencia.py` list and out of `TIPOS_MOVIMIENTO`.
- **Dashboard.** Its own router and RBAC. Never reuse `/api/motored/corridas*` (ADMIN/COMPRAS only, F4-16).
- **Sidebar.** If a sidebar item is added, ping the F3/F4 agent with the commit, because they will add a "Pedidos" item to `MotoredSidebar.js`.
- **Do not touch:** `services/corridas/*`, `api/corridas*.py`, `schemas/corrida.py`, `schemas/pedido.py`, `supervisor_corridas.ensure_started()`, or the "- copia" worktree.
- **Personal data (Ley 1581):** `cliente_factura` and `vendedor`. No new exposure beyond the roles that see sales.
- **Select options:** every new `<option>` needs `style={{ color: '#1a1a18' }}` for the dark theme. No backticks inside `themeCss` comments.
- **Tablet:** new screens must work at 768–1024px.

## TDD
- Mode: strict. Source: project rules and user memory. RED, then GREEN, then REFACTOR.
- Backend: `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`. The venv is Python 3.11.16, the same as prod.
- Also `-m pg_real` on a throwaway PG 18 (TCP 127.0.0.1, `unix_socket_directories=''`, deleted afterwards; do not use port 55432).
- Frontend: `cd frontend && npx jest`.

## Decisions (user, 2026-10-01, later the same day)
- **CLIENTES TECNIRED:** each upload replaces the full list.
- **"Maestro de vendedores":** named so it does not clash with the app's RBAC roles. Sellers absent from it go to RESTO COMPAÑÍA, as in the Excel; the dashboard still lists them so the user can add them.
- **Dashboard:** visible to ADMIN and COMPRAS only, with no per-sucursal view.
- **Retention:** option B, an auto-purge toggle plus days set in the app. It is built in the future admin Configuración screen (ADMIN only), see `odd/backlog/motored-configuracion-admin.md`. In this feature the purge stays env-gated.
- **Config rule:** business operation and calculations are set in the app. Server and technical settings stay in Coolify.

## Delivery
- Strategy: ask-on-risk.
- Each task is one or more work-unit commits, pushed to main (Coolify auto-deploys). The native review runs per commit when it is due.
- Tell the F3/F4 agent every new alembic head.

## Tasks
| ID | Task | Route | Status |
|---|---|---|---|
| T1 | INVENTARIO: required "Costo prom. uni.", the new `inventario_detalle` table, migration, set-based write in the same transaction, replace by (fecha_corte, sucursal), retention purge in the same job, template update, fixtures, pg_real tests. | delegated writer (2+ non-trivial files) | done (d64c4f3 on main) |
| T2 | CLIENTES TECNIRED upload in Maestros (backend 4-maestros pattern plus a frontend tab). Columns: NIT, razón social. Each upload REPLACES the full list. | delegated writer | done (9fdf3e3, not pushed) |
| T3 | "Maestro de vendedores": every person who sells, with or without an app user. Fields: ERP name (the "Nombre vendedor" join key, normalized), cargo, sucursal principal, cédula (optional), linked Usuario (optional). Loaded by Excel in Maestros and editable by hand. | delegated writer | done (71052cb, not pushed) |
| T4 | Dashboard endpoint and screen (indicators from the analysis, period and HMCL filters). Visible to ADMIN and COMPRAS only. Sellers not in the maestro group as RESTO COMPAÑÍA. | delegated writer | done (9f01c76 backend, 7eafa62 frontend, not pushed) |

- [x] T1 (commit d64c4f3 on main, rebased from 0f6106e)
- [x] T2 (commit 9fdf3e3, head d3b7f19a4c26)
- [x] T3 (commit 71052cb, head e8c2a5f17b93)
- [x] T4 (commits 9f01c76 and 7eafa62; advisory fixes in 02a3675; no new alembic head, still `e8c2a5f17b93`)

## Log
- 2026-10-01: feature document created. The two-table inventory design was confirmed by the user and by the F3/F4 agent.
  - The INVENTARIO path has no row cap; `MOTORED_MAX_UPLOAD_ROWS` applies only to `api/carga.py` maestros.
  - The real 3-Sep inventory export has 58,819 rows and 7,871 refs; only 1,728 of 5,402 multi-bodega refs have a uniform cost, and 811 rows have a negative cost.
- 2026-10-01: T1 done, commit `0f6106e` (not pushed). New alembic head `c4a9e7d1b852` (inventario_detalle, chained on `b8e2d4a1c735`): tell the F3/F4 agent.
  - RED (before implementing): 30 failed / 3619 passed in tests/motored (new detail, cost, retention, template and apply tests; the missing symbols and the 4-column header failed).
  - GREEN: tests/motored 3649 passed; full backend suite 4945 passed; pg_real on a throwaway PG 18 (migration upgrade, downgrade -1 and upgrade again): 234 passed, 2 skipped, including the 5 new tests in `pg_real/test_inventario_detalle_pg.py`.
  - Decisions:
    - A blank, invalid, too-large (>= 1e14) cost is stored as NULL, with no warning: no warning mechanism exists for per-row non-blocking notes, so none was invented. A negative cost is stored as-is. Readers must exclude NULL and <= 0.
    - Optional extras `fecha_ultima_entrada` / `desc_tipo_inventario` were skipped: the exact ERP header names are unknown and are not in the table. Add them later through `COLUMNAS_OPCIONALES_POR_TIPO` plus a migration.
    - `bodega` is stored raw, trimmed and cut to 20 chars; a blank bodega is stored as an empty string.
    - Rows staged by an older version (payload without `bodega`) are skipped by the detail write but still feed the snapshot.
    - Retention: one ledger row per table in `retencion_ejecucion` (`inventario_detalle` first, then `inventario_snapshot`, which stays the scheduler anchor and the returned row).
    - Cost parsing reuses `ventas._limpiar_moneda` and `_VALOR_MAX_ABS` (gga suggested moving them to `numeros.py` if a third caller appears).
    - No frontend change: no file lists the INVENTARIO columns (the template comes from the backend).
- 2026-10-01: T1 native review (medium risk) granted by the user, approved on the reliability lens and acknowledged. Rebased on main 40994b0 and pushed as d64c4f3 + 74ea4c1. Post-rebase `tests/motored`: 3800 passed. New head: `c4a9e7d1b852`.
  - Advisory follow-up: blank, invalid or too-large costs become NULL silently. Add a count of null costs to `carga.log` so the user can see when the cost base shrinks.
- 2026-10-01: T2 and T3 done in worktree "- encuesta" (branch feat/motored-encuesta-satisfaccion), NOT pushed. Commits: T2 `9fdf3e3`, T3 `71052cb`. Alembic chain: `c4a9e7d1b852` -> `d3b7f19a4c26` (cliente_tecnired) -> `e8c2a5f17b93` (vendedor): tell the F3/F4 agent the new head `e8c2a5f17b93`.
  - RED (before implementing): T2 `test_clientes_tecnired.py` failed at collection (`ModuleNotFoundError: app.motored.models.cliente_tecnired`) and the T2 jest suite failed to run (`Cannot find module ClientesTecniredTab`); T3 `test_vendedores.py` failed at collection (no `app.motored.models.vendedor`) and the T3 jest suite failed to run (`Cannot find module VendedoresTab`). Only after those did the implementations land.
  - GREEN: tests/motored 3872 passed (3800 baseline + 29 T2 + 43 T3); full backend suite 5168 passed (final run after the gga fixes); pg_real on a throwaway PG 18 (migration upgrade, `downgrade -1`, upgrade again for both migrations): 272 passed, 2 skipped, including 4 new Tecnired and 6 new vendedor pg_real tests; full jest 112 suites / 875 tests passed. `next lint` does not exist here (Next 16, no ESLint config): skipped. gga review passed on both commits (the first T3 attempt was rejected for a misleading helper name, an uncaught unique-index race and long lines; all three were fixed, with 409 tests for the race).
  - Decisions not covered above:
    - CLIENTES TECNIRED: duplicate NITs in the file are DEDUPED (first row wins) with a per-row warning, not an error. An empty file (zero rows) is REJECTED so it can never wipe the list. Replace = `DELETE` all + ORM inserts in one transaction, one commit; no per-row audit rows (`created_by` records who loaded it). NIT normalization is trim + remove internal spaces + remove trailing "." + remove a trailing ".0" (Excel numbers). `CargaResultado` gained `eliminados` (rows replaced). Read-only list endpoint `GET /api/motored/clientes-tecnired` (paginated, ADMIN|COMPRAS); no delete-all and no manual add.
    - Vendedores: `cargo` is normalized to UPPERCASE with collapsed spaces (max 80). A duplicated vendedor in the same file (same `normalizar_vendedor` key) is a row ERROR. Sucursal in the Excel is resolved by `normalizar_texto_sucursal` (name, `MR ` prefix, or `sucursal_alias`); an unknown value is a row error. The upload upserts by `nombre_norm` and never touches `nombre`, `usuario_id` or `activo` of an existing person (a blank cell keeps the stored value). Dedicated router `/api/motored/vendedores` (ADMIN|COMPRAS): list with `q`/`cargo`/`activo`, create (409 on duplicate name, also on the unique-index race), PATCH (explicit `null` unlinks sucursal/usuario), DELETE = deactivate, `POST /{id}/reactivar`, `GET /sin-registrar` (max 500, ordered by lines; inactive maestro people count as registered), `GET /usuarios-disponibles` (id, nombre, role only; no emails).
    - Frontend: tabs "Clientes Tecnired" and "Vendedores" in group Maestros; `BulkUploadModal` got a readable title map and a replace warning for Tecnired. No sidebar item was added (no ping needed for `MotoredSidebar.js`).
  - Not done: real-browser tablet check (768-1024px) of the two new tabs (no live backend to log into; jsdom cannot verify layout). Both tables sit in `MotoredTableScroll` and the forms wrap with flex-wrap.
- 2026-10-01: T2+T3 native review (medium risk, one consolidated candidate) granted by the user, approved on the reliability lens and acknowledged. Rebased on main de11e81 and pushed as a929a26 (T2), 7d6568d (T3) and 1c233eb (docs). Post-rebase `tests/motored`: 3872 passed. Frontend jest: 961 passed. New head: `e8c2a5f17b93`.
  - Advisories, to fix as a small `fix` commit before T4:
    1. `GET /vendedores/sin-registrar` must exclude NULL or empty `vendedor_norm`.
    2. `normalizar_nit` must be idempotent (it runs twice).
    3. Concurrent Tecnired replaces raise an uncaught IntegrityError, giving a 500; return a 409 instead.
    4. POST/PATCH `/vendedores` responses return null `sucursal_nombre`/`usuario_nombre`.
  - Not done: a real-browser tablet check of the two new tabs.
- 2026-10-01: review advisories of T2/T3 fixed in `02a3675` (before T4): `sin-registrar` excludes NULL/empty `vendedor_norm`; `normalizar_nit` is idempotent (loops to a fixed point); a concurrent Tecnired replace is a 409 (message names "otra carga", rollback done, raised from `_reemplazar_lista` so it covers JSON and Excel uploads); POST/PATCH `/vendedores` return the real `sucursal_nombre`/`usuario_nombre` (one extra query after the commit, skipped when neither is linked).
- 2026-10-01: T4 done in worktree "- encuesta", NOT pushed. Commits: fix `02a3675`, backend `9f01c76`, frontend `7eafa62`. No migration (head stays `e8c2a5f17b93`). Sidebar: ONE item "Tablero asesores" (icon `BarChart3`, roles ADMIN and COMPRAS) right after "Pedidos" in `MotoredSidebar.js` (+1 import): tell the F3/F4 agent the commit `7eafa62`; the existing `motored-pedidos-sidebar.test.jsx` expectation "Maestros right after Pedidos" was updated to Pedidos, Tablero asesores, Maestros.
  - RED (before implementing): fix tests, 7 failed (4 `normalizar_nit`/409/sin-registrar/names behaviours) plus the pg_real `sin-registrar` test failed against the old endpoint; T4 pure-calc tests failed at collection (`ImportError`, no `tablero_asesores` module); the frontend suites failed (`Cannot find module .../tablero-asesores/page`, and 3 sidebar tests failed). The pg_real T4 tests were written together with the first query draft: their first run failed on a SQL `GroupingError` (total variants) and on one of my hand-computed values (top-5 clients, my arithmetic slip: 5600, not 5500); the empty-range case later failed with a NULL sum, fixed with `coalesce`.
  - GREEN: `tests/motored` 3940 passed (3872 baseline plus the new fix, calculation and API tests; run before the frontend commit, no backend change since); full backend suite 5236 passed; pg_real on a throwaway PG 18 (no migration needed, head `e8c2a5f17b93`): 282 passed, 2 skipped, including 9 new tablero tests and the new `sin-registrar` one; full jest 121 suites / 990 tests passed (one unrelated suite, `motored-bulk-upload-referencia-csv`, failed once under load and passed on its own re-run).
  - Design:
    - The SQL does all aggregation with GROUP BY (never lines in Python): one "cubo" query by (fila, mes, linea, HMCL/Tecnired/mostrador/con-costo flags) plus facturas (distinct nro_documento + sucursal, per-line marks, multi-line), clientes (distinct + top 5 by window function) and personas. `tablero_asesores.py` is pure (grouping, var 3M, ranks, ratios), `tablero_asesores_consultas.py` is the SQL, `api/tablero_asesores.py` the router (prefix `/tablero-asesores`, `require_roles("ADMIN","COMPRAS")`, own router, never `/corridas*`).
    - The cargo -> group map is ONE constant, `tablero_asesores.GRUPO_POR_CARGO`; the SQL CASE that assigns the row is generated from it.
    - The line is normalized once per referencia in a MATERIALIZED CTE (not per sales line); client NIT normalization in SQL is `regexp_replace` and a pg_real test compares it with `normalizar_nit` on 11 samples.
    - Median unit cost = `percentile_cont(0.5)` over positive costs of the latest `fecha_corte` of a non-ANULADO inventory carga; kept in `_subconsulta_costos`. No SQLite fallback: this suite never executes aggregate SQL outside pg_real (sessions are fakes), so a portable path would be untested code.
    - Tablero payload: all `pct_*`, `mix` and `indice` are FRACTIONS; a zero denominator is `null` (shown as a dash), never 0. Extra fields: `venta_sin_linea`, `pct_venta_sin_linea`, `fecha_corte_costos`, `meses`, `meses_disponibles`.
  - Decisions not covered above:
    - Only people WITH sales in the range appear as rows (maestro people with no sales are not listed with zeros); "(n personas)" counts distinct sellers with sales in the range and filters, not the whole maestro. Ranks and the average ("índice vs promedio") are computed among those rows; ties share the position (like Excel RANK).
    - `venta_sin_linea` respects the HMCL filter and the month range; every other indicator ignores lines outside the 7.
    - Descuentos and "mes con más descuento" only count lines of the 7 recognized lines (an excluded line's discount is excluded too).
    - The frontend gate reuses `usePedidosGate` (ADMIN and COMPRAS, same rule). Default range = last 6 months ending in the current month; an invalid range is explained locally and not sent. The fetch helper lives in `components/motored/tablero-asesores/tableroApi.js` (new file) so `lib/motored/api.js` stays untouched.
    - `percentile_cont`/`translate` only strip the accents of `ÁÉÍÓÚÜ` in SQL (enough for the 7 lines).
  - Performance (synthetic, local PG 18 in WSL, default config, no tuning): 1M `venta_detalle` lines over 6 months with 875k invoices, 17.5k clients and 300 sellers: the whole tablero takes about 10 s with HMCL "incluir" (cubo 3 s, facturas 2x1.3 s, clientes 2x1.9 s, personas 1 s) and about 4 s with "solo". Before moving the line normalization to a per-referencia CTE it took 19 s. Real data (more lines per invoice, fewer invoices) should be lighter. If this is too slow in production, the next lever is a per-month cached aggregate; not built.
  - Not done: a real-browser or tablet (768-1024px) check of the new screen: no live backend to log into and jsdom cannot judge layout. The table sits in `MotoredTableScroll` with three sticky columns (fixed widths 150/250/210 px, 610 px in total) and the filters wrap with flex-wrap, so on a 768px tablet the sticky block takes most of the width: worth a real look.
  - gga review passed on all three commits (the first backend attempt was rejected for an unused import and the single-letter variable `l`; both fixed). Non-blocking gga notes left as they are: `_constante` guards with `assert` (only code constants reach it), `_indicadores` is about 60 lines of one dict.
- 2026-10-01: follow-up units (worktree "- encuesta", NOT pushed; no migration, head stays `e8c2a5f17b93`). Commits: TALLER fix `08a2b21`, dashboard fixes `e6eb1c9`, tablet fixes `9664efe`, plus a small docs/comment commit.
  - **Unit 1, TALLER sales never reached `venta_mensual`.** Cause: default `tipos_inventario_incluidos` was `["0002 - REPUESTOS"]`, so IRPTOSYACC and IVNLUBGR (the ERP's TALLER tags) were dropped and the engine's TALLER origen was 0.
    - New default `["0002 - REPUESTOS", "IRPTOSYACC", "IVNLUBGR"]` in BOTH places that hold it: the registry (`parametros_claves.py`) and the resolver fallback (`parametros.DEFAULT_TIPOS_INVENTARIO_INCLUIDOS`, the one that really applies when no row exists). A test pins that they match. "0003 - OTROS" stays out.
    - `venta_detalle` now keeps every approved line: tipo-excluded rows are staged with payload `solo_detalle: true`. `agregar_unidades`, the period histogram, `fecha_maxima_de_filas`, `filas_validas` and the out-of-period carga_error pass ignore them. Proven by tests: a 0002-only file and the same file plus 0003 rows give identical log (minus the new `filas_solo_detalle` key, written only when > 0), `fecha_max_detectada`, `filas_validas`, period and errors.
    - Decision: a detail-only row with any problem (bad date or cantidad, blank detail field, unresolved sucursal or referencia) is skipped silently with no carga_error; only the count `log.filas_solo_detalle` of stored ones is kept. Rows of an included tipo keep the old behaviour (a blank detail field still rejects the row; known advisory, not changed).
    - RED: `test_ingesta_ventas_taller.py` 9 failed / 14 passed before the code; the pg_real mixed-file test failed against the old `ventas.py` (restored temporarily). One existing test (`test_tipo_inventario_no_incluido_se_descarta_en_silencio`) changed meaning and was rewritten. MOSTRADOR+TALLER summing in the cargador is already covered by `pg_real/test_cargador_pg.py` (lines 149-153).
    - Deploy: a `parametro_metodologia` row for `tipos_inventario_incluidos` overrides the default. Check: `SELECT clave, valor, vigente_desde FROM parametro_metodologia WHERE clave='tipos_inventario_incluidos';`. Cargas already applied are not fixed retroactively; re-upload the months to get TALLER.
  - **Unit 2.** `useTableroAsesores` resets `loading` when the range turns invalid mid-request (RED: jest test failed); date-dependent range test fixed; `hmcl` filter treats NULL `cliente_factura` as non-HMCL (`coalesce` inside `_expr_es_hmcl`; RED: pg_real test returned NULL). New `useTableroGate` (ADMIN, COMPRAS) replaces `usePedidosGate` in the dashboard (`usePedidosGate` untouched); test shows it allows ADMIN and COMPRAS, denies SUCURSAL, and does not follow a widened Pedidos gate (RED: module missing).
  - **Unit 3, real screenshots** (headless Chrome via puppeteer-core, Next dev server with `--webpack` because Turbopack rejects the symlinked node_modules, API stubbed by request interception, no real backend), widths 768, 1024, 1440, saved under the scratchpad `tablet-shots/`.
    - Found: at 768 the three sticky columns (610px) left about 120px of data room. Fix: under 1024px only the asesor column is fixed (and first, 140px); re-shot, about 300px of data room, readable.
    - Found: at 1440 the Maestros tab bar (12 tabs) widened the page by 111px (old tabs plus the 2 new ones). Fix: the bar scrolls in its own box (`overflowX: auto`); re-shot, no page overflow at any width. Open: the scrollable bar has no visual hint that more tabs exist (Movimientos tabs sit beyond the visible edge at 1024 and 1440).
    - Vendedores and Clientes Tecnired tabs: fine at 768 and 1024 (forms wrap, tables fit).
  - GREEN: `tests/motored` 3963 passed; full backend 5259 passed; pg_real on throwaway PG 18 (port 55871, deleted afterwards): 284 passed, 2 skipped; full jest 133 suites / 1181 tests passed. gga passed on every commit.
