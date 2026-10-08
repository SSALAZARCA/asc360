# Motored — pending invoice ingresos (asesor card + Gestión repuestos panel)

## Objective
Track HMCL invoices (FACTURAS_PEDIDOS) not yet ingresadas (INGRESOS_FACTURAS):
- each asesor confirms "Llegó" / "No ha llegado" from their report;
- ADMIN/COMPRAS/GERENCIA/COORDINADOR_REPUESTOS follow up in a panel.

## Decisions (user, 2026-10-08)
- **Who confirms.** Any asesor of the store can confirm. There is one shared state per invoice and store, with full history (who, when), and it can be corrected.
- **Rule.** An invoice is pending when its date is ≥ the earliest loaded ingreso date (the "Verificable desde" date), its carga is not ANULADO, and it has no live ingreso for the same `(prefijo_rh, numero_rh)`. Every pending invoice shows the buttons, including ones younger than 2 days.
- **Closing.** A real ingreso removes the invoice from the asesor list automatically. The panel shows it as closed.
- **Data** (checked against the samples with the pedidos session):
  - invoices are single-store;
  - ingresos accumulate (upsert);
  - NRH credit notes reduce quantities;
  - multi-date docs take the min date;
  - ingresos marked Anulado are ignored.
- **Asesor card.** A compact card the size of "Comisión estimada", integrated in the asesor view and in the public link. The design is being reworked: canvas board `PendientesAsesor.dc.html`.
- **Panel APPROVED** (canvas board `IngresosFacturasPanel.dc.html`):
  - KPIs: pendientes, llegaron sin ingresar (ámbar), sin confirmar, aún no llegan, más antigua;
  - a por-tienda table;
  - a detalle table with filters and per-invoice history.
- **Split** (agreed with the pedidos session, 00):
  - 00 builds the COORDINADOR_REPUESTOS role (migration plus deps), the "Gestión repuestos" sidebar group and route `/motored/gestion-repuestos/ingresos-facturas`, and fills `ingreso_factura.sucursal_id` from C.O.
  - This session builds the cross service, the confirmation tables, the endpoints, the asesor card and the panel content.

## Tasks
- [ ] **P1 Backend.**
  - The pending cross service, reusing the `transito_corte` logic: per invoice and principal store, with units, value, date, days.
  - Tables `factura_confirmacion_ingreso` (state) and `factura_confirmacion_ingreso_historial`; migration chained with 00.
  - Endpoints:
    - panel reads (summary, por tienda, detalle, historial);
    - authenticated asesor confirm;
    - public confirm `POST /publico/informe/{token}/pendientes/{factura}` (token+cédula, same lock rules);
    - add the pending list to the asesor detail payload.
  - Tests: pure, API, pg_real.
- [ ] **P2 Panel frontend** (approved design) + jest.
- [ ] **P3 Asesor card** (after the compact design is approved) in `AsesorDetalle` + public page + jest.

## Next step
P1 + P2 now; P3 after design approval.
