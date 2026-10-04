# Motored: early warning before pedido input data goes stale

## Objective
Warn COMPRAS before a pedido input (inventario, backorder, facturas, ingresos) reaches its staleness limit (`max_dias_antiguedad_*`, default 7 days), so the data is refreshed before the weekly corrida is blocked.

## Owner decisions (2026-10-03, Engram `motored/aviso-anticipado-antiguedad`)
- Two warnings per dataset and due date (Bogotá time):
  - Day before the due day at 16:30.
  - Due day at 08:30.
  - The due day is the last day the data is still valid: data loaded on D with limit L is due on D+L, and corridas block from D+L+1.
- In-app banner on the Pedidos screens from the day before onward.
- Telegram: the backend sends the message itself through the Lore bot (Telegram Bot API `sendMessage` with Lore's token) to COMPRAS users with a linked Telegram. The lore-bot process is not changed.
- Each (dataset, threshold, due date) is sent at most once. Sending is idempotent and survives restarts.
- Open: whether ADMIN also receives it. Default is COMPRAS only (`ROLES_DESTINO`).
- COMPRAS self-links Telegram exactly like ADMIN (coordinator, 2026-10-03).

## Constraints
- Python 3.11 (prod), with deps pinned in `backend/requirements.lock.txt`. Never use `field(default=<unhashable>)`.
- The Motored DB has its own Alembic chain. Chain on main's current head (`f3a8d1c5b704` unless it moved).
- Engine and corrida behavior are unchanged. This feature only reads the same freshness data the corrida preflight uses (`services/corridas/vigencia.py`).
- Lore's token is read from the existing env name `LORE_BOT_TOKEN` (Settings field `LORE_BOT_TOKEN`, empty by default). The Coolify app-level env list already defines it for lore-bot and Coolify injects that list into every service, so the owner configures nothing. Without it, Telegram sending is skipped and logged once, and the in-app banner still works. If the token turns out to be absent in the backend container, the fix is one line, `- LORE_BOT_TOKEN=${LORE_BOT_TOKEN}`, under backend `environment` in `docker-compose.coolify.yml` (not edited here).
- No secrets in logs.
- gga style; tablet layout 768–1024 px; style every `<option>`; no backticks in `themeCss` comments.

## TDD
- Mode: strict, source is the project rules.
- Backend: `cd backend && .venv/bin/python -m pytest tests/motored -q`, plus `-m pg_real` on a throwaway PG 18.
- Frontend: `cd frontend && npx jest`.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Backend: compute upcoming due dates per dataset; a daily job (loop like the corridas supervisor) that sends the 16:30 and 08:30 Telegram warnings via Lore's token to linked COMPRAS users, idempotent per (dataset, threshold, due date); a read endpoint for the banner. Frontend: the banner on the Pedidos screens. | delegated writer (2+ non-trivial files) |

- [x] T1 (working tree, not committed yet; commit pending the coordinator)

## Log
- 2026-10-03: feature document created after the owner's decisions.
- 2026-10-03: T1 implemented (route: delegated writer; triggers: 2+ non-trivial files, backend plus frontend). Not committed.
  - Backend: `services/avisos_antiguedad.py` (due dates reusing `vigencia._elegir`/`_TIPOS` and `cargar_parametros_corrida` limits; idempotent reserve via INSERT ON CONFLICT DO NOTHING on `aviso_antiguedad_enviado`), `services/avisos_telegram.py` (httpx Bot API, never logs token, masks chat), `services/trabajos/supervisor_avisos.py` (lazy loop, tick every `MOTORED_AVISOS_POLL_SEGUNDOS`=60, kill switch `MOTORED_AVISOS_ANTIGUEDAD_ENABLED`), `api/avisos_antiguedad.py` (`GET /api/motored/avisos-antiguedad`, ADMIN/COMPRAS), migration `b5d91e3a7c42` (head, chained on `f3a8d1c5b704`).
  - Inventario is global in the preflight (one carga for the whole network), so the alert is per dataset, not per sucursal. One message per threshold lists all affected datasets.
  - Late tick (restart) still sends the same day; total send failure releases the reservation and retries next tick.
  - Frontend: `AvisoAntiguedadBanner` + `useAvisosAntiguedad` on the Pedidos list and corrida detail; failure is silent; dismiss control 44 px.
  - Follow-up (same day): `vigencia.py` now exposes `TIPOS_ANTIGUEDAD` and `elegir_carga_vigente` (thin public wrappers, behavior unchanged) and the aviso module uses them. COMPRAS can self-link Telegram: `POST /usuarios/me/telegram/codigo`, `DELETE /usuarios/me/telegram` and new `GET /usuarios/me/telegram` (`{telegram_vinculado}`) accept ADMIN and COMPRAS; SUCURSAL, CONSULTA, SERVICIO_CLIENTE get 403. UI: `TelegramVinculoPanel` in Mi cuenta (ADMIN and COMPRAS; the Usuarios page is ADMIN-only so COMPRAS never saw it).
  - Lore check (read only, lore-bot untouched): `POST /admin/vincular` and `consumir_codigo_vinculacion` have no role check, so a COMPRAS code is accepted. Cosmetic only: the bot replies "Vinculado como administrador" and `/yo` shows "usuario" for non-ADMIN/asesor roles.
  - Still open for the owner: ADMIN also receiving the alert.
  - Checks: backend tests/motored 4612 passed; UM 1296 passed; pg_real 408 passed, 2 skipped (PG 18 throwaway, removed); jest 1504 passed (152 suites).
