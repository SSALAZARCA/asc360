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

## Delivery
- Strategy: ask-on-risk.
- Each task is one or more work-unit commits, pushed to main (Coolify auto-deploys). The native review runs per commit when it is due.
- Tell the F3/F4 agent every new alembic head.

## Tasks
| ID | Task | Route | Status |
|---|---|---|---|
| T1 | INVENTARIO: required "Costo prom. uni.", the new `inventario_detalle` table, migration, set-based write in the same transaction, replace by (fecha_corte, sucursal), retention purge in the same job, template update, fixtures, pg_real tests. | delegated writer (2+ non-trivial files) | done (0f6106e) |
| T2 | CLIENTES TECNIRED upload in Maestros (backend 4-maestros pattern plus a frontend tab), with replace semantics pending the user's decision. | delegated writer | pending decisions |
| T3 | Salesperson → advisor mapping (table, API, UI). Cargo handling pending the user's decision. | delegated writer | pending decisions |
| T4 | Dashboard endpoint and screen (indicators from the analysis, period and HMCL filters). Roles pending the user's decision. | delegated writer | pending decisions |

- [x] T1 (commit 0f6106e)
- [ ] T2
- [ ] T3
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
