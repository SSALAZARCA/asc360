# Motored: workshop satisfaction survey and detractor management

## Objective
Customers who took their motorcycle to a Motored workshop receive a WhatsApp message from the CRM "Escala". The message ends with ONE generic link. The customer opens the survey, identifies themselves with their cédula, and answers the Google Form "ENCUESTA TALLERES" questions. Responses are stored in Motored. Customers whose overall satisfaction is 3 or lower open a detractor case, managed centrally in a panel with an append-only action log.

## Problem / why
- Today the survey lives in Google Forms. The answers are disconnected from the customer base, and nobody manages detractors.
- Escala cannot put a per-customer link into the message, so we must identify the customer inside the survey.

## Decisions (user, 2026-09-29)
- **Questions:** exactly the Google Form questions (verbatim below). The 7 identity fields are NOT asked; they come from the uploaded base.
- **Visual design:** follow `Motored/Medicion de NPS/Encuesta Motored (offline).html` (outside the repo). That means:
  - Manrope, red `#E20714`, gray header `#F2F2F0` with the logo and a skewed red stripe, and a progress bar.
  - One question per screen, 44px+ touch targets, and a sticky footer with "Atrás" and a red CTA.
  - Sharp corners and `prefers-reduced-motion`.
  - Closing and state screens.
- **Scope:** only the workshop survey (TIPO = Servicio taller) for now. The sales survey comes later with the same structure, so TIPO stays as data.
- **Customer base:** an Excel with Nombre, Cédula, Celular, Línea, Placa, SIC, Centro de servicio and TIPO (Venta / Servicio taller), uploaded into Motored before Escala sends.
- **Identification:** the first screen asks for the cédula.
  - **Not found:** block the survey and show "No encontramos esa cédula. Recuerda ingresar la cédula de la persona a cuyo nombre está registrada la motocicleta. Revísala e intenta de nuevo."
  - **Several pending records:** the customer chooses by placa.
  - **All records answered:** show "Ya recibimos tu calificación".
  - One response per record.
- **Detractor rule:** a case opens when overall satisfaction is 3 or lower. The matrix does not trigger cases.
- **Case workflow:** ABIERTO → EN_GESTION → CERRADO. A closed case has a result of RECUPERADO, NO_RECUPERADO or NO_CONTACTABLE.
  - The log is append-only and records who, when and what: calls, WhatsApp, notes, state changes and compensation offered.
  - Corrections are new entries.
- **Roles:** a new role SERVICIO_CLIENTE sees only this module. Management is centralized, and ADMIN has full access.
- **Consent "No":** the response is stored, and a case still opens if satisfaction is 3 or lower. The panel shows a prominent "Cliente NO autorizó tratamiento de datos" warning.
  - The user chose this knowing that Ley 1581 has no explicit exception for it.
  - We suggested a legal review of the privacy policy.

## Survey questions (verbatim from the Google Form)
- **Intro:** "En estos momentos estamos haciendo un estudio sobre la satisfacción del servicio de posventa prestado en nuestros talleres."
- **Q1 (required, 1-5):** "En una calificación de 1 a 5, donde 5 es "Muy Satisfecho" y 1 es "Muy Insatisfecho", en general, ¿qué tan satisfecho se siente usted con el servicio de posventa recibida por el taller?"
  - The end labels are MUY INSATISFECHO (1) and MUY SATISFECHO (5).
- **Q2 (required, matrix 1-5 plus NS/NR per row):** "Pensando en su experiencia en el taller al que asistió, por favor califique utilizando la misma escala de 1 a 5, donde 5 es "excelente" y 1 es "pésimo", como califica usted:"
  1. La explicación y asesoría técnica que le dieron en el taller de los problemas que tenía la moto
  2. La confianza en la reparación de la motocicleta realizada por el taller o centro de servicio
  3. Servicio que le prestaron en el taller o centro de servicio
  4. La calidad del trabajo realizado por los mecánicos
  5. La claridad en la explicación recibida de los cobros realizados antes y después del servicio
  6. La confianza en la procedencia y originalidad de los repuestos
