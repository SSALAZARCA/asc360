# Motored Referencias: resolve sustituta within the same upload

## Objective
A bulk upload of referencias must accept a "Código de referencia sustituta" that points to a referencia **created in the same file**, not only to one already stored in the DB.

## Problem
`_resolve_referencia_relaciones` (`backend/app/motored/api/carga.py`) only looks the sustituta code up in the DB before any row is written. On a first load, every sustituta pointing to a new code in the same file fails, and the all-or-nothing rule then rejects the whole file. The real file `plantilla_referencia_HMCL.xlsx` has about 736 sustitutas and would be rejected.

## Constraints
- The sustituta must belong to the same proveedor. This is still enforced, whether the code comes from the DB or from the file.
- The all-or-nothing rule is unchanged: a code that is neither in the DB nor in the file (same proveedor) is still a row error.
- The file may contain chains (A→B, B→C): there are 33 in the real file. Setting a sustituta marks the substituted referencia `activa=False`, and that existing side effect must hold for rows created in the same upload too.
- A self-reference or a cycle within the file must be a clear row error, not a crash or an infinite loop.
- Validation-only (dry-run) endpoints must give the same verdict as the real upload.
- `homologados` holds compatible motorcycle MODELS (business confirmed 2026-09-28), not part codes. There is no behavior change, but tooltips and docs should not say "codes".

## TDD
- Mode: strict.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q`
- Frontend: `cd frontend && npx jest`

## Tasks
- [x] **T1: resolve the sustituta from the same file.** Two-pass upsert, with the same-proveedor rule, chains, and self/cycle errors, plus tests. Route: delegated writer.
- [x] **T2: homologados wording.** Tooltips and docstrings say "compatible models of other brands". Route: same writer.
- [x] **T3: commit and push to main.** Repo policy. Parent spot check: `test_carga_sustituta_mismo_archivo.py` gives 14 passed.

## Progress
- 2026-09-28: document created.
- 2026-09-28: T1 done. `_resolve_referencia_relaciones` (`api/carga.py`) now checks, per row: self-reference (row error), then a target row in the same file under the same proveedor (row is marked `SUSTITUTA_EN_ARCHIVO`), then the DB via `_pick_sustituta`. A code found only in the file under another proveedor gives the "otro proveedor" error. Cycles among in-file links are detected in O(n) (`_ciclos_de_sustitucion`) and reported on every row of the cycle, e.g. "A -> B -> C -> A". `procesar_carga` (`services/carga.py`) upserts every row without the in-file link, calls `flush()`, then sets `sustituida_por` via `maestros.update_referencia`, which keeps the `activa=False` side effect and the audit trail. Everything stays in one commit. No new queries: still one proveedor query and one sustituta query, and pass 2 issues none. Validar and carga share the resolver, so they give the same verdict. Tests are in `backend/tests/motored/test_carga_sustituta_mismo_archivo.py` (14): A->B->C chain over JSON and `.xlsx`, target listed before its source, an existing DB row pointing to a new in-file row, a cycle, a self-reference (new and existing), a target under another proveedor, a code in neither DB nor file, and validar/carga parity. A fake session enforces the FK at autoflush, flush and commit. RED: 11 failed, 3 passed before the code change.
- 2026-09-28: T2 done. The homologados tooltips (`ReferenciasTab.js`, `BulkUploadModal.js`) and the docstrings/comments (`models/referencia.py`, `schemas/referencia.py`, `services/carga_excel.py`) now say "compatible motorcycle models of other brands". The bulk sustituta help now also says the target can be in the same file. Two jest tests were added and observed RED first.
- Verification (2026-09-28): `backend/.venv/bin/python -m pytest tests/motored -q` -> 1027 passed, 1 deselected. `cd frontend && npx jest` -> 65 suites, 453 tests passed.
- 2026-09-28: follow-up (coordinator decision). The "equivalentes de otras marcas van en 'Homologados otras marcas'" hint is gone everywhere: the `_pick_sustituta` (`api/carga.py`) and `maestros._verificar_sustituta` error messages, the sustituta tooltip in `ReferenciasTab.js` and the bulk help in `BulkUploadModal.js`. They now say "La referencia sustituta debe ser del mismo proveedor.", and the row error still names "Código de referencia sustituta". The asserting tests were updated first and observed RED (3 backend, 2 frontend) before the code change. Verification: `backend/.venv/bin/python -m pytest tests/motored -q` -> 1027 passed, 1 deselected. `cd frontend && npx jest` -> 65 suites, 454 tests passed.
- Open: cycles that go through links already stored in the DB (not in the file) are not detected.
