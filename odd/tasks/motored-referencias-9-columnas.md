# Motored Referencias: 9-column layout

## Objective
The Referencias master uses exactly these 9 fields, in this order, in the xlsx template, the bulk upload (Excel/CSV), the database and the Referencias page:

1. Código
2. Código del proveedor (identifies the supplier, `Proveedor.codigo`)
3. Nombre
4. Línea comercial
5. Unidad de empaque
6. Precio Normal antes de IVA
7. Precio Público antes de IVA
8. Código de referencia sustituta
9. Homologados otras marcas (new, multi-value)

## Constraints and decisions
- `precio_venta` is removed from the Excel template and the UI, but the DB column and its data are kept.
- Old snake_case headers and old labels keep uploading (backward compatibility).
- **Sustituta must belong to the same supplier as the row.** Equivalent parts from other suppliers or brands go in `homologados`, never as sustituta. Confirmed by the user on 2026-09-28.
- `homologados` is entered as one cell with values separated by comma or semicolon, and displayed joined with ", ".
- Motored conventions: tooltips on non-obvious fields, explicit `<option>` styles, no backticks in `themeCss` comments.

## TDD
- Mode: strict, enabled by the user's global config.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q`
- Frontend: `cd frontend && npx jest`

## Tasks

- [x] **T1: 9-column layout across the DB, parser, template and UI.** Route: delegated writer (2+ non-trivial files).
  - **Evidence:** backend 997 passed, frontend 447 passed. Not committed yet.
  - **Migration:** `5c2e8a1f9b47_referencia_homologados`.
- [x] **T2: Fixes from review (review-risk + review-reliability).** Route: delegated writer. RED was observed first: backend 20 failing tests, frontend 4 failing tests. Final results: backend 1013 passed, frontend 451 passed.
  - [x] **Blocker:** blank xlsx cells now arrive as `""`, exactly like CSV. `_strip_blank_values` drops `None`, `""` and whitespace-only values for every entity. `unidad_empaque` is coerced only when a value was provided. Blank boolean and multi-value cells are never coerced, in both Excel and the frontend CSV. **Evidence:** `test_carga_excel_blank_cells.py` builds a real `.xlsx`, runs parse, resolve and `procesar_carga`, and shows that `nombre`, `linea_comercial`, `unidad_empaque`, `precio_publico` and `homologados` survive, and that `es_principal` is not demoted.
  - [x] **Sustituta:** `_pick_sustituta` accepts the same supplier only, and its error points to "Homologados otras marcas". `services/maestros._verificar_sustituta` checks single-record create and update (other supplier, missing, or self), and the API returns 422. Bulk upsert skips the extra query because the resolver already enforces the rule. The form picker filters by the selected supplier and clears a sustituta that no longer fits. **Evidence:** `TestSustitutaMustBelongToTheSameProveedor`, `TestSustitutaSameProveedorOnSingleRecordWrites` and 2 ReferenciasTab tests.
  - [x] **homologados:** capped by `HOMOLOGADOS_MAX_ITEMS = 50`, with a clear error. **Evidence:** `test_list_longer_than_the_max_items_is_rejected_with_a_clear_error`.
  - [x] **Audit:** truncation keeps whole items and adds a `… (+N más, #hash8)` marker. Long scalars get a prefix plus the hash marker. **Evidence:** `TestListAndLongValues`, including a change beyond the cutoff.
  - [x] **Duplicate headers:** backend `ColumnaDuplicadaError` returns 400 through `CargaExcelError`. The frontend CSV shows a parse error. **Evidence:** `test_duplicate_headers_for_the_same_field_are_rejected_with_a_clear_error` and the CSV jest test.
  - [x] **Migration:** `SET LOCAL lock_timeout = '5s'` runs before `add_column`. `env.py` wraps migrations in `context.begin_transaction()`. **Evidence:** `test_upgrade_sets_a_local_lock_timeout_before_the_alter`.
  - [x] **Frontend tests:** use `getAllByRole('columnheader' | 'row' | 'cell' | 'listitem' | 'option')`, plus `role="note"` to strip tooltip text.
- [x] **T3: Commit and deliver.** Delivery: the repo policy is a commit to main plus push, because Coolify auto-deploys.
  - **Commit:** `c8e2aed`, pushed with `9422c8f..c8e2aed`. gga passed.
  - **Native RDD review:** assessed as medium, `slice_budget_reached`. The user chose to push without it. The change had already passed review-risk and review-reliability.
  - **Pending:** the migration has not been verified against a live Postgres. Check the Coolify deploy log.

## Out of scope / noted
- The Referencias header text still says "Subí un archivo CSV" although `.xlsx` is accepted.

## Progress
- 2026-09-28: T1 done. The reviews found a data-loss blocker. T2 is next.
- 2026-09-28: T2 done and still not committed.
  - `backend/.venv/bin/python -m pytest tests/motored -q` → 1013 passed, 1 deselected.
  - `cd frontend && npx jest` → 65 suites, 451 tests passed.
  - T3 (commit and push) is next, after a fresh review.
  - **Behavior change:** a missing or blank `unidad_empaque` in a bulk upload no longer resets existing referencias to 1. New referencias still get 1 with a warning.
