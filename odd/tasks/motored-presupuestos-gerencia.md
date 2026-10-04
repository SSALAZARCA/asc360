# Motored: sales budgets master + GERENCIA role

Engram mirror: `odd/motored-presupuestos-gerencia/tasks` (project asc360).
Exploration: Engram `sdd/motored-presupuestos-gerencia/explore` (id 468). SDD was dropped by the user (2026-10-04); this runs as ODD.

## Objective
Give Motored a monthly, versioned **sales budget per asesor**: the base for KPI compliance (cumplimiento) and commissions. Also add a new **GERENCIA** role that can load budgets and see the KPI's dashboard.

## Problem / why
- KPI's compliance and commissions need a budget per asesor per month. Today it lives only in an Excel file (sheet PRESUPUESTOS).
- The user wants budgets loaded by ADMIN or a new GERENCIA role, kept as history, and every correction audited.

## Decisions (user, 2026-10-03 / 2026-10-04)
**Budgets**
- Budget is per asesor (by cédula) per month.
- The upload has 4 columns: Cédula, Mes, Tienda, Presupuesto.
- One file may contain one or several months.
- Each month in the file replaces ONLY that month. An asesor omitted from a re-uploaded month has no budget that month.
- Every upload or manual edit creates a new **version** of that month. Old versions are kept (timestamp, user, origin), and indicators use the latest version.
- Store budget = the sum of the asesores assigned to that store in that month. The row's Tienda is the assignment.

**Access**
- Budgets are loaded, edited and viewed by **ADMIN and GERENCIA** only.
- **GERENCIA sees Presupuestos and KPI's (the tablero) only.** No other Maestros, no pedidos/corridas, no Telegram self-link, no Configuración.
- GERENCIA must be confined **server-side** with a path allow-list, like SERVICIO_CLIENTE, because many Motored reads only check authentication.
- **Usuarios → "Roles y permisos"** is a READ-ONLY matrix of role × screen. Editable permissions are a separate future project.

**Calculation (for the later KPI work, not built here)**
- Cumplimiento = venta CON HMCL ÷ presupuesto.
- Comisión = venta SIN HMCL × tramo %. The rules are configurable in Configuración (another session).

## Defaults chosen for minor open questions (user may override)
- **Mes formats accepted:** an Excel date cell, `YYYY-MM`, `MM/YYYY`. Past and future months are allowed.
- **Presupuesto:** integer pesos, must be > 0, no maximum.
- **Cédula:** cleaned with `limpiar_cedula`. Must match at least one `vendedor` row (cédula is not unique: one person can have several ERP names). An inactive vendedor is allowed, with a warning.
- **Tienda:** matched by name or alias, like the vendedores upload. An inactive sucursal is an error.
- **Repeats:** a cédula repeated in the same month of the file is an error.
- **Manual edits:** a manual edit or addition of one asesor creates a new version of that month. The note is optional.
- **Out of scope:** restoring an old version. History is view-only.
- **Display name:** for a cédula, the name of an active vendedor row with that cédula.

## Scope
**In scope**
- The GERENCIA role (enum, user admin, frontend role lists and gates, server confinement).
- KPI's/tablero access for GERENCIA.
- The budget tables (version header + lines), service, API, template, upload with dry-run summary, apply, manual edit, history, and a read API for the KPI work.
- The Maestros → Presupuestos tab, with Maestros tabs filtered by role.
- The Usuarios → Roles y permisos read-only matrix.

**Out of scope**
- KPI compliance/commission screens (KPI Etapas 1-3).
- The Configuración screen (session aplicaci-n-red-de-servicio-22).
- Editable permissions.

## Constraints
**Coordination with session -22**
- It edits `frontend/components/motored/MotoredSidebar.js` (adds an ADMIN-only Configuración item) and the `parametros` files. Keep sidebar edits minimal, and whoever pushes second rebases.
- Pedidos/corridas (`require_roles("ADMIN","COMPRAS")`), `/usuarios/me/telegram` and Configuración stay closed to GERENCIA.

**Migrations**
- Alembic Motored head on main is `b5d91e3a7c42`. Chain on the real head at write time.
- Bump the head asserts in `tests/motored/test_migration_fase4.py` and `test_migration_referencia_codigo_unico.py`.
- Follow the enum precedent `7be41d9c0a26_servicio_cliente_role.py` (autocommit `ALTER TYPE ... ADD VALUE`).

