# Motored: referencia identity by code + full-replace referencias upload

## Objective
- A referencia is identified by its CODE.
- Re-uploading the master with a different proveedor corrects the proveedor instead of creating a duplicate.
- Every movement upload (VENTAS, INVENTARIO, BACKORDER, FACTURAS, ...) recognises a referencia whatever its proveedor.
- The referencias upload becomes a "full replace": the file is the truth.

## Problem / why
The user is about to upload a new referencias master with several proveedores (HMCL plus others). Today:
- `referencia` is unique on (codigo, proveedor_id) (`uq_referencia_codigo_proveedor`), and `maestros.upsert_referencia` looks up by (codigo, proveedor). A proveedor change creates a DUPLICATE: the old HMCL row stays, keeps appearing in the HMCL pedido, and the new row is never matched.
- Movement ingest resolves referencias by (codigo, proveedor PRINCIPAL = HMCL). The resolution cache in `services/ingesta/resolucion.py` (~78, 146-153, 184) is filled from `orquestador.resolver_proveedor_principal`. A referencia under any other proveedor never resolves; its rows become "referencia no encontrada" and never reach `venta_mensual`, `venta_detalle` or `inventario_detalle` (the dashboard loses them).

## Decisions (user)
- 2026-10-01: different proveedores always mean different codes, so one code is one referencia.
- 2026-10-01: a re-upload with another proveedor must correct the proveedor.
- 2026-10-02: full replace ("si cargo un nuevo archivo ese reemplaza por completo"). The user approved the design:
  - Every referencia in the file is set exactly as the file says. A blank optional cell CLEARS the stored value (no more "blank keeps old").
  - A proveedor change MOVES the referencia: same `referencia.id`, history kept, no duplicate.
  - Referencias in the DB but absent from the file become `activa = false`. They are never deleted: 11 tables have FKs to referencia.
  - A referencia absent before, or deactivated, that comes back in a later file is reactivated.
  - A dry-run summary is shown BEFORE applying, and the user confirms. It lists:
    - creates,
    - updates,
    - proveedor moves (code, old proveedor, new proveedor),
    - deactivations, highlighting those with sales in the last 6 months (`venta_mensual`) or stock (latest `inventario_snapshot`),
    - reactivations.
  - Safety brake: if the file would deactivate more than 10% of the currently active referencias, a SECOND explicit confirmation is required.

## Constraints (F3/F4 agent impact checks, 2026-10-01)
- **Engine.** It filters every read by `Referencia.proveedor_id == principal` (`cargador.py` 213/247/267/284/298/513). Moving a referencia away from HMCL removes it from FUTURE HMCL pedidos, which is intended.
  - Stored `corrida_linea.referencia_id` stays valid, because the id never changes.
  - Replay uses stored lines.
- **`activa`.** With `consolidar_sustituidas` OFF (prod default) the engine ignores it. With it ON, an inactive referencia without a sustituta becomes INACTIVA_SIN_REEMPLAZO and drops out of pedidos, which is why the summary warning and the 10% brake exist.
- **Sustituta invariant.** A sustituta must belong to the SAME proveedor (`maestros.py` ~225-246).
  - In the file, a row whose sustituta has a different proveedor is a row error. The upload stays all-or-nothing.
  - A referencia moved to another proveedor that is still the target of `sustituida_por` from a DB referencia under the old proveedor: clear that link with a warning listed in the summary.
- **Resolver.** The ingest resolver must keep loading ALL referencias with no `activa` filter, so movement rows for inactive referencias still resolve.
- **Uniqueness.** The migration makes `codigo` unique.
  - Normalize on write: strip.
  - Pre-migration guard: if prod has duplicates on `upper(trim(codigo))`, the migration aborts with a clear message listing them. Never auto-merge.
  - Store codes trimmed; do not change case.
- **Do not touch:** the corridas files (`services/corridas/*`, `api/corridas*`, `schemas/corrida.py`, `schemas/pedido.py`) or the "- copia" worktree.
  - Ping the F3/F4 agent with the new alembic head.
  - The resolver change affects what reaches `venta_mensual` for non-HMCL refs; HMCL-only data must stay byte-identical.

## TDD
- Strict: RED, then GREEN, then REFACTOR.
- Backend: `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`.
- pg_real on a throwaway PG 18 (127.0.0.1, `unix_socket_directories=''`, not port 55432; the migration also needs dummy `DATABASE_URL`, `MINIO_*`, `SECRET_KEY` and `SONIA_BOT_SECRET`).
- Frontend: `cd frontend && npx jest`.