- **Q3 (optional, free text):** "¿Qué observaciones tiene respecto al servicio que obtuvo en el taller?"
- **Q4 (required, Sí/No):** "PHD2. Dando cumplimiento a la ley de Protección de Datos Personales le solicito su autorización para que Motos red Nacional pueda contactarlo nuevamente en caso de ser necesario con fines de supervisión de esta encuesta y futuras encuestas. ¿Está usted de acuerdo?"

## Assumptions (to confirm with user, non-blocking)
- The public URL is `/motored/encuesta`.
- **Closing screens:**
  - Satisfied (4-5): thank you.
  - Detractor (3 or lower): "Gracias por decírnoslo. Nuestro equipo de servicio al cliente te va a contactar", with the case number and no promise of hours.
- No Google review link and no photo upload for now.
- Excel rows with TIPO = Venta are stored, but the survey only serves Servicio taller records until the sales survey exists.
- Each upload is a batch (`carga`). A record is unique per (cédula, placa, batch).

## Constraints and technical notes (from mapping, 2026-09-29)
- **Data model:** own engine `MotoredBase`. UUID PKs, naive UTC `created_at`, and String status columns with `ck_<table>_<col>` CHECK constraints.
- **Migrations:** the Alembic chain is `backend/alembic_motored` and its head is `a3f7c91d2e58`.
  - Adding a `motored_role` value needs its own revision with `autocommit_block` (precedent `d0f33eb07f78`).
  - Motored migrations seem to be run MANUALLY in deploy. `start.sh` runs only the asc360 chain; this must be confirmed before merge.
- **Authorization gap:** many Motored read endpoints only require an authenticated user. SERVICIO_CLIENTE must be denied server-side outside survey routes, not only hidden in the UI.
- **Public endpoints:** there is no public Motored endpoint yet. Rate-limit with slowapi `@limiter.limit` (`app/core/limiter.py`), plus a per-cédula attempt bound, because cédulas are guessable.
- **Excel template to copy:** `api/carga.py` with `services/carga_excel.py`. It gives a bounded read, a row cap, header aliases, and all-or-nothing validation with a `{ok, errores[{fila, motivo}]}` response. Cast numeric cells to text for cédula and celular.
- **Frontend:**
  - Public pages render under `MotoredRootLayout` without `MotoredLayout`.
  - Role lists live in `motored-layout.js:28` (VALID_ROLES), `usuarios/page.js:43` (ROLES), `MotoredSidebar.js:47-51,90` (adminOnly filter), and the login redirect in `login/page.js:42`.
  - Manrope is not loaded yet. Load it via `next/font/google` only for the survey.
- **`<select>` styling:** every new `<select>` needs an explicit style on each `<option>`.
- **Tooltips:** fields with non-obvious names (SIC) need a tooltip.
- **Tablet support:** every screen must work at 768-1024px.

## TDD
- **Mode:** strict. The source is the project's ODD convention (`odd/tasks/motored-salir-y-cambio-password.md`).
- **Backend:** from `backend/`, run `.venv/bin/python -m pytest tests/motored -q`.
- **Frontend:** from `frontend/`, run `npx jest`.
- **Worktree:** `../Aplicación red de servicio - encuesta`, branch `feat/motored-encuesta-satisfaccion`.
  - `.venv`, `node_modules` and `.env` are symlinked from the main checkout and excluded through `.git/info/exclude`.

