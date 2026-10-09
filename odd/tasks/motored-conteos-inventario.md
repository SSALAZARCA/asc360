# Motored: physical inventory counts (total and selective). Definition in progress.

## Objective
A new menu module for running total store counts and scheduled selective (cyclic) counts from the app. Counting uses barcode scanners or manual entry, and leaders follow progress and critical differences live.

## Owner decisions (2026-10-08)
- **Store state:** the count happens with the store CLOSED. Several stores can be counted at the same time.
- **Snapshot:** "Iniciar conteo" on a store COPIES that store's current system inventory (the latest Maestros inventory carga) into the conteo. The copy is frozen: later Maestros uploads, for example before another store starts, never change it.
  - Starting shows which carga the snapshot came from.
  - It warns if that inventory is stale.
- **Barcodes:** the label barcode equals the referencia code (no EAN). Lookup uses the existing normalized referencia code.
- **Devices:**
  - Mostly laptops with wired USB scanners (keyboard input).
  - Phones also work, by camera, Bluetooth scanner or manual entry.
  - The counting screen works on both: desktop layout and mobile-first layout.
- **Counters:** pairs from other company areas, with NO user accounts.
  - A pair enters both members' name and cédula once per device session. This is traceability only; no user is created.
  - Each device is one pair, and every reading is stored with its pair.
- **Access for pairs:**
  - ONE link per store conteo, shown as a QR for phones and as a copyable or short link for laptops, plus a short numeric code.
  - It is valid only while the conteo is open.
  - The leader sees the connected pairs (what each counted, current location), can disconnect a pair (its readings are kept) and can rotate the code (pairs already in keep counting).
- **Location first:** before counting, the pair sets a bin location (e.g. "Estante A3"). Every reading is stored with the current location until it changes.
  - Location labels can be printed with barcodes and scanned.
  - A referencia can sit in several locations: they are summed against the system, and a reconteo lists every location.
- **Blind count:** pairs never see the expected quantity.
- **Reconteo:** a mismatched referencia goes to reconteo, ideally by a different pair. A configurable MONEY threshold limits reconteos to differences above X pesos.
- **Critical:** a difference above a larger configurable MONEY threshold shows red, at the top, live.
- **New role LÍDER DE INVENTARIOS** (with a user account):
  - schedules and starts conteos;
  - gets the QR, link and code;
  - watches the live panel;
  - requests reconteos;
  - closes the conteo;
  - downloads the ERP adjustment list.

  ADMIN can do all of this. GERENCIA sees the panel and results read-only.
- **The app never changes stock.** Closing produces an adjustment list for the ERP.
- **Accuracy KPI per store:** the % of referencias that matched, and the difference in money. It allows comparing stores and following the trend.
- **Selective counts:** the app generates a weekly short list per store, prioritizing high-rotation or high-value referencias (ABC). Details are still to be defined.

## Planned stages
1. Total count (scanner and manual, blind, locations, pairs, reconteo, close).
2. Live panel (progress, critical differences, alerts, pairs).
3. Automatic selective counts (weekly scheduling).
4. ERP adjustment list and accuracy history.

## Open questions
- RESOLVED 2026-10-08: differences are valued at the inventory file's "Costo prom. uni." per referencia and bodega, frozen in the snapshot. Thresholds and selective rules live in Configuración, new tab "Conteos de inventario".
- RESOLVED 2026-10-08 selective counts:
  - **ABC by sales money per store.** Thresholds (default 80/15/5) and frequencies (default A monthly, B quarterly, C semiannual) are configurable.
  - **Always included:** referencias with a difference in the last count, negative system stock, and selling with zero stock.
  - **Weekly list per store,** size configurable (default 40), auto-generated.
  - **Counted by the store's asesores (Lore users)** in a Telegram Mini App opened from a Lore message button. Telegram identifies the asesor; a shared Telegram asks for the cédula. It can be resumed, and differences go to the leader panel.
  - **Counted at store opening, store OPEN,** against that morning's inventory. A selective difference is confirmed only if it repeats in a next-day reconteo.