## Tasks
| ID | Task | Route |
|---|---|---|
| R1 | Identity by code: migration with duplicate guard and unique `codigo`; `upsert` by code that moves the proveedor and handles the sustituta invariant; CRUD lookups by code; the ingest resolver by code (cache code -> (id, proveedor_id)). Tests: HMCL-only data gives byte-identical `venta_mensual`; a non-HMCL ref now resolves in VENTAS and INVENTARIO; a move keeps the id. | delegated writer (2+ non-trivial files) |
| R2 | Full-replace referencias upload: blank clears, deactivate absent, reactivate returning, dry-run summary (creates, updates, moves, deactivations with sales/stock highlight, reactivations, cleared sustituta links), 10% second-confirmation brake, audit. Frontend summary and confirm flow in the Referencias tab. | delegated writer (same) |

- [x] R1 (d58cac8, 2eb37d0)
- [x] R2 (6b5debc)

## R3: deactivation is opt-in (user decision 2026-10-03)
- **Trigger:** the user's first real dry-run showed 709 creates, 72 updates and 127 deactivations. Production still holds the FIRST master `plantilla_referencia_HMCL.xlsx`. The user does not want absent references deactivated automatically.
- **Decision:**
  - References in the DB but absent from the file are LISTED, not deactivated.
  - By default they all STAY ACTIVE. Each one gets an "Inactivar" checkbox, plus "Marcar todas" and "Marcar solo las que no tienen ventas ni inventario".
  - On confirm, only the selected codes are deactivated.
  - The 10% double confirmation applies to the selected count plus `inactivar_por_sustituta`, the latter staying automatic because the file says so.
- R3 shipped locally (not pushed): the replace can be confirmed once it is merged and deployed.

| ID | Task | Route |
|---|---|---|
| R3 | Opt-in deactivation. The backend returns the FULL list of absent references (not a 50-row sample) with `con_ventas_6m` and `con_inventario`; the apply takes `codigos_inactivar` (validated as a subset of the absent set, recomputed at apply); the threshold is computed on the selection. The frontend shows the list with checkboxes, the two bulk buttons and the highlight flags, defaulting to none selected. | delegated writer |

- [x] R3 (backend e6ed04d; frontend in the next commit, `feat(motored): make referencias deactivation opt-in per code in full replace`, same subject)

## Log
- 2026-10-03: feature created. The user approved starting (identity plus replace mode). Worktree synced to main 4b07fc9; alembic head `e8c2a5f17b93`.
- 2026-10-03: R1 and R2 implemented by one delegated writer (route: delegated direct, trigger: 2+ non-trivial files). New alembic head `f3a8d1c5b704` (`referencia_codigo_unico`, chained on `e8c2a5f17b93`).
- 2026-10-03: native review findings fixed by one bounded writer (route: delegated direct). (1) After a successful confirm the modal shows "Reemplazo aplicado: ..." and hides "Confirmar reemplazo" (`aplicado` state in `useCargaMasiva`). (2) The mass confirmation is bound to the summary object it was ticked for, so a new summary starts unticked. (3) Decision: separate `inactivar_por_sustituta` group in the summary (count plus sample); `pct_inactivar` and the 10% brake count `inactivar` + `inactivar_por_sustituta`; the 409 message and the frontend text use the combined total. (4) Decision: the replace path is NOT affected (R1 `mover_referencia` / `limpiar_vinculos_entrantes` no longer exist; the plan reads the final proveedor of every file row, and only DB rows absent from the file can get a cleared link); tests added only. With the sustituta repeated in the file the link is kept with no warning; with it blank the link is cleared by the replace semantics (file is the truth), not reported as a cross-proveedor warning. (5) `POST /maestros/referencias`: only `uq_referencia_codigo` (read from `orig.diag`, `orig.constraint_name`, the `__cause__` or the text) is 409; other IntegrityErrors are 422 "Proveedor o referencia sustituta inexistente, o falta un dato obligatorio.". Two older tests that deactivated their only active referencia through a sustituta now pass the mass confirmation (100% > 10%).
- 2026-10-03: R3 implemented by one delegated writer (route: delegated direct, trigger: 2+ non-trivial files plus frontend). No migration (head stays `f3a8d1c5b704`).

