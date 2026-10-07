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

- [ ] T1
- [ ] T2
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