## Delivery
- Strategy: **stacked-to-main** (user decision 2026-09-29): every slice goes to `main` (auto-deploy via Coolify on push) and must be testable in production on its own; no half-built UI exposed (menu entries/public page only land when their backend is live).
- Work-unit commits on `feat/motored-encuesta-satisfaccion`, then fast-forward/push each slice to `origin/main` after rebasing on the latest `origin/main` (another agent also pushes to main from the other checkout).
- Forecast ~3000 authored lines. RDD on (default): after each work-unit commit run `gentle-ai review assess --committed-only`.
- VERIFIED 2026-09-29: `backend/scripts/start.sh:6` runs only the asc360 chain (`alembic upgrade head`); `alembic_motored` is NOT run on deploy. Any slice with a Motored migration needs the migration applied in production — how is pending user answer.

## Tasks
| ID | Task | Route |
|---|---|---|
| T1 | Role SERVICIO_CLIENTE (backend). Add the enum value plus an autocommit migration. Enforce a server-side allow-list so this role only reaches survey and case routes. Let the usuarios API accept the role. Tests. | delegated writer |
| T2 | Data model plus migration. Tables: `encuesta_carga` (batch), `encuesta_registro` (the 7 fields, tipo, respondida), `encuesta_respuesta` (q1, 6 matrix answers nullable for NS/NR, observaciones, autoriza_datos), `caso_detractor` (estado, resultado, timestamps) and `caso_detractor_accion` (append-only, with a PG trigger blocking UPDATE/DELETE). Tests. | delegated writer |
| T3 | Customer-base Excel upload (backend): template download, validate (dry run) and commit. ADMIN and SERVICIO_CLIENTE only. Tests. | delegated writer |
| T4 | Public survey API. The cédula lookup is rate-limited and returns only pending records (placa, línea, first name). The submit validates cédula plus record, stores the response once, and opens a case when q1 is 3 or lower. Tests. | delegated writer |
| T5 | Detractor case API: list with filters, detail with response and consent flag, add an action, change state (auto log entry), and close with a result. Tests. | delegated writer |
| T6 | Public survey page (frontend), styled like the offline HTML. Screens: cédula, placa choice, Q1, matrix, observaciones, consent, closing, not found, already answered. Tests. | delegated writer |
| T7 | Admin frontend. Role plumbing (VALID_ROLES, ROLES select, login redirect, sidebar role filter), plus "Encuesta satisfacción" and "Detractores" menu entries and the base upload page. Tests. | delegated writer |
| T8 | Detractor panel (frontend): list, case detail, action log, add action, state change and close, and the consent warning badge. Tests. | delegated writer |
| T9 | (moved first — blocks slice 1) Deploy readiness. Confirm how Motored migrations run in Coolify, document the steps, and check the link-preview metadata for the public page. | inline |

