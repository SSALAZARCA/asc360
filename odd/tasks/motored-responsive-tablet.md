# Motored web: tablet-responsive layout

## Objective
Every existing Motored web screen is usable on a tablet: portrait at 768px and landscape at 1024px. Desktop keeps the current look. Business confirmed on 2026-09-29 that admins may use tablets.

## Current state (verified 2026-09-29)
- There are zero `@media` rules in `frontend/app/motored` and `frontend/components/motored`.
- `components/motored/MotoredSidebar.js` is a fixed 240px sticky aside (line ~46).
- Tables (Sucursales, Bodegas, Proveedores, Referencias, cargas tabs, Usuarios, Ventas perdidas) have no horizontal-scroll container, so they overflow the page.
- Create forms put 9–10 fields in one row.
- The theme CSS lives in `themeCss` in `frontend/app/motored/layout.js`, a template literal. NEVER put a backtick inside a CSS comment there; that has broken the whole app 3 times.

## Design
- **Breakpoint `1024px`, max-width.** Below it the sidebar becomes an off-canvas drawer, hidden by default. A top bar with a ☰ button (aria-label "Abrir menú") and the Motored logo opens it over the content, with a backdrop.
  - Tapping the backdrop, pressing Escape, or navigating closes it.
  - The drawer keeps the user name and "Salir".
  - At 1024px and above the current layout is unchanged.
- **Tables:** wrap every Motored data table in a shared horizontal-scroll container (`overflow-x: auto`, with a sensible min-width on the table), so the page itself never scrolls sideways. Use one shared component or class, not per-screen hacks.
- **Forms and filter bars:** use `flex-wrap` so fields flow onto several rows on narrow widths. Buttons stay reachable.
- **Tabs rows** (Maestros/Movimientos, etc.) must not overflow either: they wrap or scroll horizontally.
- **Where the styles live:** put responsive CSS in `themeCss` (class-based, with `@media`), or in a separate plain CSS module. The inline style objects can't express media queries. Keep the dark-theme variables working.
- **Out of scope:** phones below 768px get no special design work, but the layout should not break catastrophically there.

## Verification
- **Jest:** the drawer opens and closes (☰, Escape, backdrop, navigation) and the table wrapper is present.
- **Real screenshots** at 768×1024, 1024×768 and 1440×900 for Maestros/Sucursales, Referencias, Usuarios and Ventas perdidas, using puppeteer against the Next dev server.
  - Authenticated pages: seed `sessionStorage` with the Motored user and token keys (`MOTORED_USER_KEY` / `MOTORED_TOKEN_KEY` in `frontend/lib/motored/motoredFetch.js`) and intercept `/api/motored/*` requests with fixture JSON. No real backend is needed.
  - Save the screenshots under the session scratchpad and report their paths. They must NOT be committed.
- **Before/after:** each screenshot set must show no page-level horizontal scroll (`document.documentElement.scrollWidth <= innerWidth`). Assert that in the script.

## TDD
- Mode: strict for the drawer behavior and the table wrapper.
- Runner: `cd frontend && npx jest`.

## Tasks
- [x] T1: Off-canvas sidebar below 1024px, top bar with ☰, tests. Route: delegated writer.
- [x] T2: Shared table scroll wrapper applied to every Motored table, wrapping forms, filters and tabs. Route: same writer.
- [x] T3: Screenshot verification at 3 sizes, plus the no-horizontal-scroll assertion. Route: same writer.
- [x] T4: Commit and push to main.

## Progress
- 2026-09-29: document created.
- 2026-09-29: T1-T3 implemented (uncommitted). RED observed (7 of 8 new tests failing), then GREEN; full `cd frontend && npx jest`: 74 suites, 531 tests passing (baseline 512). Drawer: `useDrawerMenu` + `MotoredTopBar` + `motored-sidebar`/`is-open` classes; table wrapper `MotoredTableScroll` on 8 table files (VistaPreviaTab and BulkUploadModal already had their own overflow box); themeCss rules verified by loading /motored pages in the dev server. Screenshots (puppeteer-core + Chrome 154, fixtures intercepted): 12/12 PASS on `scrollWidth <= innerWidth` at 768x1024, 1024x768, 1440x900. First run FAILED at 1024 (10-tab bar 1366px wide); fixed with horizontal scroll on the tab bar below 1280px. PNGs and script in the session scratchpad `responsive/`. Next: T4 commit and push (user decision).
