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
- [x] T5 (store code C.O.: owner asked for it at the start; I wrongly deferred it)
- [x] T5b (C.O. is the sucursal business key: upload matches stores by C.O., name is a mutable attribute; C.O. required in upload and form; first upload backfills by name for stores without C.O.; "Sucursal principal" accepts C.O.)
- [x] T4 (edit secondary bodegas from the Sucursales screen)
- [x] T6 (REINSTATED, owner confirmed verbatim): VENTAS ingest resolves the sucursal by the row's C.O.; bodegas_excluidas checked first; bodega only as fallback for files without C.O.; unknown C.O. = row error; non-store C.O. (MR/PAF01) needs an exclusion. No re-upload of old ventas. Runs after T5 (single writer); coordinate ventas.py with the KPI session (R6).
- [ ] T7 (presupuestos and vendedores recognize the store by C.O., name as fallback). KPI session files: coordinate; they may implement it.
- [ ] T8 (per-store data-control report for the owner before the first pedido)
- [x] T9 (BUG found while validating the owner file): the Sucursales upload and form never sync the `bodega` record of a store's PRINCIPAL bodega. A moved principal (BA071 → A07, BC111/BA011/... → new stores) keeps a stale or NULL `sucursal_id`, and secondaries chain to it via `bodega_principal`, so inventory resolves to the wrong store or none (MCD01, MCB11). Fix: when a store's principal is set or changed, upsert that bodega record with sucursal_id = store and bodega_principal = NULL, and re-point the old record. MUST land before the owner uploads.

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
- 2026-10-04: owner rule: the C.O. identifies the sucursal. Ventas, KPIs and pedidos fall on the sucursal by C.O.; bodegas belong to sucursales. Added T6 and T7.
- 2026-10-04: the owner clarified that a sale goes to the sucursal that owns the bodega, so the 892 cross-store rows go to the bodega's sucursal. T6 is cancelled and VENTAS ingest is unchanged.
- 2026-10-04: the owner confirmed verbatim: "Cada venta se registra en la sucursal de su C.O. (columna G), sin importar de qué bodega salió el repuesto." T6 is reinstated. The earlier cancellation came from my misunderstanding. Ventas already loaded will not be re-uploaded.
- 2026-10-04: T8 added: a per-store data-control report (bodegas, 6-month ventas, stock, associated points, anomalies) for the owner to approve before the first pedido.
- 2026-10-04: T5 done.
  - Migration `b5d9e3a7c418` adds `sucursal.codigo_co`, unique and DEFERRABLE (so codes can swap in one upload). Format `^[A-Z][0-9]{2}$`.
  - Upload column "Código C.O." placed after Nombre. Form input and table column added.
  - Non-blocking health warning `sucursal_sin_codigo_co`.
  - The 422 response no longer becomes a 500 on schema errors.
  - Results: tests/motored 5493 passed; pg_real 559 passed, 2 skipped; jest 1859 passed.
- 2026-10-04: independent audit of T1–T3 (cd7797f vs 2bd7596).
  - With no associations, pedido output is invariant: the queries differ only in `= X` vs `IN (X)`.
  - Uploads and KPIs are unchanged. Migration is safe, with no table rewrite.
  - Low risks recorded:
    - `start.sh` starts the server even when a migration fails.
    - A JSON upload can carry a raw `principal_id` that is not checked against other rows in the same file.
    - Associated stores without a SIC are no longer flagged.
- 2026-10-04: the owner stated that the C.O. identifies the sucursal and the name can change, so the name must not be the key. Added T5b: the C.O. becomes the business key.
- 2026-10-04: T5b done.
  - The upload matches stores by C.O. It falls back to the name only for stores without a C.O., and renames work through a temporary name.
  - The C.O. is required on every upload row and in CRUD create, and a stored C.O. cannot be cleared.
  - "Sucursal principal" accepts a C.O. or a name.
  - The C.O. column is first in the template.
  - Out-of-surface tests (rbac matrix, reemplazo api) were updated by the parent.
  - Results: tests/motored 5516 passed plus the 3 fixed; pg_real 578 passed, 2 skipped; jest 1867 passed.
  - Follow-up: make `codigo_co` NOT NULL and the check blocking after the owner's backfill upload.
