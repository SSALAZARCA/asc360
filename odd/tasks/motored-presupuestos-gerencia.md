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
- [ ] **T2: Budgets backend.**
  - Migration with `presupuesto_version` (mes, version, origen, archivo_nombre, nota, created_at, created_by) and `presupuesto_linea` (version_id, cedula, sucursal_id, monto).
  - Service: parse, validate, dry-run summary, apply (one new version per month in the file), manual edit/add as a new version, history, and reads (latest per mes/cédula, sum per mes/tienda).
  - Router `/presupuestos` with ADMIN+GERENCIA, plus a template endpoint.
  - Tests: unit + pg_real.
  - Route: delegated writer.
- [ ] **T3: Maestros → Presupuestos tab.**
  - Month selector and budgets grouped by tienda with totals.
  - Upload modal with template download and dry-run summary, then apply.
  - Manual edit/add with an optional note.
  - Version history.
  - Maestros tabs filtered by role (GERENCIA sees only Presupuestos), and `homePathFor(GERENCIA)` moves to maestros.
  - Jest tests.
  - Route: delegated writer.
- [ ] **T4: Usuarios → Roles y permisos (read-only).**
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

## Next step
T2 (budgets backend).
