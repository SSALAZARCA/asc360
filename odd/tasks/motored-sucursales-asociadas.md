# Motored: active flag, bodega moves and associated stores in Sucursales

## Objective
Let the owner load the corrected Sucursales file in one go, and model physical points that roll up into a principal store.

## Problem
- The Sucursales upload cannot mark a store inactive, so closed stores arrive active.
- A secondary bodega cannot move between stores in one upload, which forces a "release" upload first.
- Some points have their own C.O. (a different C.O. is a different store) but operate under a principal store. They need to count as that principal for everything without losing their own identity.

## Owner decisions (2026-10-04)
- A different C.O. is a different store.
- Closed stores load as inactive with an invented SIC.
- **Associated point → principal:** the point rolls up for EVERYTHING (ventas, inventario, presupuestos, vendedores). Only the principal gets a pedido, and KPIs show the principal with the totals.

## Agreement with the KPI session
- The column is `sucursal.principal_id`, a nullable self-FK where NULL means the store is its own principal. It has depth 1, so no chains.
- Helper: `principal_de(db) -> dict[sucursal_id, principal_id]`.
- Raw `sucursal_id` stays everywhere, and the rollup happens at read time.
- The KPI session wires KPIs, presupuestos and vendedores after the column lands on main.
- **Off limits:** `tablero_asesores*.py`, `tablero_kpis*.py`, `kpi_resumen*.py`, `api/tablero_kpis.py`, `frontend/components/motored/kpis/*`.

## Tasks

| ID | Task | Route |
|---|---|---|
| T1 | Strict "Activa" yes/no column in the Sucursales upload (blank keeps the current value; unknown text is a row error). Allow moving a secondary bodega between stores in one upload when the file also releases it. | delegated writer (5+ files) |
| T2 | `sucursal.principal_id` migration, depth-1 validation, `principal_de` helper, upload column "Sucursal principal", form field in Sucursales, health checks. Notify the KPI session. | delegated writer |
| T3 | Corridas rollup: `cargador.cargar_entradas` queries the store group; associated stores never get their own pedido; the group is frozen on the corrida for reproduction. | delegated writer |

- [x] T1
- [x] T2
- [x] T3
- [ ] T4 (edit secondary bodegas from the Sucursales screen)

## Constraints
- **Python 3.11, gga style:** lines of 79 characters or fewer, functions of 50 lines or fewer, no mid-file imports.
- **Frontend:** tablet layout, `<option>` style, tooltips for non-obvious fields.
- **Moving a bodega affects future uploads only.** Data already ingested stays under the old store. The owner must re-upload ventas and inventario.

## Checks
- **Backend:** `cd backend && .venv/bin/python -m pytest tests/motored -q` plus pg_real on a throwaway PG.
- **Frontend:** `cd frontend && npx jest`.
- Test-first applies to all three tasks.

## Log
- 2026-10-04: document created after mapping. The explorer's map is summarized in Engram `odd/motored-sucursales-asociadas/tasks`.
- 2026-10-04: T1 done.
  - Strict "Activa" column: validated in `validators._activa_error`, audited via `maestros._set_activa_sucursal`.
  - `_codigos_liberados` lets a secondary bodega move between stores in one upload. A replaced principal bodega can move too; one that is still the principal stays rejected.
  - RED observed first.
  - Results: tests/motored 5376 passed; pg_real 509 passed, 2 skipped (throwaway PG 18); jest 1835 passed. The parent spot check passed 77.
- 2026-10-04: the owner accepted the pedido rules ("se suma todo"). The 6 closed points will be associated by hand from the Sucursales screen, so no reprocess button is needed.
- 2026-10-04: T2 done.
  - Migration `a8c4e2f61d07`: `sucursal.principal_id` self-FK with ON DELETE RESTRICT, a CHECK that a store is not its own principal, and an index.
  - Depth-1 rule in `motivo_asociacion`, plus the `sucursal_grupo` helpers (`principal_de`, `grupo_de`, `principal_efectivo_expr`).
  - Upload column "Sucursal principal": blank keeps the value, "Ninguna"/"-" clears it.
  - Form select and table column in Sucursales.
  - Health checks: `asociada_principal_inactiva` and `asociada_activa` are warnings. `sucursal_sin_sic` now skips associated stores.
  - Results: tests/motored 5432 passed (after updating the 2 head-pin tests); pg_real 547 passed, 2 skipped (run with `-m pg_real`); alembic downgrade -1 and upgrade head both OK; jest 1851 passed. The parent spot check passed 67.
- 2026-10-04: T4 added by the owner: edit a store's secondary bodegas from the Sucursales screen (add/remove, same rules as the upload: no duplicates across stores, not another store's principal). Route: delegated writer, after T3, so only one writer runs at a time.
- 2026-10-04: T4 requirement: swapping a store's principal and secondary bodega (e.g. Quilichao BA071 <-> BA161) must work in ONE save, validated against the final state.
- 2026-10-04: T3 done.
  - Groups are frozen in `seleccion_datos["grupos"]` when the corrida is created.
  - `cargar_entradas` queries `.in_(miembros)` and merges tránsito across the group.
  - `_resolver_sucursales` keeps only principals. An explicitly selected associated store is rejected with E-CORRIDA-011.
  - Reproduction is unchanged: it uses the stored line inputs.
  - Results: tests/motored 5445 passed; pg_real 552 passed, 2 skipped. RED was observed on HEAD.
  - Pending: the corrida store picker in the frontend may still list associated stores. That goes into T4.
