# Motored Comisiones — cleaner bonus visuals

## Objective
Replace the saturated per-line bonus detail in KPI › Comisiones with the two designs the user chose in the "Motored KPIs" canvas:
- `project/ComisionBonos.dc.html`, variant B;
- `project/BonosPorLinea.dc.html`, variant B.

## Decisions (user, 2026-10-07)
- **"Comisión por asesor" rows (ComisionBonos, B):**
  - The commission bar stays as it is today.
  - Directly under it, a thin ámbar bar (#B45309) labeled "+ $X bonos (Lubricantes, Baterías)", shown ONLY when bonuses were earned, with the total payout on the right.
  - Below the 95% gate, the row shows the small grey note "No alcanza el 95% para bonos".
  - Unmet lines and "le faltan $X" leave the main view. The per-line detail (met ✓ with amount, unmet "le faltan $X") stays reachable by expanding the asesor (tap/click), and in the Excel.
  - The chosen proposal becomes the only view; no extra modes.
- **"Bonos por línea · <mes>" card (BonosPorLinea, B mosaic):**
  - 6 tiles: line name, meta chip ("≥21% · $35.000 c/u"), amount paid in large type, one dot per winner (+N after about 12), and a thin share-of-total bar.
  - Inactive lines are muted with an "Apagado" chip and "lo habrían ganado N".
  - Header chips: "Pagado en bonos $X" and "N bonos ganados".
  - The grid uses 3 columns, 2 on tablet, 1 on phone.
- **Tablet.** 768–1024 px must work.
- **Untouched.** The asesor detail card in KPI › Asesores keeps its per-line chips; the change is limited to the Comisiones tab.

## Tasks
- [ ] **V1** The frontend for both designs (`components/motored/kpis/comisiones/*`), using the existing payload (`bonos`, `gate`, `resumen.por_linea`), plus jest tests. Backend fields only if something is missing (e.g. winners for inactive lines).

## Next step
V1 by one delegated writer; then review, push, and send the hash to 5d.
