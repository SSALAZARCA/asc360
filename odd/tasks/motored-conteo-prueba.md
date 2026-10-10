# Motored: test counts ("Conteo de prueba")

## Objective

The ADMIN can run a complete inventory count as a test without polluting the app's record of real counts.

## Problem

The owner wants to rehearse a real count end to end: pairs, QR, phones, reconteo, closing and Excel. Today every count stays forever in the counts list and, from Stage 4 on, in the accuracy history. Closing never touches the ERP (the Excel is uploaded by hand), so the only harm is to the app's own records.

## Decisions (owner, 2026-10-10)

1. A flag `es_prueba` is set when scheduling.
   - Only ADMIN sees the "Es de prueba" checkbox and only ADMIN may set it.
   - The backend rejects the flag (403) for any other role.
2. A test count behaves exactly like a real one: snapshot, pairs, readings, reconteo, closing and Excel all work.
3. It is visible only to ADMIN.
   - LIDER_INVENTARIOS, COORDINADOR_REPUESTOS and GERENCIA never see it, in lists, the panel or by id (404).
   - The ADMIN list hides test counts by default; a "Mostrar pruebas" toggle shows them, each with a PRUEBA badge.
4. Every screen of a test count shows a PRUEBA badge, including the pair device page (`/motored/c/<slug>`).
5. The adjustments Excel says "PRUEBA – NO CARGAR AL ERP" in its title row, and its filename starts with `PRUEBA_`.
6. A test count never blocks a real one.
   - It is excluded from the "one open TOTAL count per store" unique index.
   - Real counts are unaffected by an open test count.
7. "Borrar conteo de prueba" (ADMIN only, any state, only when `es_prueba`) hard-deletes the conteo and every child row.
   - Child rows: sessions, readings, locations, results, reconteos and anything else keyed to it.
   - There is a confirmation dialog. Real counts can never be deleted.
8. Any cross-count aggregate, now or later (accuracy history, KPIs), must filter `es_prueba = false`.

## Scope

- Backend:
  - model and alembic_motored migration (column, plus rebuilding the open-count index with `AND NOT es_prueba`);
  - schedule schema and service;
  - list and visibility queries;
  - Excel;
  - delete endpoint;
  - pair public payload (`es_prueba`).
- Frontend:
  - the schedule form checkbox;
  - the list toggle and badge;
  - the header badge on all count screens;
  - the pair page badge;
  - the delete button and dialog.
- Out of scope: converting a test count to a real one, and vice versa.

## Checklist

- [x] T1 backend + migration + tests (route: delegated writer, because there are 2+ non-trivial files)
  - Migration `f4b8d2a6c917` (down_revision `c4e8a2d6f931`).
  - Evidence: `pytest tests -q -k conteo` gave 499 passed (RED first: 27 failed in `test_conteos_prueba.py`).
  - Evidence: `pytest -m pg_real` over the 10 conteo pg files on a throwaway PG18 gave 125 passed, including the 7 tests in `test_conteo_prueba_pg.py` (upgrade/downgrade/upgrade, index exclusion, explicit-order delete).
  - Evidence: the full `tests/motored` unit run had 2 failures, both alembic-head pins. They were moved to `f4b8d2a6c917` and now pass (16 passed).
- [x] T2 frontend + jest tests (route: same writer)
  - Done: the "Es de prueba" checkbox, the "Mostrar pruebas" toggle, the PRUEBA badge in the list, the PRUEBA band on every count screen, and "Borrar conteo de prueba" (list and detail) with its dialog.
  - Done: the PRUEBA badge on the pair device screens, both laptop and phone (`conteo-publico/PruebaBadge.js`), driven by `es_prueba` from the join answer and from `GET /sesion`.
  - Done: `borrarConteoPrueba` moved into `lib/motored/conteosApi.js`; the temporary `borrarConteoPrueba.js` was removed.
  - Evidence: `npx jest conteos` gave 98 passed (RED first: 4 failed). `motored-conteo-publico-prueba` failed first (2 failed: the badge on the laptop and phone screens).
  - Evidence: final `npx jest conteo` gave 133 passed.
  - Not done: no tablet (768–1024px) screenshots yet.
- [x] T3 commits eb8deaf 29fbe84 (gga PASSED), pushed

## Checks

- pytest for the conteos tests, plus the related pg_real conteos tests (`-m pg_real`, throwaway PG18).
- A migration upgrade/downgrade on PG.
- jest conteos tests.
- Production runs Python 3.11.

## Progress

- 2026-10-10: decisions recorded, writer launched.
- 2026-10-10: T1 and T2 done (see the checklist).
  - Store locations (`ubicacion_inventario`) are store-level and have no FK to conteo, so a test delete keeps them.
  - A test count that another conteo references through `verifica_conteo_id` or `arrastra_conteo_id` is refused with a 409.