- RESOLVED 2026-10-08: a total-count reconteo MUST be done by a different pair; the first pair never sees it. With only one pair in the store, the leader can authorize that same pair.
- RESOLVED 2026-10-08: no ERP import template yet. Closing generates a downloadable Excel (referencia, bodega, system qty, counted qty, difference, unit cost, difference value, locations). The owner will send the ERP format later if it must change.
- 2026-10-08: the owner approved the screen prototypes (artifact https://claude.ai/artifact/Eq1mconFxKgnLzhkENW89G): leader panel, start count, laptop count, pair join, phone count, Telegram mini app. Technical design: odd/design/motored-conteos-inventario.md.
- 2026-10-08 owner decision: counts are per STORE (sucursal), not per bodega.
  - The snapshot sums all of the store's own bodegas (principal + secondary), and readings and locations carry no bodega.
  - The ERP adjustment Excel assigns each referencia's whole difference to that SAME store's principal bodega.
  - Associated stores (`principal_id`) are not merged into a count.
  - This supersedes the design's per-bodega location tagging (open question 2).
- 2026-10-08: default thresholds are reconteo above $100.000 and critical above $500.000, both editable in Configuración.
- 2026-10-08 leaders: each conteo has ONE assigned LIDER_INVENTARIOS, which can differ per store and per count.
  - Only ADMIN schedules counts and assigns the leader.
  - Only the assigned leader can start, watch, request reconteos and close that count; other leaders neither see nor touch it.
  - ADMIN sees and manages all counts; GERENCIA sees all, read-only.

---

## STAGE 1 BUILD PLAN (ready to start 2026-10-09)

**Status:** the definition is closed and the prototypes are approved. Building has NOT started. Stage 1 = the total count.

### Sources of truth, in priority order
1. **This file:** the owner decisions above.
2. **The technical design,** `odd/design/motored-conteos-inventario.md`: data model §4, state machines §5, API §6, counting rules §7, security §8, performance §9, frontend §10, files §11, delivery §12, tests §13.
3. **The approved prototypes:** https://claude.ai/artifact/Eq1mconFxKgnLzhkENW89G. Build the screens to match them, and diff the final JSX against them before closing UI tasks.

### Owner decisions that OVERRIDE the design doc
Apply these when building.
- **Count per STORE, not per bodega** (design §4.3/§4.10/§7/WU10):
  - the snapshot = the sum of the store's own bodegas per referencia;
  - `ubicacion_inventario` has NO bodega column;
  - at close, each referencia's whole difference is attributed to the store's PRINCIPAL bodega (multi-bodega attribution in WU10 = "everything to principal");
  - keep the per-bodega system quantities in the snapshot only for the Excel's informative columns.
- **Default thresholds:** reconteo $100.000 (the design used a $50.000 placeholder) and critical $500.000.
- **Leader assignment** (design §6.1/WU6):
  - `conteo.lider_id` (FK usuario, required for TOTAL);
  - only ADMIN creates or schedules a conteo and assigns its leader;
  - LIDER_INVENTARIOS sees and acts ONLY on conteos where `lider_id` = self (404 on others, never 403, so ids don't leak);
  - ADMIN does everything on all conteos; GERENCIA reads all conteos and writes nothing.
- **Role identifier:** `LIDER_INVENTARIOS` (UI label "Líder de inventarios").

### Work units
Each is about 400 changed lines or less, with one work-unit commit, tests alongside, and conventional commits.

| ID | What | Depends on |
|---|---|---|
| WU1 | Role `LIDER_INVENTARIOS`: enum migration on top of the current head (check it; it was `d7a3c5e91f20`), `MotoredRole`, `deps.py` allowlist (leader: auth + `/api/motored/conteos`; GERENCIA gets `/api/motored/conteos` read-only via method checks), frontend wiring (`session.js`, `motored-layout.js` VALID_ROLES and redirect, `MotoredSidebar.js` new group "Inventarios" → "Conteos", `permisosPorRol.js`, user form, `useTableroGate` untouched). Follows exactly the pattern of 9b209f8/b7258b7 (COORDINADOR_REPUESTOS). | none |
| WU2 | Migration plus models `conteo` (with `lider_id`), `conteo_snapshot_linea` (per sucursal+referencia, bodega quantities informative), `ubicacion_inventario` (per sucursal, no bodega). | WU1 |
| WU3 | Migration plus models `conteo_sesion`, `conteo_integrante` (cédula stored, never echoed), `conteo_lectura` (client UUID, idempotent), `conteo_reconteo`, `conteo_acceso_intento`, `conteo_resultado`. | WU2 |
| WU4 | Configuración tab "Conteos de inventario": keys for the reconteo amount (100000), critical amount (500000) and stale inventory hours. Validation: reconteo < critical. Tooltips. | none |
| WU5 | `services/conteos/snapshot.py`: schedule; Iniciar = ONE SQL statement that resolves the store's latest non-ANULADO INVENTARIO carga and copies its rows; the cost fallback (other bodega → median → precio_normal → SIN_COSTO flag); the staleness warning; annul. `acceso.py`: slug plus 6-digit code (hash only). | WU2, WU4 |
| WU6 | Leader API part 1: list / create (ADMIN) / reschedule / detail / iniciar / qr.png / rotate code, with leader scoping (own conteos only). Router wiring. | WU5 |
| WU7 | Pair access, public: unirse (code + 2 names + 2 cédulas), attempt counters (5 → 15 min lock; 30/hour → auto-rotate), session dependency, sesion, salir. Leader: list sessions, disconnect. | WU3, WU6 |
| WU8 | Readings: catálogo (ETag), ubicaciones, set location, POST lecturas (batch ≤100, idempotent), void, recent. **Blind guard:** a test fails if any pair response carries expected qty, cost or difference. | WU7 |
| WU9 | Reconteo: end round, differences valued at the frozen cost, threshold candidates, manual add, assignment to a DIFFERENT pair (disjoint cédula sets), leader override only with no other eligible pair (reason stored), auto-assign, pair tasks. | WU8 |
| WU10 | Close: guards, force close, `conteo_resultado` (final qty rule, everything to the principal bodega, cost fallback), accuracy KPI (count % and money), adjustment Excel download (referencia, bodega principal, system qty, counted qty, difference, unit cost, value, locations). | WU9 |
| WU11 | Leader UI 1: list, schedule (ADMIN picks store + leader + date), start with the staleness warning, access card (QR, link, code, print QR). Matches the prototype "Iniciar". | WU6 |
| WU12 | Leader UI 2: live panel (polling every 5 s visible / 30 s hidden, version short-circuit), pairs + disconnect, reconteo control, close dialog. Matches the prototype "Main". | WU9, WU10, WU11 |
| WU13 | Pair UI 1: public route, join screen, session persistence, location bar, USB scanner input (keyboard bursts + Enter), manual entry, offline queue + retry, sounds. Matches "IngresoPareja" and "ConteoPortatil". | WU8 |
| WU14 | Pair UI 2: mobile layout, camera scanning (dynamic import), reconteo tasks tab. Matches "ConteoCelular". Manual check on Android + iPhone, plus tablet screenshots. | WU13 |

- [x] WU1 (0339642 backend + migration b4f9c2e6a813, d0ba5c2 frontend; backend 6719 passed, pg_real 814 passed, jest 2457 passed; route: delegated writer)
- [x] WU2 (e252dc4, migration c3e7a1f50d24)
- [x] WU3 (e252dc4, migration d58b2c9e4a17 = head; backend 6735 passed, pg_real 855 passed; route: delegated writer; SIN_COSTO valor_diferencia left nullable, decide in WU10)
- [x] WU4 (32866b4; backend 6808 passed, jest 2465 passed)
- [x] WU5 (4c0545c; pg_real 878 passed; slug is 96 bits, String(16), accepted with the 6-digit code and rate limits)
- [x] WU6 (cfc65c6; backend 6887 passed, pg_real 888 passed). Public URL <MOTORED_PUBLIC_URL>/motored/c/<slug>; lock = 429; no consent checkbox (notice only, per prototype)
- [x] WU7 (cfc65c6). Pending for WU9: release a disconnected pair's reconteos. Pending for WU12: a leader notice when the code auto-rotated
- [x] WU8 (ec9e753; backend 6957 passed, pg_real 900 passed). Unknown codes are not stored unless forzar_desconocido; no per-IP limit on lecturas (a store shares one IP). Follow-up: functional index on upper(btrim(referencia.codigo)) needs a migration
- [x] WU9 (ac2bcf8 rebased; backend 7182 passed after rebase, pg_real 911 passed). Thresholds inclusive (>=, matches the approved panel "desde"); reconteo origen UMBRAL/LIDER; only the current assignee's round-2 readings count; `cantidad_final(ronda1, estado_reconteo, ronda2)` for WU10. Alembic head is now f6b2d8a35c71 (another session added 2 migrations on top of d58b2c9e4a17)
- [x] WU10 (dfe6ab7; backend 7229 passed, pg_real 926 passed). Principal bodega = bodega.codigo = sucursal.bodega_principal (409 SIN_BODEGA_PRINCIPAL otherwise); KPI universe excludes 0-vs-0; unknown codes only in the "Sin costo" sheet; avance.xlsx also built
- [x] WU11 (3663aee; jest 2557 passed; no barcode labels: they print UBI-<code> as text, since that needs a library)
- [x] WU12 (3663aee; polling 15/60 s plus the idle-pair yellow mark and close warning)
- [x] WU12b (24c4557 backend, 32cff10 UI; backend 7245 passed, pg_real 934 passed, jest 2564 passed). GET /conteos/{id}/panel?version=: a version hash plus sin_cambios short-circuit, progress, partial accuracy, readings per pair; the list carries progreso
- [x] WU13 (d0014b3; jest 2590 passed). Public /motored/c/<slug>; queue in localStorage; corrections = void + new reading
- [x] WU14 (d0014b3). Camera via native BarcodeDetector (Android); hidden on iPhone, so manual entry or a BT scanner
- [x] WU13b (8748441 backend, 89d866e UI; backend 7259 passed, pg_real 937 passed, jest 2593 passed). Each reading carries ubicacion_codigo (created if new); location can change offline; the session location follows the newest reading
- [ ] Manual device checks: Android camera, iPhone manual/BT, real USB scanner, tablet screenshots, real offline test.
- [ ] Widen CONTEOS_ROLES_VISIBLES to ADMIN, LIDER_INVENTARIOS and GERENCIA after WU13b and an owner test.

### Visibility while building
Until WU12 lands, the sidebar group "Inventarios" shows only to ADMIN, so nothing half-built is exposed.

### Checks per work unit
Run them in the foreground and read the result line before committing; never chain tests with commit or push.
- Backend: `cd backend && env -u MOTORED_DATABASE_URL -u MOTORED_TEST_PG_URL .venv/bin/python -m pytest tests/motored -q -p no:warnings`. Must show 0 failed.
- pg_real on a throwaway PG18 (127.0.0.1, `unix_socket_directories=''`, own port and data dir): alembic_motored `upgrade head`, plus `downgrade -1` / `upgrade head` when there is a migration, then the full `-m pg_real`. Must show 0 failed. Clean up afterwards.
- Frontend: `cd frontend && npx jest`, full. The Tests line must show 0 failed.
- gga reviews WHOLE files: Python lines ≤79, functions ≤50, exactly 2 blank lines after classes and top-level defs, explicit style on every `<option>`.

### Coordination
- Session `fe` (KPI): ping before any migration so the alembic heads chain cleanly.
- Session `43` (manuals/audit).

### Routing
- Delegate WU1, WU2 + WU3, and each UI unit to one bounded writer with an explicit allowed-edit-surface list.
- The parent spot-checks, commits and pushes.

### Later stages (not started)
- Stage 2: polish the live panel (most of it lands in WU12).
- Stage 3: selective counts plus the Lore Mini App. Pending owner details:
  - overflow when the always-included items exceed the list (proposal: fill the list and carry the rest over);
  - meaning of "repeats" (proposal: a difference with the same sign the next day);
  - the ABC sales window (proposal: 6 months).
- Stage 4: accuracy history.

### Resume steps
1. `mem_search` "odd/motored-conteos-inventario".
2. Read this file and the design doc.
3. Check the alembic head.
4. Start WU1.
- 2026-10-09 owner: the leader panel polls every 15 s visible / 60 s hidden, stops when CERRADO, and has an "Actualizar ahora" button. This supersedes the design's 5 s / 30 s.
- 2026-10-09 owner: the leader panel marks in YELLOW any pair with no activity for over 2 minutes ("Sin actividad hace N min"). Closing warns, listing those pairs, because they may hold unsent offline readings; the leader can still close. Pairs never see it.
- Offline behaviour (WU13): readings are queued on the device and shown at once; the catalogue is cached; a "Sin conexión · N pendientes" banner shows; sync is automatic and idempotent; a warning shows before closing the tab with pending readings.