- 2026-10-04: final owner file v2 built (`Documents/Motored/Sucursales_carga_final_v2_2026-10-04.xlsx`): 48 stores, one per sales C.O. (MR and Z01 excluded), C.O. first; new stores A07 and C11 with invented SICs 9008 and 9009; A16 principal BA161; A11 inactive. It validates with 0 errors, but emulating the result exposed bug T9. The upload is blocked until T9 lands.
- 2026-10-04: T6 done.
  - VENTAS rows resolve the sucursal by C.O. when the file has that column: aliases C.O., CO, Centro de operación. The `bodegas_excluidas` check runs first.
  - A blank C.O. falls back to the bodega and is counted in `filas_co_vacio`.
  - An unknown C.O. returns the new error `CO_NO_ENCONTRADO`.
  - The parent added PAF01 (the administrative non-store bodega, C.O. MR) to the default `bodegas_excluidas`.
  - Results: tests/motored 5560 passed; pg_real 600 passed, 2 skipped (writer run).
- 2026-10-05: T9 upload path done.
  - `bodegas_secundarias.sincronizar_principales` runs last in the Sucursales upload. It makes each principal record the root of its store, chains the store's other records to that root, and cuts foreign chains to it.
  - In the owner scenario every bodega resolves to its new store, in both row orders.
  - Results: tests/motored 5575 passed; pg_real 603 passed, 2 skipped.
  - Pending: the CRUD form path in `maestros.py` has the same bug. It goes into T4, after the KPI session's R7 lands. Call `sincronizar_principales` from `api/maestros.py` after create or update.
- 2026-10-05: the KPI session's R7 is on main (785ac8c), so `maestros.py` is free for T4 and the T9 form path.
  - Note for T4 tests: `maestros.update_referencia` and `reemplazar_clientes_tecnired` now call `kpi_resumen.marcar_sucio_si_construido`. FakeAsyncSession tests on those paths need the `_sin_marca_de_sucio` stub.
  - The new `supervisor_kpis` loop holds an advisory lock while it rebuilds. A VENTAS apply can then wait up to 60 s and fail with "try again".
  - Stopped for the day at the owner's request.
- 2026-10-05: hotfix 93cfaef.
  - Uploading v2 failed in production with `bodega_sucursal_id_fkey`, shown to the owner as "otra carga".
  - Cause: autoflush is off and there is no relationship between bodega and sucursal, so new stores were not yet INSERTed when their bodegas pointed at them.
  - Fix: flush right after the renames in `_aplicar_columnas_de_sucursal`.
  - Regression test: `test_sucursal_carga_autoflush_pg.py`, with a production-like session. RED reproduced the error, then GREEN; pg_real 627 passed.
  - Follow-up: make the IntegrityError handler surface the real constraint, and switch the pg_real Sucursales fixtures to `autoflush=False`.
- 2026-10-05: T4 done.
  - `bodegas_secundarias` is optional in sucursal create/update, so a swap happens in one atomic save.
  - Shared rules: `normalizar_codigos` and `guardar_de_sucursal`. A code owned by another store is rejected with a message that names that store.
  - The form path syncs principals in `api/maestros._guardar_bodegas`. The list payload includes the secondaries (one extra read).
  - Chips editor in `SucursalesTab`. The corrida picker hides associated stores.
  - Results: tests/motored 5644 passed; pg_real 629 passed, 2 skipped; jest 1881 passed.
  - Open finding: neither the form nor the upload checks whether a store's PRINCIPAL code already belongs to another store.
- 2026-10-05: the owner uploaded Sucursales v2 successfully. After a page reload all stores have a C.O. and no health warnings remain.
  - Pending (small): the Maestros health warnings are fetched only once, on mount (`MaestrosTabs.useSaludPorEntidad`). They should refresh after a save or an upload.
  - The `codigo_co` NOT NULL migration is now unblocked. Ping the KPI session first, because its pg_real fixtures create sucursales without a C.O.
- 2026-10-05: the health warnings now refresh by themselves.
  - Maestros writes (create, update, deactivate, reactivate, row upload, file upload) go through `api._escribirMaestro`, which announces `motored:maestros-cambiaron` (`lib/motored/maestrosEventos.js`). `MaestrosTabs` fetches `/maestros/salud` again when it hears it.
  - RED was observed first (module missing). Full jest: 1903 passed.