## Progress
- [x] T1 — slice 2, commit 135276f on main. Route: delegated writer (sonnet). `MotoredRole.SERVICIO_CLIENTE`, migration `7be41d9c0a26` (autocommit ADD VALUE), confinement in `deps.get_current_motored_user` via `SERVICIO_CLIENTE_ALLOWED_PREFIXES` (/api/motored/auth, /encuesta, /detractores; segment-boundary match). TDD: RED = ImportError at collection; GREEN tests/motored 1180 passed, asc360 suite 1292 passed. gga: 1 finding fixed (dynamic import in test). RDD: medium, granted, 1-lens (reliability) approved, acknowledged (review-8098f351527b23c7).
- [x] T2 — slice 3. Route: delegated writer (sonnet). 5 models + migration `c4e81a7d3f26` (down `7be41d9c0a26`), append-only PL/pgSQL trigger on `caso_detractor_accion`, `caso_detractor.numero` Identity. TDD: RED = 2 collection errors; GREEN tests/motored 1198 passed, asc360 1292 passed. Offline `alembic upgrade --sql` DDL inspected (valid for PG16); NOT executed on a live Postgres (no docker in WSL).
- [x] T3 — slice 4. Route: delegated writer (sonnet). `/api/motored/encuesta/cargas` (GET plantilla, POST validar, POST commit, GET list) for ADMIN+SERVICIO_CLIENTE; reuses carga_excel/carga helpers; all-or-nothing; normalizes cédula/placa/celular/tipo; VENTA advertencia. TDD: RED 39 failed (404) → GREEN; tests/motored 1376 passed, asc360 1292 passed. List query (correlated count + outer join) not run on live Postgres.
- [x] T4 — slice 5. Route: delegated writer (sonnet). Public `/api/motored/encuesta/publico/identificar` (NO_ENCONTRADA/YA_RESPONDIDA/PENDIENTE, minimal payload, 10/min/IP) and `/respuestas` (20/min/IP; 404 indistinguishable mismatch; 409 on duplicate incl. IntegrityError race; case + APERTURA when q1<=3, consent-No noted). Shared `normalize_cedula`. Dedupe: newest registro per placa decides. TDD: RED 29 failed → GREEN 31; tests/motored 1407 passed, asc360 1292. Not run on live Postgres; no per-cédula bound yet (per-IP only).
- [x] T5 — slice 6. Route: delegated writer (sonnet). `/api/motored/detractores`: GET list (filters estado/centro/autoriza/desde/hasta/q, paginated, conteo_por_estado), GET detail (registro, respuesta, autoriza_datos, log), POST acciones (LLAMADA/WHATSAPP/NOTA/COMPENSACION/CORRECCION; closed cases only NOTA/CORRECCION), POST estado (ABIERTO→EN_GESTION|CERRADO, EN_GESTION→CERRADO; no reopen; SELECT FOR UPDATE; auto CAMBIO_ESTADO; asignado_a on EN_GESTION). TDD: RED 43 failed → GREEN 47; tests/motored 1454, asc360 1292. Not run on live Postgres.
- [x] T6 — slice 7. Route: delegated writer (sonnet). Public page `/motored/encuesta` (container EncuestaContainer + presentational screens in components/motored/encuesta, Manrope for this route only, CSS scoped `.enc-root`). TDD: RED module-not-found → GREEN 23 tests; full jest 80 suites / 588 passed; `next build --webpack` compiles (Turbopack build fails only on the worktree node_modules symlink). Parent visual check: full mocked flow screenshotted at 390x844 (detractor) and 1024x768 (satisfecho) — cédula, placa picker, Q1, matrix, observaciones, consent, both closings render as in the reference HTML.
- [x] T7 — slice 8. Route: delegated writer (sonnet). SERVICIO_CLIENTE role plumbing (VALID_ROLES, usuarios ROLES "Servicio al cliente", login redirect, MotoredLayout allow-list redirect, useAdminGate), sidebar `roles` field + "Encuesta satisfacción" entry (ADMIN, SERVICIO_CLIENTE), page /motored/encuesta-satisfaccion (copy survey link, upload base: template/validate/save, batches list with % respondidas, SIC tooltip). TDD: RED 12 failed → GREEN; full jest 87 suites / 627 passed; next build --webpack OK. Parent reviewed screenshots 1280/820 both roles.
- [x] T8 — slice 9. Route: delegated writer (sonnet). Sidebar "Detractores" (ADMIN, SERVICIO_CLIENTE); /motored/detractores list (estado tabs with counts, debounced filters, pagination, NO AUTORIZÓ badge) and /motored/detractores/[id] detail (consent warning banner, cliente card with tel/WhatsApp, verbatim matrix + NS/NR, historial, registrar acción, tomar/cerrar caso with resultado; 409 reload). useDetractoresGate. TDD: RED module-not-found → GREEN 39 tests; full jest 90 suites / 666 passed; next build --webpack OK. Parent reviewed screenshots.
- [x] T9 — slice 1: `backend/scripts/start.sh` now runs `alembic -c alembic_motored.ini upgrade head` after the asc360 chain, gated on `settings.MOTORED_DATABASE_URL`, non-fatal (`|| echo`). Route: inline (1 mechanical file + static test). TDD: RED 4 failed → GREEN 4 passed; full `tests/motored` 1137 passed. User confirmed 2026-09-29 they never ran Motored migrations by hand; prod log 2026-09-29 shows only the asc360 chain running on start.

