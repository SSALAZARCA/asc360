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
