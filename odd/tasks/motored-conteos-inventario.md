# Motored: physical inventory counts (total and selective). Definition in progress.

## Objective
A new menu module for running total store counts and scheduled selective (cyclic) counts from the app. Counting uses barcode scanners or manual entry, and leaders follow progress and critical differences live.

## Owner decisions (2026-10-08)
- **Store state:** the count happens with the store CLOSED. Several stores can be counted at the same time.
- **Snapshot:** "Iniciar conteo" on a store COPIES that store's current system inventory (the latest Maestros inventory carga) into the conteo. The copy is frozen: later Maestros uploads, for example before another store starts, never change it.
  - Starting shows which carga the snapshot came from.
  - It warns if that inventory is stale.
- **Barcodes:** the label barcode equals the referencia code (no EAN). Lookup uses the existing normalized referencia code.
- **Devices:**
  - Mostly laptops with wired USB scanners (keyboard input).
  - Phones also work, by camera, Bluetooth scanner or manual entry.
  - The counting screen works on both: desktop layout and mobile-first layout.
- **Counters:** pairs from other company areas, with NO user accounts.
  - A pair enters both members' name and cédula once per device session. This is traceability only; no user is created.
  - Each device is one pair, and every reading is stored with its pair.
- **Access for pairs:**
  - ONE link per store conteo, shown as a QR for phones and as a copyable or short link for laptops, plus a short numeric code.
  - It is valid only while the conteo is open.
  - The leader sees the connected pairs (what each counted, current location), can disconnect a pair (its readings are kept) and can rotate the code (pairs already in keep counting).
- **Location first:** before counting, the pair sets a bin location (e.g. "Estante A3"). Every reading is stored with the current location until it changes.
  - Location labels can be printed with barcodes and scanned.
  - A referencia can sit in several locations: they are summed against the system, and a reconteo lists every location.
- **Blind count:** pairs never see the expected quantity.
- **Reconteo:** a mismatched referencia goes to reconteo, ideally by a different pair. A configurable MONEY threshold limits reconteos to differences above X pesos.
- **Critical:** a difference above a larger configurable MONEY threshold shows red, at the top, live.
- **New role LÍDER DE INVENTARIOS** (with a user account):
  - schedules and starts conteos;
  - gets the QR, link and code;
  - watches the live panel;
  - requests reconteos;
  - closes the conteo;
  - downloads the ERP adjustment list.

  ADMIN can do all of this. GERENCIA sees the panel and results read-only.
- **The app never changes stock.** Closing produces an adjustment list for the ERP.
- **Accuracy KPI per store:** the % of referencias that matched, and the difference in money. It allows comparing stores and following the trend.
- **Selective counts:** the app generates a weekly short list per store, prioritizing high-rotation or high-value referencias (ABC). Details are still to be defined.

## Planned stages
1. Total count (scanner and manual, blind, locations, pairs, reconteo, close).
2. Live panel (progress, critical differences, alerts, pairs).
3. Automatic selective counts (weekly scheduling).
4. ERP adjustment list and accuracy history.

## Open questions
- RESOLVED 2026-10-08: differences are valued at the inventory file's "Costo prom. uni." per referencia and bodega, frozen in the snapshot. Thresholds and selective rules live in Configuración, new tab "Conteos de inventario".
- RESOLVED 2026-10-08 selective counts:
  - **ABC by sales money per store.** Thresholds (default 80/15/5) and frequencies (default A monthly, B quarterly, C semiannual) are configurable.
  - **Always included:** referencias with a difference in the last count, negative system stock, and selling with zero stock.
  - **Weekly list per store,** size configurable (default 40), auto-generated.
  - **Counted by the store's asesores (Lore users)** in a Telegram Mini App opened from a Lore message button. Telegram identifies the asesor; a shared Telegram asks for the cédula. It can be resumed, and differences go to the leader panel.
  - **Counted at store opening, store OPEN,** against that morning's inventory. A selective difference is confirmed only if it repeats in a next-day reconteo.
- RESOLVED 2026-10-08: a total-count reconteo MUST be done by a different pair; the first pair never sees it. With only one pair in the store, the leader can authorize that same pair.
- RESOLVED 2026-10-08: no ERP import template yet. Closing generates a downloadable Excel (referencia, bodega, system qty, counted qty, difference, unit cost, difference value, locations). The owner will send the ERP format later if it must change.
- 2026-10-08: the owner approved the screen prototypes (artifact https://claude.ai/artifact/Eq1mconFxKgnLzhkENW89G): leader panel, start count, laptop count, pair join, phone count, Telegram mini app. Technical design: odd/design/motored-conteos-inventario.md.
- 2026-10-08 owner decision: counts are per STORE (sucursal), not per bodega.
  - The snapshot sums all of the store's own bodegas (principal + secondary), and readings and locations carry no bodega.
  - The ERP adjustment Excel assigns each referencia's whole difference to that SAME store's principal bodega.
  - Associated stores (`principal_id`) are not merged into a count.
  - This supersedes the design's per-bodega location tagging (open question 2).
- 2026-10-08: default thresholds are reconteo above $100.000 and critical above $500.000, both editable in Configuración.
