# Motored movement uploads: templates and data-safety fixes

## Objective
Fix the problems found in the 2026-09-29 read-only audit of the 6 movement upload types (VENTAS, INVENTARIO, BACKORDER, FACTURAS_PEDIDOS, INGRESOS_FACTURAS, DEMANDA_PERDIDA). This mirrors what was done for Referencias in `c8e2aed` and `9422c8f`.

## Business decisions (user, 2026-09-29)
- **CHANGE (2026-09-29, supersedes the three bullets below for quantity/value cells):** for ALL 6 movement types, a BLANK or Excel-error (`#N/A`, `#NAME?`, `#VALUE!`, `#REF!`, `#DIV/0!`, `#NUM!`, `#NULL!`) quantity/value cell (INVENTARIO `Existencia`, VENTAS, FACTURAS_PEDIDOS and INGRESOS_FACTURAS quantity/value, BACKORDER pending quantity, DEMANDA_PERDIDA `cantidad_solicitada`) makes the row a ROW ERROR: it is NOT loaded, the other valid rows still load, and `carga_error` gets a Spanish message with the column and the offending value. A real 0 stays valid. BACKORDER lines with pending quantity 0 stay excluded as "not pending". This replaces "INVENTARIO blank = 0" and the old silent drop for BACKORDER/DEMANDA_PERDIDA blank quantities.
- **Visibility (2026-09-29):** both the informe previo and the carga after Aplicar must state how many rows were NOT loaded because of errors ("N filas con errores no se cargaron. Revisá el detalle en Errores o descargá errores.csv").
- (Superseded by the CHANGE above, kept for history:)
- **INVENTARIO:** a blank `Existencia` or an Excel error value (`#N/A`, `#NAME?`, `#VALUE!`…) means 0 stock and is written as 0. A 0 stays 0. This is not a row error.
- **VENTAS, FACTURAS_PEDIDOS, INGRESOS_FACTURAS:** a blank or error-valued quantity or value cell becomes a ROW ERROR in `carga_error`, visible in the informe previo. It is never a silent 0. The user proposed this and did not object.
- **BACKORDER and DEMANDA_PERDIDA:** keep dropping blank-quantity rows, which is already safe. A BACKORDER row without a `Número del pedido` becomes a row error.

## Audit findings (file:line under `backend/app/motored/services/ingesta/` unless noted)
1. **Template.** It is a header-only CSV built in the frontend (`frontend/components/motored/cargas/UploadMovimientoModal.js:26-35`, columns from `tiposCarga.js`), but upload accepts only `.xlsx` (`UploadMovimientoModal.js:178`, `lector.py:59`). Accents may also garble in Excel.
2. **Blank numeric cells become 0 and overwrite existing data:**
   - VENTAS: `ventas.py:172`, upsert `:328`
   - INVENTARIO: `inventario.py:106`
   - FACTURAS: `facturas.py:137`
   - INGRESOS: `ingresos.py:129`
3. **Whole workbook.** Only `wb.active` is read (`lector.py:59`, `deteccion.py:144`). The real workbook's active sheet is "Lista HMCL", so uploading the whole workbook fails.
4. **Duplicate headers.** They are silently ignored: the first match wins (`columnas.py:70-74`).
5. **No contract test** ties `tiposCarga.js` columns to the backend `COLUMNAS_ESPERADAS`. BACKORDER's frontend `Fecha Creación` is optional in the backend, and that is intentional.
6. **Numbers stored as text.** `Decimal(str(x))` reads `"1.234"` as 1.234 without error, and accepts `NaN`/`Infinity`.
7. **BACKORDER null order number.** A blank `Número del pedido` becomes a NULL unique-key part (`backorder.py:245`), which risks duplicates on re-upload.
8. **Zero valid rows.** A load with zero valid rows succeeds silently. The real `Ventas perdidas` sheet has 709 `#NAME?` rows.
9. **Minor.** FACTURAS and INGRESOS reject Excel serial dates while VENTAS accepts them. Partial-header files fail late, in the job, instead of at upload.

