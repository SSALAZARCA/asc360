# Lore: several advisors sharing one Telegram account

## Objective
Some stores have two advisors but only one phone number and one Telegram account. Each advisor registers through Lore's normal registro flow (nombre, celular, sucursal) from that same Telegram and is approved by an admin as today. Every lost sale and correction is attributed to the advisor who actually made it.

## Business decisions (user, 2026-09-29)
- Use the existing registro flow, with no new admin screen. Each advisor is a real `usuario`, approved individually.
- When a Telegram has more than one approved and active advisor, Lore asks "¿Quién registra?" with one button per advisor at the start of EVERY Captura and Correccion. The choice is never remembered across conversations, to avoid silent misattribution. With a single advisor the flow is unchanged and nothing is asked.
- The sucursal comes from the chosen advisor. It is auto-selected if the advisor has exactly one; otherwise the current picker is shown, limited to that advisor's sucursales.
- In Correccion each advisor sees and edits only their own records. This is already enforced per `usuario.id` once the actor is chosen.
- Accepted limit: people sharing a phone can pick each other's name. The system only guarantees that the chosen advisor belongs to that Telegram.

## Current state (mapped 2026-09-29, paths under `backend/app/motored/` unless noted)
- `models/usuario.py:53` declares `UniqueConstraint("telegram_id", name="uq_usuario_telegram_id")`, created in `alembic_motored/versions/8611c3e463ac_lore_bot_schema.py:56`. The Motored head is `5c2e8a1f9b47`.
- `deps_bot.py:141` `get_bot_actor` looks up `telegram_id` and takes `.first()`. Every bot endpoint depends on it through `_require_bot_roles`.
- `api/bot.py:146` `/registro` returns 409 YA_REGISTRADO for any existing row on that Telegram, with an IntegrityError backstop at :165. `/admin/vincular` (:221) and `services/vinculacion.py` also assume one row per Telegram. `/yo` (:94) returns a single actor. The admin notification list (:172) could repeat IDs.
- Bot endpoints in `api/bot_demanda_perdida.py` scope by `actor.usuario_id` and `actor.sucursal_ids`, so they need no change once the actor is resolved correctly.
- The Lore side:
  - `lore-bot/lore/api.py` `BackendClient` sends `x-lore-telegram-id`.
  - `handlers/registro.py:56` `/start` never offers a new registration to a registered Telegram.
  - `captura.py::iniciar` (:275) and `correccion.py::iniciar` (:76) are the insertion points.
  - `context.user_data` is in memory only.
- The Motored `usuario` table is independent from UM's `app.models.user.User` and from `telegram-bot/`. No cross-system impact.
- Tests to update: `backend/tests/motored/test_migration_lore_bot_schema.py:111`, and `test_bot_api.py:309` and `:412`.

## Design
- **DB:** a migration drops `uq_usuario_telegram_id` and adds a non-unique index on `telegram_id`, plus a partial unique index on `(telegram_id, phone)` WHERE `status <> 'rejected'`, so the same person can't register twice from the same Telegram. Use the exact phone column name from the model and a SET LOCAL lock_timeout, as in `5c2e8a1f9b47`. The downgrade restores the unique constraint.
- **Actor resolution (`deps_bot.py`):**
  - A new optional header `X-Lore-Usuario-Id`, validated server-side.
  - Candidates are the usuarios with that `telegram_id`.
    - Header present: it must be one of the candidates, otherwise 403 `ASESOR_NO_PERTENECE`.
    - Header absent and exactly one candidate: use it (backward compatible).
    - Header absent and more than one usable candidate: 409 `ASESOR_REQUERIDO`.
  - The status and activo gates still apply to the chosen row. Never use `.first()`.
