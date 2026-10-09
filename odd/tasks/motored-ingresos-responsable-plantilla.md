# Motored — who enters each pending invoice, and the ERP entry template

Locator: `odd/tasks/motored-ingresos-responsable-plantilla.md` · Engram topic `odd/motored-ingresos-responsable-plantilla/tasks`

## Objective
Split pending supplier invoices (Gestión repuestos → Ingresos facturas) by who must enter them into the ERP:
- **≤ N references (default 10, configurable, inclusive):** the store's parts advisor enters it manually. Once the invoice is confirmed "Llegó", the advisor's KPI card and the public daily-report link show a "enter it into the system" notice that persists every day until the invoice appears in the loaded ingresos.
- **> N references:** a new role **ANALISTA_ADMINISTRATIVO** enters it. In the panel Detalle, each invoice shows who enters it; for analyst invoices confirmed "Llegó", a "Descargar plantilla" button downloads the ERP "Entradas x Compra" Excel.

## Decisions (user, 2026-10-09)
- Threshold inclusive: exactly 10 references → advisor.
- Template = `Plantilla Entradas x Compra - Dctos (1) 4.xlsx` (sheet "Entrada Compra"). Header: Centro de Operación = store `codigo_co`, "B", date = download day (Bogotá), "AAAAMMDD", MODO 2; Tipo Documento 16; Descuento Global 5; Proveedor 900723988; Suc. Proveedor "001"; Comprador 1151943311; Descuento x Item 0; Notas "ENTRADA POR COMPRA RH<n>"; Doc. Referencia "RH<n>". Lines: consecutivo 1, referencia code, bodega = store `bodega_principal`, Precio Unit = invoice "Vlr. Unitario", Cantidad, `=D*E`, `=+F*$D$4%`, "Mvto k", C.O. (first `=+B1`, rest store code), U.N. "003".
- Fixed values stay as in the template but are configurable in Configuración; discounts left as-is (people edit the Excel if needed).
- Download button only after the invoice is confirmed LLEGO.
- Analyst has full Gestión repuestos access and can confirm Llegó / No ha llegado.
- Invoices loaded before the unit price is stored: fallback price = valor_total / cantidad (daily loads make this short-lived).
- Invoice file has no warehouse column → warehouse comes from the store's `bodega_principal`; missing → clear error, no incomplete file.

## Tasks
- [x] T1 Backend (5d724fe): store invoice unit price; configurable threshold + template fixed values; ANALISTA_ADMINISTRATIVO role with Gestión repuestos access + confirm.
- [x] T2 Backend (b38df41): reference count + responsible on pending data (panel + advisor + public link); template download endpoint.
- [ ] T3 Frontend: Detalle "Ingresa" column + download button; advisor card / public link notice; Configuración fields; role selectable in user admin.

## Route
Delegated direct (2+ non-trivial files per task, one writer per task).

## Progress / evidence
- Base: main `a5f1caa`, migration head `d58b2c9e4a17`.
- T1 `5d724fe`: migrations `e3a7c1d94b52` (`factura_proveedor_linea.valor_unitario`, optional source column "Vlr. Unitario", NC keeps it positive, a load without it keeps the stored price) and `f6b2d8a35c71` (enum `ANALISTA_ADMINISTRATIVO`, head). Parameters tab `ingresos` with 8 keys (`ingreso_umbral_referencias_asesor`, `ingreso_plantilla_*`; new type `texto` for "001"/"003"). Role allow-list: auth + gestion-repuestos only (no KPI endpoints: `tablero_kpis.py` was outside the allowed surface).
- T2 `b38df41`: pending items carry `num_referencias`, `responsable`, `puede_descargar_plantilla`; `GET /gestion-repuestos/ingresos-facturas/plantilla?factura=RH208629&sucursal=<uuid>` (ADMIN + ANALISTA_ADMINISTRATIVO). Reference count = distinct references with positive net quantity per principal store (the template lines); fully credited lines are left out.
- Checks: motored unit 6965 passed; pg_real (role, conteo migrations, pendientes, plantilla) 6+4+ passed on a throwaway Postgres 18 migrated to head; single alembic head `f6b2d8a35c71`; compileall on Python 3.11.16 venv.
