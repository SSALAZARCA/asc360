# Motored: visible logout and admin password reset

## Objective
1. The "Salir" button must always be visible.
2. An ADMIN can set a new password for any Motored web user from the Usuarios screen.

## Current state (verified 2026-09-29)
- The logout button already exists in the footer of `frontend/components/motored/MotoredSidebar.js:105-109`. The aside uses `minHeight: '100vh'` (line 42) and stretches with the page, so on long tables (Sucursales, Referencias) the footer sits below the last row and the user never sees it.
- Passwords: `POST /usuarios` sets `hashed_password` via `get_password_hash` (`backend/app/motored/api/usuarios.py:120`). There is no endpoint or UI to change a password afterwards. Lore-only advisors (`ASESOR_MOSTRADOR`) have `hashed_password = None` and log in only through the bot (`backend/app/motored/api/auth.py:85`).

## Design
- **Sidebar:** make the aside sticky (`position: sticky; top: 0; height: 100vh`). The nav area scrolls if it overflows, and the footer (user name plus Salir) is always visible. No behavior change to the logout itself.
- **Backend:** add `POST /usuarios/{id}/password` (ADMIN only, the existing `_require_admin`). The body is `{ "password": str }`.
  - **Validation:** the minimum length follows the existing create-user schema. If that schema has no rule, use a minimum of 8 characters, applied to both create and reset.
  - **Users without web access:** 404 for an unknown user. For a user without web access (no email, or `ASESOR_MOSTRADOR`), return 422 `SIN_ACCESO_WEB`.
  - **Storage:** hash with `get_password_hash`. Never log the password.
  - **Own password:** an ADMIN may reset their own password through the same endpoint.
- **Frontend (Usuarios page):** a "Cambiar contraseña" action on each row that has web access, visible only to ADMIN. A small modal or inline form has "Nueva contraseña" and "Confirmar contraseña" inputs (type=password). It validates the minimum length and that the two match before sending, and shows success or error. It never pre-fills or echoes the password.

## TDD
- Mode: strict.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q` (run from `backend/`).
- Frontend: `cd frontend && npx jest`.

## Tasks
- [x] T1: Sticky sidebar so Salir is always visible. Add a test that the footer and Salir are rendered, plus the sticky style. Route: delegated writer.
- [x] T2: Backend password-reset endpoint with tests covering: admin OK, non-admin 403, unknown user 404, no web access 422, and too short 422. Route: same writer.
- [x] T3: Usuarios "Cambiar contraseña" action with tests. Route: same writer.
- [x] T4: Commit and push to main.

## Progress
- 2026-09-29: document created.
- 2026-09-29: T1-T3 implemented (strict TDD, RED observed then GREEN). Evidence: `.venv/bin/python -m pytest tests/motored -q` -> 1133 passed; `npx jest` -> 72 suites, 512 tests passed. Not committed yet (T4 pending).
  - T1: `MotoredSidebar.js` aside sticky/100vh, nav scrolls (`frontend/__tests__/motored-sidebar-logout-visible.test.jsx`).
  - T2: `POST /usuarios/{id}/password` in `api/usuarios.py`, `audit_password_reset` in `services/auditoria.py`, min length 8 (`PASSWORD_MIN_LENGTH`) also enforced on create; validated in the endpoint (not pydantic Field) so the 422 never echoes the password (`backend/tests/motored/test_usuarios_password_api.py`).
  - T3: `resetPasswordUsuario` in `lib/motored/api.js`, `components/motored/CambiarPasswordForm.js`, wiring in `app/motored/usuarios/page.js` (`frontend/__tests__/motored-usuarios-password.test.jsx`).