- **`/bot/yo`:** returns the list of that Telegram's usuarios (id, nombre, role, status, activo, sucursales) under a new key. It keeps the current single-actor fields when exactly one exists, so the currently deployed bot keeps working during the rollout.
- **`/bot/registro`:** it rejects only a duplicate of the SAME person (same Telegram and same phone, not rejected) with YA_REGISTRADO. It also rejects adding an advisor to a Telegram that already has an ADMIN usuario. Admins don't share: 409 with a clear code. `/admin/vincular` and vinculación keep refusing a Telegram that already has usuarios.
- **Admin notifications:** de-duplicate the Telegram IDs.
- **Lore:**
  - `/start` on a registered Telegram greets as today and offers an inline "➕ Registrar otro asesor" button that starts the normal registro flow. A pending or rejected advisor never blocks adding another.
  - Captura and Correccion call `yo()`. If more than one approved and active advisor exists, the first step is "¿Quién registra?", with one inline button per advisor plus ✖️ Cancelar. The choice is stored in that conversation's `user_data` and sent as `x-lore-usuario-id` on every backend call of the conversation.
  - Captura's sucursal step uses the chosen advisor's sucursales.
  - `BackendClient` gets an optional `usuario_id`.
  - Map `ASESOR_REQUERIDO` and `ASESOR_NO_PERTENECE` in `_ERROR_CODE_MAP` to friendly messages.

## TDD
- Mode: strict, from the global CLAUDE.md.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q` (run from `backend/`).
- Lore: `lore-bot/.venv/bin/python -m pytest -q` (run from `lore-bot/`).

## Tasks
- [x] **T1: backend.** Migration, actor resolution with header validation, `/yo` list (backward compatible), `/registro` duplicate rules and the admin-sharing rule, admin notification de-duplication, and the existing tests updated. Route: delegated writer (2+ non-trivial files).
- [x] **T2: Lore.** "Registrar otro asesor" on `/start`, "¿Quién registra?" in Captura and Correccion, the per-conversation header, sucursal from the chosen advisor, and the error mapping. Route: same writer.
- [x] **T2b: Lore error codes.** `BackendClient._request` (and the 404 branches) read the error code from top-level `code` AND FastAPI's `detail.code`, through one `_error_code` helper. Unrecognized shapes (detail string/list, non-JSON, non-string code, unknown code) still map to `BackendCaido`. Route: same writer.
- [x] **T3: commit and push to main.** Repo policy, one work-unit commit per task. The backend lands first and is backward compatible.

## Delivery
The forecast is above ~400 changed lines. The user's standing policy is commit plus push to main (Coolify auto-deploy), with one commit per task.

## Progress
- 2026-09-29: document created from the read-only map.
- 2026-09-29: T1 (backend) and T2 (Lore) implemented by the delegated writer, NOT committed yet. Route: delegated writer, trigger 2+ non-trivial files. TDD strict, RED observed before each GREEN.
  - T1 evidence: `backend/.venv/bin/python -m pytest tests/motored -q` (from `backend/`): 1107 passed, 1 deselected (45 new tests in `test_bot_multi_asesor.py` + `test_migration_multi_asesor_telegram.py`). Migration revision `a3f7c91d2e58` (down `5c2e8a1f9b47`), single Alembic head verified.
  - T1 notes: extra partial unique index `uq_usuario_telegram_admin` (ADMIN, one per Telegram) added so `/admin/vincular`'s IntegrityError backstop still guards two codes racing for one Telegram. Malformed and foreign `X-Lore-Usuario-Id` both return 403 `ASESOR_NO_PERTENECE`. New code `TELEGRAM_ES_ADMIN` (409) on `/registro`.
  - T2 evidence: `lore-bot/.venv/bin/python -m pytest -q` (from `lore-bot/`): 375 passed (326 before, 49 new).
  - Resolved by T2b (below); original finding: `lore/api.py::_request` reads `body["code"]` but the backend returns `{"detail": {"code": ...}}`, so every coded 401/403/409 currently maps to `BackendCaido` in production. This also makes the new `ASESOR_*`/`TELEGRAM_ES_ADMIN` friendly messages unreachable until fixed.
  - Pending: T3 commits (one per task), review assessment per work-unit commit.
- 2026-09-29: T2b done, not committed. RED: 4 new tests failed on the old code, then GREEN. `lore-bot/.venv/bin/python -m pytest -q` (from `lore-bot/`): 389 passed. Audit of newly live branches: see the coordinator report.

