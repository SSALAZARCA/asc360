# Motored: daily individual report to each asesor through Lore

## Objective
Every day, once the VENTAS carga that includes the previous day is applied, Lore sends each asesor their own month-to-date report as a PDF protected with their cédula.

## Owner decisions (2026-10-07)
- **Cédula capture:**
  - Lore asks for the cédula at registration.
  - The admin can set or correct it in Gestión de usuarios for asesores already registered.
  - It must match an active vendedor in the master, and be unique per usuario.
- **Identity chain:** Telegram → usuario → cédula → report.
- **Format:** the report is ALWAYS a PDF protected with the asesor's cédula as password. This holds for shared and personal Telegram accounts alike. Shared Telegram accounts are allowed for that reason.
- **Trigger:**
  - Automatic and daily, after the VENTAS carga covering yesterday is applied.
  - One send per asesor per day; a reload does not resend.
  - The kill switch lives in Configuración.
- **Content:** the same figures as KPI's, month to date:
  - ventas;
  - presupuesto;
  - % cumplimiento;
  - what's missing to reach 95% and 100%;
  - estimated commission by tramo;
  - per-line bonuses, earned and missing amounts.
  
  No comparison with other asesores.
- **Skipped asesores:** those without a cédula or a linked Telegram are skipped and listed for the admin.

## Tasks
| ID | Task | Owner |
|---|---|---|
| T1 | `usuario.cedula` (migration, coordinated with 84 first), validation against the vendedor master plus uniqueness, field in Gestión de usuarios, Lore `/start` asks for the cédula | this session |
| T2 | Per-asesor report builder: compute the board and commissions once per day, then slice per cédula, with no peer comparisons | 84 (KPI owner); this session consumes it |
| T3 | PDF rendering plus password (new dependency `pypdf`), `sendDocument` with throttle and 429 retry, ledger `reporte_asesor_enviado(cedula, fecha)`, daily supervisor loop, kill switch, admin list of skipped asesores | this session |

- [x] T1 (53c1ef5 backend + migration c6d2f8a41b97, b45666b Lore, 6149f47 UI; backend 6226 passed, pg_real 735 passed, lore 429 passed, jest 2247 passed)
- [x] T2 (84, 47cbcd3)
- [ ] T3

## Risks to verify with 84 and 5d
- **Privacy (Ley 1581).** The cédula is a weak password (owner accepted for now).
- Cost of computing the report for N asesores.
- The trigger condition ("the carga covers yesterday").
- Behaviour when a month is reloaded.
- Telegram rate limits.
- Asesores who blocked the bot (403).

## Audit (5d, 2026-10-07): accepted changes
- **H1:**
  - A cédula entered by the asesor in Lore stays PENDING until an ADMIN approves the link, through the existing Pendiente/Aprobado flow.
  - No report goes out until the link is approved.
  - An ADMIN entry in Gestión de usuarios is approved directly.
  - The uniqueness check only counts approved links, so an impostor can't block the real owner.
  - Owner confirmation goes through 5d.
- **H2:** encrypt with AES-256 through pypdf (never RC4), and keep the content minimal.
- **H3:** T2 maps cédula to sales through the KPI persona key (vendedor master, P:cedula), the same identity KPI's uses. Test it with 84.
- **M1:** send only after the KPI summary has been rebuilt for that data. Never compute live.
- **M2:**
  - The ledger key is (cedula, fecha_datos), where fecha_datos is the last sales date covered.
  - ADMIN gets a manual "Reenviar" for a date after a correction or reload.
- **M3:** T2 reuses 84's helpers (festivos, días hábiles restantes, falta_100, siguiente tramo, venta diaria necesaria), so the PDF always matches the web card.
- **M4:** the PDF is labelled "Comisión ESTIMADA · datos al <fecha>". It is not a payment statement.
- **M5:** no carga (Sunday or holiday) means no report.
- **LOW:**
  - A 403 marks the asesor and lists them for the admin.
  - A 429 is retried with backoff.
- **2026-10-07, owner:** a button in Configuración, "Reenviar reportes a todos los asesores", ADMIN only.
  - It resends the latest available date, or a date the admin picks.
  - It asks for confirmation and shows how many asesores will receive the report.
  - It bypasses the "one per day" ledger, and records each resend in the ledger with the user and time.
  - This is part of T3.
- 2026-10-07: T2 contract agreed with 84.
  - `reportes_asesores(db, fecha)` returns `{reportes: {cedula: {cedula, nombre, tienda, mes, fecha_datos, venta_cumplimiento, venta_comision, presupuesto, cumplimiento_pct, tramo, comision, bono_total, total_a_pagar, siguiente_tramo, compuerta, falta_100, dias_habiles_restantes, venta_diaria_necesaria, bonos[], tramos[]}}, sin_presupuesto: [{cedula, nombre, venta}], sin_cedula: [{vendedor, venta}]}`.
  - Money is in whole pesos and percentages are fractions.
  - Readiness: an APLICADO VENTAS carga with `periodo_hasta ≥ yesterday` and the KPI summary not dirty; otherwise wait until the deadline (default 10:00).
- 2026-10-07: owner decision (direct, "conmigo"): only the ADMIN sets the cédula, in Gestión de usuarios. It is validated against the active vendedor master and must be unique.
  - There is no self-entry in Lore and no approval flow.
  - This supersedes "Lore asks for the cédula at registration" and the H1 pending flow.
- 2026-10-07 FINAL (owner, clarified directly): BOTH flows apply. This supersedes the previous entry.
  - **New users:** Lore asks for the cédula. It stays PENDING until the ADMIN approves it.
  - **Existing users:** the ADMIN sets it in Gestión de usuarios, and it is approved directly.
  - Reports go only to approved links. The partial unique index applies only to approved cédulas.
