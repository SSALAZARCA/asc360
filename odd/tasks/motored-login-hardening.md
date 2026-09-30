# Motored: login and password hardening

## Objective
Fix the safe, code-only findings of the Motored login audit (2026-09-30): long passwords crashing login, the DB password printed in deploy logs, confusing login messages and silent session expiry, missing change-own-password with no session invalidation after a password change, and a per-cédula attempt limit for the public survey.

## Why
Read-only audit, with the top findings verified by hand:
- bcrypt 5.0.0 (the pinned production version) raises `ValueError` for passwords over 72 bytes. `app/core/security.py:36-43` does not catch it, so the endpoint returns a 500.
- `backend/scripts/start.sh:4` echoes the full `DATABASE_URL`, password included.
- The survey rate limit is per IP only.

## Scope (user: "avanza con todos", 2026-09-30)
Included:
- T1 through T5 below.

Excluded, deferred by the user:
- Anything in Coolify, Traefik or the proxy, including `--forwarded-allow-ips` (other applications run on that server).
- Rotating the database password (infrastructure).

Not requested:
- Password policy changes (minimum stays 8).
- Forced change on first login.
- Per-account lockout.
- Email-based password recovery.

## Constraints
- Production runs Python 3.11. `backend/.venv` is 3.11 with the production lock.
- Motored migrations auto-run on deploy.
- Never use `git stash`: it is shared across worktrees and holds the user's saved work.
- `app/core/security.py` is shared with UM. Changes there must keep UM behaviour, apart from the crash being fixed.
- Every Motored screen must work at tablet width (768–1024px).
- Every `<select>`/`<option>` must be explicitly styled.
- No backticks in CSS comments.
- Every field whose name is not obvious gets a tooltip.

## TDD
- Mode: strict.
- Backend: `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`, plus pg_real tests on a throwaway PG18 whenever SQL changes.
- Frontend: `cd frontend && npx jest`.

## Delivery
- Stacked-to-main slices from the worktree `feat/motored-encuesta-satisfaccion`.
- Each slice goes through gga + RDD consent + push.
- Coordinate with the F3 agent over a new Motored migration head.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Long passwords. `verify_password` returns False instead of raising above 72 bytes. Motored create and reset reject passwords over 72 bytes with a 422 and a clear Spanish message. | delegated writer (with T2) |
| T2 | `start.sh` stops printing the DB password. Print only host and database, or nothing. | delegated writer (with T1) |
| T3 | Change-own-password for web users (current + new + confirm), plus invalidation of existing sessions after an admin reset or an own change. Uses `password_changed_at` compared with the token `iat` (migration). Adds a "Cambiar mi contraseña" entry in the sidebar. | delegated writer |
| T4 | Login UX. Clear messages for 429 ("Demasiados intentos…") and 503. A "your session expired" notice after an automatic logout. Show/hide password toggle. `autocomplete` attributes. Labels tied to inputs and `role="alert"` on errors. A "¿Olvidaste tu contraseña? Contacta al administrador" line. Confirm field and min-length hint on create-user. | delegated writer |
| T5 | Survey per-cédula attempt limit. After N failed identifications for the same cédula within a window, answer 429 regardless of whether the cédula exists. In-memory, single process (as slowapi). | delegated writer |

- [x] T1 — verify_password returns False above 72 bytes (shared core, UM unchanged otherwise); Motored create/reset 422 "no puede superar 72 caracteres" (bytes); bootstrap script min 8/max 72. RED 9 → GREEN; motored 2647, UM 1296.
- [x] T2 — start.sh prints only host/db (python heredoc with `||` fallback; verified never aborts and never prints the password).
- [x] T3 — POST /api/motored/auth/password (actual+nueva, 5/min, fresh token, audited); tokens carry iat; migration b8d2f4a61c93 adds usuario.password_changed_at (set on admin reset and own change); older tokens → 401; "Cambiar mi contraseña" page /motored/mi-cuenta for all web roles. RED→GREEN; motored 2805, UM 1296, pg_real 78, jest 691.
- [x] T4 — login/mi-cuenta/reset map 401/429/5xx/network to clear Spanish messages (never [object Object]); session-expired notice via sessionStorage flag set only when a 401 clears an existing session; login: show/hide, autocomplete, labels, role=alert, autofocus, forgot-password line; create-user: confirm field, hint, maxLength 72, aligned row. RED 17 → GREEN; jest 95/711; next build OK; screenshots 390/820/1280 reviewed.
- [ ] T5

## Log
- 2026-09-30: document created from the audit (see pending-issues memory, "Auditoría de login Motored").