## Evidence
- Commits: R1 `d58cac8` (identity by code), `2eb37d0` (bot demanda perdida by code, found in the F3/F4 check), R2 `6b5debc` (full replace + frontend).
- RED -> GREEN (backend, TDD):
  - Migration test file written first: 6 failed (module missing) -> 6 passed.
  - Ingest: (b) non-HMCL ref resolves in VENTAS/INVENTARIO 2 failed -> passed; (a) HMCL-only characterization passed before AND after the change.
  - Maestros/schema/CRUD: `test_referencia_identidad.py` 11 failed, 2 passed -> 13 passed.
  - R2: `test_reemplazo_referencias.py` collection error (module missing) -> 29 passed.
- Frontend: component and tests were written together; RED was verified afterwards against the pre-change sources (`git stash` of `BulkUploadModal.js` and `api.js`): 10 failed, 3 passed -> 13 passed with the change.
- pg_real on throwaway PG 18: upgrade, `downgrade -1`, upgrade OK; guard aborts on duplicates, trim, move keeps id and `venta_mensual`, full replace (deactivate, reactivate, move, blank clears), `con_ventas_6m`.

## Decisions taken while implementing (not in the brief)
- The movement processors keep their unused `proveedor_id` parameter (smallest diff); `resolver_referencia(cache, codigo)` dropped it. In every processor `proveedor_id` was used only to resolve the referencia.
- Dead-code removal (gga): `maestros.upsert_referencia`, `mover_referencia` and `limpiar_vinculos_entrantes` were deleted once the bulk upload moved to `reemplazo_referencias`; `quitar_vinculo_sustituta` is the shared piece.
- A file row whose referencia has a sustituta is `activa=false` (existing master rule), even though the brief says "activa for every referencia in the file". It is not counted in `inactivar`; it appears under `actualizar` as an `activa` change.
- Duplicate codes inside the file (ignoring case) and a file code that matches an existing code only by case are row errors.
- A column absent from the file clears that field too (the file is the truth); `precio_venta` is never touched.
- Creating a referencia through the CRUD with an existing code returns 409 (IntegrityError mapped), not 500.
- Confirmations travel in the JSON body (`confirmar_reemplazo`, `confirmar_inactivacion_masiva`) and as query params on `/excel`. Missing `confirmar_reemplazo` is 409 on apply; row errors still return `ok=false` first.
- Lore bot `referencias/resolver` no longer filters by the principal proveedor (still `activa`, still exact upper/trim match).
- "Crear como OTROS" looks up by code only; it never moves an existing referencia.
- 6-month sales window = current month plus the previous five (`anio*12+mes`); stock = `existencias > 0` in the latest `inventario_snapshot` `fecha_corte`.

## Pending
- Ping the F3/F4 agent with the new head `f3a8d1c5b704`.
- Real end-to-end check with the production referencias file (the guard may abort the migration if prod has duplicate codes).

## R3 evidence and decisions
- RED -> GREEN backend: tests rewritten first (`test_reemplazo_referencias.py`, `test_carga_referencias_reemplazo_api.py`, pg_real): 41 failed, 12 passed against the old code -> `tests/motored` 4520 passed after; pg_real on throwaway PG 18 (alembic_motored head): 399 passed, 2 skipped.
- RED -> GREEN frontend: 24 failed, 3 passed (component and csv suites) -> 27 passed; API helper tests 2 failed against the old `api.js` -> 7 passed; full `npx jest`: 146 suites, 1469 passed.
- Decisions:
  - Renamed `plan.inactivar` / `resumen.inactivar` to `ausentes` (it no longer means "will be deactivated"); `ausentes.items` is the FULL list (codigo, nombre, proveedor, con_ventas_6m, con_inventario), capped at `AUSENTES_MAX = 20000` (the dry-run returns 422 with a Spanish message above it). The apply does not repeat the list.
  - `resumen.seleccionadas` (apply), `pct_inactivar` = (selected + `inactivar_por_sustituta`) / `activas_actuales`, `pct_inactivar_si_todas` for all absent selected. In the dry-run `pct_inactivar` counts only the substitute group, so `requiere_doble_confirmacion` is false unless the substitutes alone exceed 10%. The frontend recomputes the % from the live selection with `activas_actuales` (the existing name for `total_activas`); the backend rechecks at apply.
  - `codigos_inactivar`: JSON body field; for `/excel` a multipart form field holding a JSON list (thousands of codes do not fit a query string); an invalid value is 422. Codes are trimmed and deduplicated; any code outside the recomputed absent set is 409 with the offending codes and nothing is applied.
  - Audit text: `ausentes_ofrecidas=N; inactivar_elegidas=M`.
  - Frontend: selection and double confirmation are stored with the summary they belong to; changing the selection un-ticks the confirmation. The list is a scroll area (`max-height: min(45vh, 360px)`), rows are memoized, no virtualization (the cap is 20000 rows).