## Design
- **Template.** A server-generated `.xlsx` per movement type (a new endpoint, following the Referencias plantilla pattern in `backend/app/motored/api/maestros.py` / `carga_excel.py`). Headers come from the backend's own column definition, so it is a single source of truth. The frontend downloads it instead of building a CSV. Round-trip test: download, parse, header accepted.
- **Sheet selection.** Scan every sheet, not just `.active`, and pick the first one whose header row matches the declared type (≥60% rule). If none matches, keep the current error. If several match, take the first and log which one was used. Apply the same rule in type verification (`deteccion.py`) and reading (`lector.py`).
- **Numeric parsing.** Use one shared helper for quantity and value cells:
  - blank or None, or an Excel error string (`#N/A`, `#NAME?`, `#VALUE!`, `#REF!`, `#DIV/0!`, `#NUM!`, `#NULL!`): report it as "missing";
  - a text number with a thousands separator or a decimal comma: parse it deterministically (Colombian format: `.` for thousands, `,` for decimals, when the text is not a plain float), or reject it as ambiguous;
  - `NaN` or `Infinity`: reject.
  
  Each type then decides what "missing" means: INVENTARIO turns it into 0; VENTAS, FACTURAS and INGRESOS turn it into a row error; BACKORDER and DEMANDA_PERDIDA keep dropping the row.
- **Duplicate headers.** Detect them in `construir_mapa_columnas` and turn them into a whole-file error with a clear message.
- **BACKORDER without an order number.** A missing `Número del pedido` becomes a row error.
- **Zero valid rows.** When a load ends with zero valid rows, the informe previo shows a clear warning and Aplicar stays disabled, or the load ends `CON_ERRORES` if that already exists for this case.
- **Contract test.** A frontend test asserts `tiposCarga.js` columns equal a JSON fixture exported from the backend `COLUMNAS_ESPERADAS`, or the frontend stops hardcoding columns and fetches them from the server. Prefer the second if it is simple.
- **Out of scope for now.** FACTURAS/INGRESOS serial dates, and early failure for partial headers. Track them in pending.

## TDD
- Mode: strict.
- Backend: `backend/.venv/bin/python -m pytest tests/motored -q` (run from `backend/`).
- Frontend: `cd frontend && npx jest`.

## Tasks
- [x] T1: Shared numeric-cell parser plus the per-type missing policy (INVENTARIO→0, VENTAS/FACTURAS/INGRESOS→row error), and a BACKORDER missing-order row error.
- [x] T2: Multi-sheet selection in detection and reading.
- [x] T3: Duplicate-header error, and the zero-valid-rows warning or block.
- [x] T4: Server-generated `.xlsx` templates per movement type, frontend download switch, round-trip and contract tests.
- [x] T5: Commit and push to main.

## Progress
- 2026-09-29: document created from the read-only audit.
- 2026-09-29 (implementation, uncommitted, one commit per task pending): T1-T4 done with strict TDD (RED observed before GREEN for each).
  - T1: new `services/ingesta/numeros.py` (shared parser + `VALOR_FALTANTE` row error); all 6 transforms use it (ventas, inventario, facturas x2, ingresos, backorder, demanda_perdida); BACKORDER `PEDIDO_FALTANTE`; DEMANDA_PERDIDA `CANTIDAD_SOLICITADA_INVALIDA`. Tests: `test_ingesta_numeros.py` + updated per-type tests.
  - T2: `lector.elegir_hoja` (best header ratio >= 60%, ties -> first, logged; none -> active sheet) used by `lector.leer_lotes`, `deteccion.extraer_filas_muestra`, orquestador and `POST /cargas`. Deviation from design: BEST ratio instead of first >= 60%, because the real VENTAS sheet has 3/4 of INVENTARIO's columns and precedes it. Tests: `test_ingesta_hojas.py`.
  - T3: `columnas.EncabezadoDuplicadoError` -> whole-file error `E-CARGA-048`; zero valid rows -> `CON_ERRORES` plus whole-file error `E-CARGA-049`; `log.filas_con_error` + `FilasNoCargadasAviso` in `ResumenTab` (informe previo and after Aplicar).
  - T4: `GET /api/motored/cargas/{tipo}/plantilla.xlsx` (`plantillas.py`), frontend `descargarPlantillaMovimiento`; `columnas` removed from `tiposCarga.js` (backend is the single source; contract test = `test_ingesta_plantillas_api.py` round-trip + match against orquestador column maps).
  - Structure check against the real workbook (types and headers only, no data): every type resolves to its own sheet; header rows, names and cell types (datetime, int, float, str) match the parser.
  - Verification: backend `pytest tests/motored -q` 1281 passed; frontend `npx jest` 565 passed (79 suites).
  - Pending (not fixed): FACTURAS/INGRESOS serial dates; early failure for partial headers; rows with unresolved sucursal/referencia are counted in `filas_con_error` but not in `filas_rechazadas`.
