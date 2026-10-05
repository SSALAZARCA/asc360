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
- [ ] T2
- [ ] T3

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
