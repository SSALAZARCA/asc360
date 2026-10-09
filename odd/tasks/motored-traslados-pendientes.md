# Motored — pending transfers between stores (traslados)

Locator: `odd/tasks/motored-traslados-pendientes.md` · Engram topic `odd/motored-traslados-pendientes/tasks`
Design (approved 2026-10-09): Artifact https://claude.ai/artifact/WXrhmmeVMircjCyRRPYEXN, boards "Propuesta · Traslados por recibir (asesor)" (`project/TrasladosAsesor.dc.html`) and "Propuesta · Gestión repuestos — Traslados" (`project/TrasladosPanel.dc.html`).

## Objective
Same dynamic as pending invoices (`odd/tasks/motored-ingresos-pendientes.md`), for transfers between stores: the RECEIVING store certifies "Recibido" / "No ha llegado" so that the ERP reception is also done. A transfer marked Recibido that is still alive in the ERP shows "Recíbelo en el ERP" every day until it leaves the file.

## Source file
`Traslados_09.xlsx` (sheet1), one row per transfer line: `Nro documento` (e.g. 79-00000067), `Fecha`, `Bod. salida`, `Desc. bod. salida`, `Bod. entrada`, `Desc. bod. entrada`, `Referencia` (padded with spaces), `Desc. item`, `Item resumen`, `U.M.`, `Cant. Saldo`. Sample: 143 lines, 85 documents, 2026-08-03..2026-10-09; text fields padded with trailing spaces.
- The file lists ONLY transfers still alive in the ERP (user confirmed). Each load is a full snapshot: pending = present in the latest non-annulled TRASLADOS load; gone from it = received in the ERP.
- `Nro documento` repeats across origin stores (16 docs in the sample have several origin/destination pairs): a transfer is identified by (`Nro documento`, `Bod. salida`).
- Bodega codes resolve to stores through the Maestros bodegas (`bodega.codigo` → `sucursal_id`, principal rollup like other features).

## Decisions (user, 2026-10-09)
- Upload in Maestros → Cargas as a new load type.
- Asesor card "Traslados por recibir · tu tienda" sits NEXT TO "Pedidos por ingresar" in KPI's (Asesores) and in the public link (stacked on phone).
- No Excel/template generation (unlike invoices).
- Who certifies: same as invoices — store asesores via link and KPI card; in app ADMIN, COORDINADOR_REPUESTOS, ANALISTA_ADMINISTRATIVO; COMPRAS and GERENCIA read-only.

## Tasks
- [x] T1 Backend data: TRASLADOS load type (ingestion, validation, unknown bodegas/referencias handling, snapshot semantics), models + migration for transfer lines and confirmations (+ history).
- [x] T2 Backend service + API: pending transfers (cards, por tienda, detalle with lines, historial), confirm, asesor endpoint, public link endpoint.
- [x] T3 Frontend: Maestros upload type; Gestión repuestos → Traslados panel; asesor card next to the invoice card (KPI's + public link).

## Route
Delegated direct.

## Progress / evidence
- Base: main `84f4c79`.
- T1: type `TRASLADOS` registered like the other movement loads (`orquestador.TIPOS_MOVIMIENTO`, `deteccion` signature/label "Traslados"/optional columns, handler, apply); `carga_archivo.tipo` is a varchar so no enum migration. Migration `b2f6d9a4c718` (head): `traslado_linea`, `traslado_confirmacion` (unique `nro_documento, bodega_salida`), `traslado_confirmacion_historial`. Snapshot convention: each applied load keeps its own rows; the current snapshot is the latest APLICADO non-ANULADO TRASLADOS carga (annulling it falls back to the previous one). Unknown destination bodega = row error `SUCURSAL_NO_ENCONTRADA`; unknown origin or reference are kept. The real sample loads end to end (143 lines, 103 transfers).
- T2: `services/traslados_pendientes.py`, routes under `/gestion-repuestos/traslados` (nested in `api/gestion_repuestos.py`), public `POST /publico/informe/{token}/traslados` and `/traslados/confirmar`.
- Commits: T1 `31e60f6`, T2 `e203c94`. Checks: motored unit 7521 passed (without MOTORED_DATABASE_URL set); pg_real 11 passed on Postgres 18 (incl. real sample file); one alembic head `b2f6d9a4c718`.
- T3: Maestros type `TRASLADOS` (`tiposCarga.js` with `ayuda`, own Maestros tab); Gestión repuestos -> Traslados (`/motored/gestion-repuestos/traslados`, sidebar + `permisosPorRol`; `Traslados*` components reuse `FiltrosIngresos`, `ingresosDerivados.filtrarItems/tiendasDe`, semáforo and styles of the invoices panel); asesor card `PendientesTraslados` next to `PendientesIngreso` in `PendientesAsesor` (two-column auto-fit grid, stacks below ~900px; staff view and public link `POST /publico/informe/{token}/traslados[/confirmar]` with the cédula). Commits: `7ee5964` (cargas), `63a782f` (panel), `2648faa` (asesor card). Checks: full jest 231 suites / 2670 tests green; `next dev --webpack` compiles `/motored/gestion-repuestos/traslados`, `/motored/tablero-asesores`, `/motored/maestros` (200). Not done: visual check in a browser against the boards (tablet/phone) and the real end-to-end flow with the backend.
