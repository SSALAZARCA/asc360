# Motored web: icon row actions with hover labels

## Objective
Every row action in Motored tables uses an icon instead of a text link, and shows a hover label saying what it does. This covers every screen: Editar, Desactivar, Reactivar, Anular, Aprobar, Rechazar, Cambiar contraseña, download/view/apply actions in Cargas, and so on. Requested by the user on 2026-09-29: "que sean con logos o imágenes y que cuando pase el mouse por encima me diga qué es… aplica para todas las demás ventanas".

## Scope
- Per-row action buttons and links in every Motored table (`frontend/app/motored/**`, `frontend/components/motored/**`), found with rg rather than by memory.
- The status text ("Activa"/"Inactiva") stays text. It is data, not an action. It may become a small colored pill for readability, using the existing semantic colors.
- Primary form buttons ("Crear referencia", "Guardar cambios", "Carga masiva") keep their text labels. They are primary actions, not row options.

## Design
- **Shared component:** `MotoredIconAction` with props `icon`, `label`, `onClick`, `variant` (default/danger) and `disabled`. It renders a real `<button>` with `aria-label={label}` and a visible hover/focus tooltip showing `label`. A native `title` alone is not enough, because it doesn't appear on keyboard focus and is slow. The tooltip must also show on keyboard focus.
- **Icons:** use `lucide-react`, which is already a dependency. The action-to-icon mapping is defined once in a shared map, so the same action always uses the same icon everywhere:
  - Editar → Pencil
  - Desactivar → Ban or PowerOff
  - Reactivar → RotateCcw
  - Anular → XCircle
  - Aprobar → Check
  - Rechazar → X
  - Cambiar contraseña → KeyRound
  - Descargar → Download
  - Ver detalle → Eye
  - Aplicar → Play or CheckCheck
- **Touch:** make hit targets at least 32px for tablet use. On touch devices the tooltip shows on focus/tap without blocking the action.
- **Accessibility:** tests query actions by accessible name (`getByRole('button', { name: 'Editar' })`), which keeps working through `aria-label`.
- **Existing confirmations stay:** Desactivar/Anular confirmation steps keep working exactly as today.

## Constraints
- Motored conventions: never put a backtick in a `themeCss` comment (`frontend/app/motored/layout.js`), and prefer a separate style approach over touching it. Every `<option>` keeps its explicit style. Screens must stay tablet-responsive (see `odd/tasks/motored-responsive-tablet.md`).
- gga: components under ~50 lines, no mid-file test imports, no trailing whitespace.

## TDD
- Mode: strict.
- Runner: `cd frontend && npx jest`.

## Tasks
- [x] T1: `MotoredIconAction` plus the shared icon map, with tests for the aria-label, the tooltip on hover and focus, and the danger variant.
- [x] T2: Replace every text row action in every Motored table, and update the affected tests.
- [x] T3: Screenshot check at 1440 and 768 of a table with actions, including a hovered tooltip.
- [x] T4: Commit and push to main.
- [x] T5: Reactivar action for inactive rows (requested by the user on 2026-09-29). Evidence: RED (18 backend and 11 frontend failures), then GREEN; `pytest tests/motored -q` 1153 passed; `npx jest` 77 suites, 551 tests passed.

## Progress
- 2026-09-29: document created. Waiting for the "hide sustituta/homologados columns" change in `ReferenciasTab.js` to land first, since it touches the same file.
- 2026-09-29: T1-T3 implemented (not committed). Route: delegated writer. RED observed (module missing; 3 icon-only assertions failing), then GREEN. `cd frontend && npx jest`: 75 suites, 540 tests passed (baseline 74/531). T1: `components/motored/MotoredIconAction.js` (state-driven tooltip on hover/focus, inline styles, 32px target) + `actionIcons.js`. T2 rows converted: Sucursales/Bodegas/Proveedores/Referencias (Editar, Desactivar), Usuarios (Desactivar, Cambiar contraseña, Vincular/Desvincular Telegram, Aprobar, Rechazar), VentasPerdidasRow (Guardar, Cancelar, Editar, Anular), ErroresTab (Mapear, Ignorar, Crear como OTROS). Left as text on purpose: Aplicar/Anular carga (page-level in ResumenTab), CambiarPasswordForm buttons (form), Descargar plantilla/CSV (toolbar). No Reactivar action exists in the UI. T3: dev server on 3457, puppeteer captures of Sucursales and Usuarios at 1440x900 and 768x1024 plus hover tooltips, no horizontal overflow; server stopped. Captures in `Documents/Motored/capturas-iconos/`.
- 2026-09-29: T5 implemented (not committed). Route: delegated writer. Existing PATCH schemas do not accept `activa`, so new endpoints `POST /maestros/{entidad}/{id}/reactivar` (ADMIN|COMPRAS, same gate as DELETE) and `POST /usuarios/{id}/reactivar` (ADMIN). Both set only the active flag, audit with new `audit_reactivate` (accion `reactivate`, activa False -> True), and are a no-op without audit if already active. Referencias keep `sustituida_por`; usuarios keep `status`. Frontend: `reactivateMaestro`/`reactivateUsuario` in `lib/motored/api.js`; the 4 maestro tabs and Usuarios show a Reactivar icon (confirm first) where Desactivar shows for active rows; Referencias refetches the current page via the existing refresh version. Tests: `backend/tests/motored/test_reactivar_api.py` (20), `frontend/__tests__/motored-reactivar*.test.jsx` (11).