**Do not touch**
- Do not register "presupuesto" in `_SCHEMA_BY_ENTIDAD`: that exposes the generic ADMIN|COMPRAS bulk routes.
- Do not touch the "- copia" worktree or the corridas files.

**Delivery**
- Production runs Python 3.11: test the backend on 3.11 before pushing.
- Every new `<select>`/`<option>` needs an explicit option style (dark theme).
- Add tooltips on non-obvious fields.
- Make it tablet-responsive (768–1024 px).
- No backticks in CSS comments inside `themeCss`.

## TDD
- **Mode:** Strict TDD ON. Source: Engram `sdd-init/asc360`.
- **Backend:** `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/motored`.
- **pg_real:** `-m pg_real` against a throwaway PG 18.
- **Frontend:** `cd frontend && npx jest`.
- **Order:** observed RED, then GREEN, then REFACTOR.

## Delivery
- **Strategy:** ask-on-risk.
- **Commits:** a Conventional Commit per task on `feat/motored-encuesta-satisfaccion`, pushed with `git push origin HEAD:main` (Coolify deploys main). Push only after the native review when one is due.
- **Forecast:** ~1,400 authored lines over 4 tasks.

## Tasks
- [x] **T1: GERENCIA role and access.**
  - Backend:
    - enum value plus an autocommit migration;
    - `GERENCIA_ALLOWED_PREFIXES` confinement in `deps.py` (auth, presupuestos, tablero-asesores);
    - tablero-asesores router roles plus GERENCIA.
  - Frontend:
    - `VALID_ROLES`;
    - `UsuarioCreateForm` role option with an explicit style;
    - sidebar tablero item roles plus GERENCIA;
    - `useTableroGate` plus GERENCIA;
    - `homePathFor(GERENCIA)` set to the tablero until T3 lands.
  - Tests: RBAC/confinement, layout, sidebar, form.
  - Route: delegated writer (multi-file).
- [x] **T2: Budgets backend.**
  - Migration with `presupuesto_version` (mes, version, origen, archivo_nombre, nota, created_at, created_by) and `presupuesto_linea` (version_id, cedula, sucursal_id, monto).
  - Service: parse, validate, dry-run summary, apply (one new version per month in the file), manual edit/add as a new version, history, and reads (latest per mes/cédula, sum per mes/tienda).
  - Router `/presupuestos` with ADMIN+GERENCIA, plus a template endpoint.
  - Tests: unit + pg_real.
  - Route: delegated writer.
- [x] **T3: Maestros → Presupuestos tab.**
  - Month selector and budgets grouped by tienda with totals.
  - Upload modal with template download and dry-run summary, then apply.
  - Manual edit/add with an optional note.
  - Version history.
  - Maestros tabs filtered by role (GERENCIA sees only Presupuestos), and `homePathFor(GERENCIA)` moves to maestros.
  - Jest tests.
  - Route: delegated writer.
- [x] **T4: Usuarios → Roles y permisos (read-only).**
  - Matrix of role × screen from one frontend source, consistent with the gates.
  - Sidebar/route under Usuarios (ADMIN).
  - Jest tests.
  - Route: delegated writer or inline, depending on size.

## Progress / evidence
**T1, done.** Route: delegated writer (multi-file, 18 files).
- **Implementation**
  - Migration `c4e8a1f6d903_gerencia_role`, chained on `b5d91e3a7c42`.
  - `deps.py` holds a role → allowed-prefixes map `_CONFINED_ROLE_PREFIXES` for SERVICIO_CLIENTE and GERENCIA. GERENCIA is allowed `/api/motored/auth`, `/presupuestos` and `/tablero-asesores`.
  - The sidebar Maestros item uses `excludeRoles: ['GERENCIA']` instead of a roles list, so ASESOR_MOSTRADOR's view is unchanged.
  - `homePathFor('GERENCIA')` points to `/motored/tablero-asesores`.
  - Admin, pedidos and detractores gates redirect via `homePathFor`.