- 2026-10-07: owner requirement, relayed by 84 and to be confirmed directly. The PDF replicates the KPI single-asesor view, one page per asesor:
  - ficha;
  - cumplimiento gauge;
  - commission card ("Para ganar más bonos" / "Para llegar al 100%");
  - tiles;
  - tendencia;
  - venta por línea;
  - Tecnired;
  - "Así se calcula tu comisión".

  Peer comparisons stay out: no puestos, no "vs red", no comparison with the tienda, no other asesores' dots.
  - T2 adds `reportes[cedula].detalle`, the same structure as `/kpis/asesores/detalle` minus the peer fields.
  - Visual reference: `components/motored/kpis/asesores/AsesorDetalle.js` and the AsesoresUno canvas.
  - T3 renders it server-side with WeasyPrint plus inline SVG charts (no JS), then encrypts it with AES-256.
- 2026-10-07: owner decision, relayed by 84 (the owner answered 84 directly). The PDF is IDENTICAL to the screen, comparisons INCLUDED: puestos, comparison with the tienda and the red, the strip with other asesores' dots, and the "vs red" refs. This overrides "no peer comparisons". `detalle.comparaciones` is populated.
  - Privacy note given to the owner: each asesor sees peers' positions and values.
- 2026-10-07: owner decision, relayed by 84: the PDF is ONE long continuous page, not split into pages.
  - Width close to phone or tablet reading width (about 720–800 px).
  - With WeasyPrint, render once to measure the content height, then set `@page` size to the width × the measured height (two passes).
- 2026-10-07: owner priorities for the PDF, relayed by 84:
  1. It looks identical to the asesor screen.
  2. It is easy to read on a phone and never tiny.
  - Layout rules:
    - width about 720–800 px;
    - body text at least 14 px, labels at least 12 px;
    - big figures as on screen (total about 32 px, gauge % about 44 px);
    - charts at full width;
    - tables wrap instead of shrinking.
  - **Gate:** before enabling the daily send, render ONE real asesor's PDF and have the owner approve it on a phone. The send stays OFF by default until then.

## 2026-10-07 REDESIGN (owner: "un link para cada uno")
No PDF. Each asesor gets a personal link through Lore that opens the single-asesor KPI view (identical, with comparisons) after the asesor enters their cédula.

### This session
- **T3a:** migration for the token table `reporte_asesor_link`. It goes on top of the head after T1, and 84 gets pinged with the model name and the head.
  - Columns: token (32+ bytes urlsafe, unique), cedula, mes, vence_en (month end plus a few days), revocado_en, creado_por, ultimo_acceso_en, intentos_fallidos INT NOT NULL DEFAULT 0, bloqueado_hasta TIMESTAMPTZ NULL.
  - Revoked automatically when the usuario is deactivated, the cédula is cleared or unapproved, or the Telegram changes.
- **T3b:** the daily Lore message, which includes a summary line from T2 and the link, plus:
  - the ledger (cedula, fecha_datos);
  - readiness and the deadline;
  - the "Reenviar a todos" button in Configuración;
  - admin revocation;
  - the kill switch, OFF by default until the owner approves a real sample.
- **T3c:** a narrow public allowlist entry in `deps.py` for POST `/api/motored/publico/informe/`, in its own commit, timed with 84's endpoint.

### 84
- `POST /api/motored/publico/informe/{token}` with body `{cedula}`.
- It returns the `/kpis/asesores/detalle` payload, rate-limited through the token row (5 failures lock it for 15 min).
- Responses carry `Cache-Control: no-store` and `X-Robots-Tag: noindex`, and every failure gets the same generic error ("Enlace o cédula no válidos").
- Public page `/motored/informe/[token]`, reusing `AsesorDetalle` read-only, mobile-first.
- 2026-10-07: owner decision, relayed by 84: the link page asks for the cédula EVERY time it is opened. Nothing is remembered on the device: the cédula lives only in memory for the open page, with no localStorage, sessionStorage or cookie. The same link stays valid all month and shows live data.
- 2026-10-07: owner decision (direct): the secret link per asesor is PERMANENT, with no monthly expiry.
  - It is revoked automatically when the usuario is deactivated or the cédula is changed or cleared.
  - The ADMIN can regenerate it.
  - The token table drops `mes` and `vence_en`; there is one active token per cédula.
- 2026-10-07: owner approved the placement.
  - **Gestión de usuarios, per asesor:**
    - "Enlace del informe" state: active or not, plus the last access time.
    - "Generar enlace nuevo": revokes the old link, creates a new one and sends it through Lore, after a confirmation.
    - "Anular enlace": after a confirmation.
  - **Configuración:** the daily-send on/off switch and "Reenviar a todos".
- **Next (2026-10-08):** T3a token table migration on top of c6d2f8a41b97, then ping 84 with the model name and head.
- [x] T3a (e222999 backend + migration 86b1df9d3d5f, 8233293 UI; backend 6298 passed, pg_real 751 passed, jest 2255 passed). Needs `MOTORED_PUBLIC_URL` set in Coolify.
- **Next:** T3b, the daily Lore send (ledger, readiness and deadline, Configuración switch OFF by default, "Reenviar a todos"); T3c, the `deps.py` allowlist once a7's endpoint is ready.
- [x] T3b (4dce673 backend + migration e8f50a4c1a9b, ed99ef1 UI; backend 6397 passed, pg_real 763 passed, jest 2271 passed). The switch `reporte_asesor_envio_activo` is OFF by default.
- **Pending:** T3c, the `deps.py` allowlist for a7's public endpoint; MOTORED_PUBLIC_URL in Coolify; owner approval of a real link before turning the switch on.
