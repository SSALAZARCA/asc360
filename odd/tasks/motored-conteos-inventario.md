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
- What money value prices the differences (cost or sale price, and from which source).
- The selective count rules (frequency, list size, ABC criteria).
- Reconteo by a different pair: required or only suggested.
- The ERP adjustment file format.