## Log
- 2026-09-29: Created the worktree and the document. Mapping done (reference HTML, spec folder, Motored module patterns).
- 2026-09-29: user chose stacked-to-main slices; consent text company -> "Moto red Nacional"; verified Motored migrations are not auto-run on deploy.
- 2026-09-29: slice 1 (T9) delivered to main as f924e67 (rebased twice on origin/main; tests 1157 passed after rebase). RDD: risk high (shell/start.sh), consent granted, 4-lens review approved, acknowledged (lineage review-86ef86e669950456, authority burned). Pending: user confirms prod deploy log shows "Corriendo migraciones de Motored".
- 2026-09-29: slice 9 (T8) delivered to main as 5f26f55. RDD medium, 1-lens approved + acknowledged. ALL TASKS DONE (T1–T9).

## Close (2026-09-29)
Status: functionally complete, 9 slices on main (f924e67, 135276f, fb34c82, 97c550c, 7d31ed4, 5993af3, 5893b8b, f6a0fc6, 5f26f55). Production deploys confirmed Success through fb34c82; Motored migrations auto-applied (prod at head).
Pending / not verified:
1. No test ran against a live Postgres (no docker in WSL): do an end-to-end production check (upload a small Excel with your own cédula → answer at /motored/encuesta with 3 or less → case in Detractores → take/close).
2. Rate limit is per IP only (in-memory, per process); no per-cédula bound.
3. Confirm SIC tooltip text on the upload page (inferred) and the spelling "Moto red Nacional" in Q4.
4. Closed cases cannot be reopened (default decision).
5. Sales (VENTA) survey not built yet; TIPO=VENTA rows are stored but not surveyed.
6. Consent "No" still opens a case (user decision, legal risk acknowledged) — validate privacy policy with legal.
Next step: user runs the end-to-end production check; then decide on items 2–5.

## Follow-up (user decisions 2026-09-29, after close)
- Q4 company name is "Motos red Nacional" (user-confirmed spelling), replacing "Moto red Nacional".
- Closed cases CAN be reopened (reverses the no-reopen default).
- Fix the lookup attempts protection (approach pending user choice).
- Sales survey stays pending; legal (consent "No" still opens case) stays as is.

| ID | Task | Route |
|---|---|---|
| T10 | Q4 text "Motos red Nacional" (frontend copy + tests + this doc) | delegated writer (with T11) |
| T11 | Reopen: CERRADO → EN_GESTION with comentario; clears resultado/cerrado_at; CAMBIO_ESTADO logged; "Reabrir caso" button in detail | delegated writer |
| T12 | Lookup protection, option B (user decision 2026-09-29): identify with cédula + last 4 digits of celular; Celular becomes REQUIRED in the customer-base upload (Escala sends the WhatsApp to it). Same generic error for any mismatch; respuestas re-validates both; per-IP limit kept. | delegated writer |

- [x] T10 — "Motos red Nacional" in copy.js + verbatim test + doc. RED 3 failed → GREEN.
- [x] T11 — CERRADO→EN_GESTION reopen (clears resultado/cerrado_at, keeps or sets assignee, CAMBIO_ESTADO "Caso reabierto: …"), "Reabrir caso" button. RED 2 backend + 3 frontend failed → GREEN; tests/motored 1456, jest 90/668.
- [x] T12 — cédula + last 4 of celular (Python-side match over cédula-scoped rows), single generic NO_ENCONTRADA message, submit re-validates, celular required (min 7 digits) in upload, second input on survey screen. RED 6+14 backend, 25 frontend → GREEN; tests/motored 1477, asc360 1292, jest 90/671. Screenshot reviewed.
- 2026-09-29: user chose T12 option B after noting option A still lets whoever guesses a cédula submit a fake answer (and burn the real customer's single response). Celular mandatory in the upload.
