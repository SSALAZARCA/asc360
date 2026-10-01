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
| T4 | Dashboard endpoint and screen (indicators from the analysis, period and HMCL filters). Visible to ADMIN and COMPRAS only. Sellers not in the maestro group as RESTO COMPAÑÍA. | delegated writer | ready |

- [x] T1 (commit d64c4f3 on main, rebased from 0f6106e)
- [x] T2 (commit 9fdf3e3, head d3b7f19a4c26)
- [x] T3 (commit 71052cb, head e8c2a5f17b93)
- [ ] T4

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
