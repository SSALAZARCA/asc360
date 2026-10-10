# Motored: download the references master as Excel

## Objective

From Maestros → Referencias, a "Descargar Excel" button downloads the reference master in the same layout as the upload template. The owner can then edit the file and re-upload it with the existing load.

## Decisions (owner, 2026-10-10)

1. The button sits next to the search box in Maestros → Referencias.
2. The columns match the upload template exactly, in the same order and with the same header text:
   - Código;
   - Código del proveedor;
   - Nombre;
   - Línea comercial;
   - Unidad de empaque;
   - Precio Normal antes de IVA;
   - Precio Público antes de IVA;
   - Código de referencia sustituta.

   A final "Estado" column (Activa/Inactiva) is added after them. Check that the existing upload ignores an extra column; if it does not, report it before changing anything.
3. The download covers the whole master, not just the current page. When a search or filter is active, it downloads only what matches.
4. Permissions are the same as viewing Maestros → Referencias today, enforced on the backend endpoint.
5. The file is named `referencias_YYYY-MM-DD.xlsx` (Bogotá date).

## Checklist

- [x] T1 backend export endpoint + tests (route: delegated writer)
  - `GET /api/motored/maestros/referencias/exportar.xlsx`, same filters (`q`, `linea_comercial`, `activa`, `proveedor_id`) and read gate (`get_current_motored_user`) as `/buscar`; one query with the proveedor and sustituta joins, no paging.
  - Evidence: `backend/tests/motored/test_referencias_excel.py` (19 tests: headers/order, filter parity with `/buscar`, roles, file name, round trip through `parse_excel_rows` + `validate_rows` + `_row_to_schema`). `pytest tests -q -k referencia`: 323 passed.
- [x] T2 frontend button + jest test (same writer)
  - `DescargarReferenciasExcel.js` in the filter row (next to the search box), busy state and error message; client `descargarReferenciasExcel` in `lib/motored/api.js`.
  - Evidence: `frontend/__tests__/motored-referencias-descarga-excel.test.jsx` (7 tests). `npx jest maestros referencias`: 83 passed.
- [x] T3 commits 0402a80 16a6ebe (gga PASSED), pushed

## Progress

- 2026-10-10: T1/T2 done. Deviation: the export includes the 9th template column "Homologados otras marcas" (the upload template has 9 columns; decision 2 lists 8 but also says "match the template exactly"). The upload ignores the extra "Estado" header (unknown headers are not mapped in `carga_excel._build_column_map`).
- 2026-10-10: decisions recorded. The writer starts after the hyphen-matching writer finishes, so there is only one writer in the worktree at a time.
