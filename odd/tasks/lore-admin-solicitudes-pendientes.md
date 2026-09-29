# Lore: pending-requests button for admins

## Objective
An ADMIN (the top Motored role; there is no separate superadmin in Motored, see `MotoredRole` in `backend/app/motored/models/usuario.py:43`) can open the pending Lore registrations from the existing Lore reply-keyboard menu and approve or reject them there, without waiting for the one-time push notification.

## Current state
- The Lore menu is `TECLADO_CAPTURA` in `lore-bot/lore/handlers/_common.py:109`, with `BOTON_REGISTRAR` and `BOTON_CORRECCIONES`. The same keyboard is sent to every approved role.
- The admin approves or rejects with the callbacks `lore_apr:<id>` / `lore_rej:<id>`, handled in `lore-bot/lore/handlers/admin.py`. The backend endpoints are `POST /bot/admin/solicitudes/{id}/aprobar|rechazar` in `backend/app/motored/api/bot.py:305`, gated by `require_bot_admin`.
- There is no bot endpoint that lists pending requests. The web panel uses its own endpoint, the source of `listSolicitudesPendientes` (`frontend/app/motored/usuarios/page.js`).

## Design
- **Backend:** add `GET /bot/admin/solicitudes`, gated by `require_bot_admin`. It returns the pending usuarios (`status='pending'`), oldest first: id, nombre, phone, sucursales (names), created_at. Reuse the panel's query or service if one exists, and don't duplicate it.
- **Lore menu:**
  - An ADMIN gets a keyboard with a third button, "📋 Solicitudes pendientes".
  - Advisors keep the current two-button keyboard.
  - Wherever the keyboard is sent, it depends on the actor's role.
- **Lore handler:** the button (and a `/pendientes` command alias) lists each pending request as its own message with the same Aprobar/Rechazar inline buttons the push notification uses, so the existing callbacks handle them. With nothing pending, it replies "No hay solicitudes pendientes." A non-admin who types the command or the text gets a polite refusal.
- **Errors:** use the `_error_code` mapping (`detail.code`). Admin-side retry messages keep their buttons. This fixes the pending item "admin.py loses Aprobar/Rechazar buttons on backend failure" for this path; fix the push-notification path too if it shares the code.

## TDD
- Mode: strict.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q` (from `backend/`)
- Lore: `lore-bot/.venv/bin/python -m pytest -q` (from `lore-bot/`)

## Tasks
- [x] **T1: backend list endpoint**, with tests. Route: delegated writer. Evidence: `GET /bot/admin/solicitudes` in `backend/app/motored/api/bot.py`; 11 new tests in `test_bot_api.py`, RED (11 failed) then GREEN; `pytest tests/motored -q` (backend): 1118 passed, 1 deselected.
- [x] **T2: Lore.** Admin keyboard button, list handler, command alias, error handling, tests. Route: same writer. Evidence: RED (5 collection errors), then GREEN; `pytest -q` (lore-bot): 412 passed, after adding the 10-message cap (2 more tests).
- [x] **T3: commit and push to main.** One commit per task, backend first.

## Progress
- 2026-09-29: document created.
- 2026-09-29: T1 and T2 implemented and verified, not committed (T3 pending). Route: delegated writer. Tests written first. The retry path in `resolver_solicitud_callback` now keeps the Aprobar/Rechazar buttons on `BackendCaido` (shared by push notification and list).
- 2026-09-29: pending list capped at `_MAX_SOLICITUDES_POR_TOQUE` = 10 (oldest first) with a count message that says when there are more. RED then GREEN. Earlier counts were mislabeled: backend is 1118, lore-bot was 410 before the cap and is 412 now.
