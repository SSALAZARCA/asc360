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
- [x] T5 — per-cédula lock: 5 failures / 15-min fixed window → 429 "Demasiados intentos con esta cédula…" on /identificar and /respuestas; counts any cédula (no existence leak); success clears; in-memory, 10k cap, threading.Lock. Frontend shows backend detail. RED→GREEN; motored 2829, jest 712.

## Log
- 2026-09-30: document created from the audit (see pending-issues memory, "Auditoría de login Motored").
- 2026-09-30: ALL TASKS DONE (T1–T5). Still deferred by user: proxy/X-Forwarded-For (M4) and DB password rotation. Not requested: policy changes, forced first-login change, account lockout, email recovery.

## Follow-up round (user, 2026-09-30)
User asked: shorter session-expired notice, plus stricter password rules, forced change on first login, account lockout after failed attempts, and a log of who logs in and when. Sync with the F3 agent on Motored migrations (F3 has none pending; keep `supervisor_corridas.ensure_started()` in `deps.require_motored_ready`).

Defaults chosen (user can adjust):
- Password rules (new passwords only: create, admin reset, own change): min 10 chars, at least one letter and one digit, not a common password, must not contain the email local part. Existing passwords keep working.
- Forced change: admin create and admin reset set `must_change_password`; until changed the user can only reach the change-password page (enforced server-side); own change clears it.
- Lockout: 5 failed logins for an account within 15 min lock it for 15 min; unknown emails tracked the same way in memory so the response never reveals whether an account exists.
- Login log: every attempt (success/failure/locked) with email, user, IP, user agent, time; ADMIN-only screen to browse it.

| ID | Task | Route |
|---|---|---|
| T6 | Short notice "Tu sesión terminó. Vuelve a ingresar." | inline |
| T7 | Stricter password rules (backend policy + frontend hints) | delegated writer (with T8) |
| T8 | Forced password change on first login / after admin reset (migration) | delegated writer (with T7) |
| T9 | Account lockout after failed logins (migration) | delegated writer (with T10) |
| T10 | Login event log + ADMIN screen (migration) | delegated writer (with T9) |

- [x] T6 — notice shortened; RED 1 failed → GREEN 6 passed (motored-login-ux).
- [x] T7 — policy: min 10, letter+digit, ~120-entry denylist, no email local part (≥4); 72-byte max kept; new passwords only (old 8-char still log in); frontend rules in lib/motored/passwordRules.js.
- [x] T8 — usuario.must_change_password (migration c4e7a19b3d58 on b8d2f4a61c93); set on admin create/reset, cleared on own change; server 403 PASSWORD_CHANGE_REQUIRED everywhere except POST /auth/password; frontend forces /motored/mi-cuenta with banner. RED→GREEN; motored 3005, UM 1296, pg_real 91, jest 737.
- [ ] T9
- [ ] T10