- **Coordination:** rebased onto -22's Configuración commit b129272. The sidebar conflict was resolved by keeping both the GERENCIA addition to mi-cuenta and the Configuración item.
- **TDD evidence**
  - RED: ImportError on `GERENCIA_ALLOWED_PREFIXES`, the head asserts, and 9 jest failures.
  - GREEN, before the rebase: pytest 4677 passed; pg_real 413 passed / 2 skipped on PG 18; jest 1522 passed.
  - After the rebase: the parent re-ran pytest (4768 passed) and the affected jest suites (8 suites, 71 passed).
  - Python: the backend venv is 3.11.16, the same as production.
- **gga notes, deferred:** stale ADMIN|COMPRAS docstrings in `tablero_asesores.py`, `test_tablero_asesores_api.py` and `motored-tablero-gate.test.jsx`.
- **Left untouched**
  - `app/motored/usuarios/page.js` has a local gate.
  - The `cargas/page.js` redirect goes to Maestros. GERENCIA is blocked server-side anyway.
- **Delivery:** commit fd37e42, pushed to main.
- **Native review:** risk medium (`slice_budget_reached`, 582 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Follow-ups from non-blocking advisories**
  - Frontend pages are not role-confined in `motored-layout.js`: GERENCIA typing another URL sees the page shell, while the API returns 403.
  - The login test does not exercise GERENCIA.
  - The password-change assert is negative-only.

**T2, done.** Route: delegated writer (multi-file backend slice).
- **Migration:** `d7a2f4b8c915_presupuestos` (down `c4e8a1f6d903`), creating `presupuesto_version` and `presupuesto_linea` with CHECKs (day=1, monto>0) and UNIQUEs.
- **Service:**
  - `services/presupuestos_archivo.py`: pure parse/validate.
  - `services/presupuestos.py`: dry-run, apply, manual edit, history and reads.
  - `services/sucursal_texto.py`: tienda resolution, moved out of `api/carga.py` and re-imported there.
- **Router** `/api/motored/presupuestos` (ADMIN+GERENCIA):
  - `GET /plantilla.xlsx`, `POST /validar`, `POST /aplicar` (422 on errors, 409 on a race);
  - `GET /meses`, `GET /meses/{yyyy-mm}`, `GET /meses/{yyyy-mm}/versiones`, `GET /versiones/{id}`;
  - `PUT` and `DELETE /meses/{yyyy-mm}/asesores/{cedula}`.
- **Decisions**
  - The immutable version header is the audit trail; `AuditoriaMaestro` is not used.
  - Each month's version number is taken under a per-month `pg_advisory_xact_lock`.
  - Removing the last asesor leaves an empty version.
  - `YYYY-MM-DD` text is also accepted for Mes.
  - Monto is BigInteger and accepts `1.500.000`.
- **TDD evidence**
  - RED: ImportErrors, head asserts, 87 API failures.
  - GREEN: pytest 4898 passed; pg_real 448 passed / 2 skipped.
  - After the rebase onto -22's 034c2b1/912cc18, the parent re-ran pytest: 4966 passed.
- **Size:** ~1,900 authored lines including tests. It is one cohesive backend slice.
- **Deferred**
  - Make `_parse_excel_upload` public.
  - The `quitar_asesor` docstring wording.
  - The KPI read helpers `presupuesto_por_asesor` and `presupuesto_por_sucursal` are tested but unused until the KPI work.

- **Delivery:** commit 5bcf940, pushed to main.
- **Native review:** risk medium (`slice_budget_reached`, 2,130 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories to fix as a small follow-up (with T3)**
  - A long `archivo_nombre` can overflow its column (`api/presupuestos.py:123`).
  - `monto` has no upper bound in the upload or the manual edit schema, so a huge value could overflow BigInteger and return a 500.
  - The IntegrityError→409 mapping is untested.

**T3, done.** Route: delegated writer, with two commits: A, the backend advisory fix, and B, the frontend tab.
- **Commit A (`fix`):**
  - `archivo_nombre` is truncated to 255 characters, keeping the extension.
  - `MONTO_MAXIMO` = 100.000.000.000 applies to both the upload and the manual edit.
  - The IntegrityError→409 mapping is now tested.
  - New `GET /presupuestos/tiendas` (ADMIN+GERENCIA) lists the active sucursales for the tienda select.
- **Commit B (`feat`):**
  - `PresupuestosTab` plus `presupuestos/` (MesPresupuesto, EditorAsesor, HistorialVersiones, CargaPresupuestosModal).
  - `presupuestosApi.js` and `maestrosTabsPorRol.js`, which filters tabs by role so GERENCIA sees only Presupuestos and makes no getSalud call.
  - The sidebar Maestros `excludeRoles` was removed, so GERENCIA sees Maestros.
  - `homePathFor(GERENCIA)` now points to `/motored/maestros`.
  - Options carry an explicit style; tables use `MotoredTableScroll`.
- **TDD evidence**
  - RED: 91 backend errors; frontend "Cannot find module"; 5 gerencia-role failures.
  - GREEN: pytest 4979 passed; pg_real `test_presupuestos_pg.py` 29 passed; jest 162 suites / 1657 tests.
  - Compile check: `/motored/maestros` returned 200 on `next dev --webpack`. Turbopack panics on the `node_modules` symlink, which is an environment issue.
- **Rebase:** onto -22's 96364cc. The parent re-ran the affected jest suites (19 suites / 216 passed) and the presupuestos/gerencia pytest (165 passed).
- **gga advisories:** the GERENCIA branch in `homePathFor` is redundant; `PresupuestosTab` has 9 state hooks, so a `usePresupuestosMes` hook would help later.

- **Delivery:** commits e4a50fb and 94425e0, pushed to main.
- **Native review:** risk medium (`slice_budget_reached`, 1,433 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories to fix with T4**
  - The month view can stay stale after Aplicar (`PresupuestosTab.js:91-94`).
  - A race on the detail fetch: switching months quickly can show the previous month's detail (`PresupuestosTab.js:54-67`).
  - The max-amount message in `EditorAsesor`.
  - A sticky error that is never cleared.

**T4, done.** Route: delegated writer, with two commits.
- **Commit A (`fix`):** the Presupuestos tab now refreshes the selected month and the months list after Aplicar. It ignores stale detail responses (latest-requested-month guard), clears a sticky error, and shows the cap message in EditorAsesor.
- **Commit B (`feat`):**
  - `lib/motored/permisosPorRol.js`: 16 screens × 6 web roles, derived from `menuItemsFor` (now exported from MotoredSidebar), the gate constants (PEDIDOS/TABLERO/CONFIGURACION/DETRACTORES_ROLES) and `filtrarTabsPorRol`/`PRESUPUESTOS_ROLES`. The backend-only Telegram rule is noted in the module.
  - `RolesPermisosMatriz` is a tab inside Usuarios (ADMIN), next to "Gestión de usuarios".
  - Drift tests cover VALID_ROLES, the sidebar and the gates.
  - ASESOR_MOSTRADOR is left out (bot-only, no web access).
- **TDD evidence**
  - RED: 4 fresh-view tests failed; the matrix suite failed on missing modules.
  - GREEN: full jest 166 suites / 1699 tests.
  - Compile check: `/motored/usuarios` returned 200 on `next dev --webpack`.
- **Rebase:** onto -22's d461d5d. The parent re-ran the affected jest suites (24 suites / 250 passed).

- **Delivery:** commits 646dbc6 and 71fdb9a, pushed to main.
- **Native review:** risk medium (`slice_budget_reached`, 526 lines). Consent granted; the R3 lens approved and the result was acknowledged.
- **Advisories, all suggestions**
  - The clear-error test is weak.
  - A successful detail fetch also clears a list error.
  - The Telegram row in `permisosPorRol.js` has no guard against drift from the backend rule.

## Status
**Feature complete.** All 4 tasks are on main. Follow-ups:
- Frontend pages are not role-confined in `motored-layout.js` (from the T1 advisory; the API already returns 403).
- The login test doesn't exercise GERENCIA.
- Stale ADMIN|COMPRAS docstrings in tablero files.
- Make `_parse_excel_upload` public.
- Extract a `usePresupuestosMes` hook.
- The T4 suggestions above.

## Next step
None for this feature. Next: the KPI's work (Etapa 1). It reads the budgets through `presupuesto_por_asesor`/`presupuesto_por_sucursal`, and the Configuración keys through `vigente_en`.
