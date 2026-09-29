# Motored Referencias: server-side pagination and search

## Objective
The Referencias page must load one page at a time, not all ~11.7k referencias at once. It needs server-side search and filters, and a searchable sustituta picker.

## Problem
- `GET /maestros/referencias` (`backend/app/motored/api/maestros.py::list_maestro`, ~line 154) returns every row. Its docstring assumes "catálogos chicos", which holds for sucursales and bodegas but not for referencias.
- `ReferenciasTab.js` fetches the whole list via `listMaestros('referencias')` and renders it all. The form's sustituta `<select>` is filled from that full list, so it has thousands of options.

## Scope
- Referencias only. Proveedores, sucursales and bodegas keep the current unpaginated behavior.
- Backend: a paginated list for referencias with `page`/`page_size` (default 50, capped at 200) and `q` (search by código or nombre, case- and accent-insensitive if feasible). Filters: `linea_comercial`, `activa`, and `proveedor_id` if useful. The response includes `total`, and ordering is stable (by código). It stays a single DB query plus a count, with no in-memory filtering. The existing scoping/role gates are kept. The endpoint shape must stay backward compatible for any other caller, so the parent must list the callers first.
- Frontend: a paginator (prev/next, current page/total, page size), a search box with debounce, and filters for línea comercial and estado. Only the current page is fetched. After create, edit or deactivate, the current page is refetched.
- Sustituta picker: a type-ahead search against the server, limited to the same proveedor and excluding the referencia itself. The current value is shown by its código when editing.
- Distinct líneas comerciales for the filter come from a small endpoint or a server-side distinct, not from the page.

## Constraints
- Motored conventions: explicit `<option>` styles, tooltips on non-obvious fields, no backticks in `themeCss` comments, components under ~50 lines, and gga's function-size rule (~50 lines).
- The homologados single-line cell (in progress in the same file) must be preserved.

## TDD
- Mode: strict.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q`
- Frontend: `cd frontend && npx jest`

## Tasks
- [x] **T1: backend.** Paginated, searchable, filterable referencias list, a líneas distinct endpoint, and a sustituta search, with tests. Route: delegated writer.
  - Evidence: `backend/tests/motored/test_referencias_busqueda.py` was RED first (20 failed, 10 passed). Then `.venv/bin/python -m pytest tests/motored -q` returned `1057 passed, 1 deselected`.
- [x] **T2: frontend.** Paginator, search and filters in ReferenciasTab, plus the type-ahead sustituta picker, with tests. Route: same writer.
  - Evidence: `motored-referencias-api`, `motored-referencias-paginacion` and the updated `motored-referencias-tab` were RED first (3 suites, 33 failed). Then `npx jest` returned `68 suites, 484 tests passed`.
- [x] **T3: commit and push to main.** Repo policy. Parent spot check: `test_referencias_busqueda.py` 30 passed.

## Compatibility decision
- Callers of `GET /maestros/referencias` (searched with rg across `frontend/`, `lore-bot/` and `backend/`):
  - The only runtime caller was `frontend/components/motored/maestros/ReferenciasTab.js` (`listMaestros('referencias')`). It now uses the new endpoints.
  - `lore-bot/` does not call it. It only uses `/api/motored/bot/*`, including `POST /bot/referencias/resolver`.
  - The backend tests (`test_sucursal_scoping.py`) and the new `test_referencias_busqueda.py` still exercise the generic list.
- Design: `GET /maestros/referencias` (`list_maestro`) is unchanged, and the new endpoints are separate:
  - `GET /maestros/referencias/buscar?page&page_size&q&linea_comercial&activa&proveedor_id` returns `{items, total, page, page_size}`. Each item is a `ReferenciaRead` plus `sustituta_codigo`, which is resolved by a self-join in the page query.
  - `GET /maestros/referencias/lineas-comerciales` returns the sorted distinct non-empty values.
  - `GET /maestros/referencias/sustitutas?proveedor_id&q&exclude_id` returns `[{id, codigo, nombre}]`, at most 20, active referencias only (business decision). A current sustituta that is inactive is still shown by código through `sustituta_codigo` from `/buscar`.
  - They live in `api/referencias_busqueda.py` plus `services/referencias_busqueda.py`, and `router.py` mounts them BEFORE `maestros`. Otherwise `/maestros/{entidad}/{entity_id}` would catch `/referencias/buscar` and return a 422.
  - Keeping the old unpaginated list is not required by any runtime caller now. It was kept only for backward compatibility and for the existing tests.
- Search: `ILIKE` with escaped `%`/`_`. It is case-insensitive but NOT accent-insensitive, because `unaccent` is not used anywhere in the Motored DB, so it was skipped.
- Index: `referencia` only has the `(codigo, proveedor_id)` unique btree, which leads with `codigo` and so helps `ORDER BY codigo`. A `%q%` ILIKE cannot use a btree (it would need `pg_trgm`). At ~11.7k rows a seq scan is acceptable, so no migration was added.

## Progress
- 2026-09-28: the document was created. Waiting for the homologados-cell change (same file) to land first.
- 2026-09-28: T1 and T2 were implemented with strict TDD (see the evidence under each task). T3 (commit and push) is still pending.
