# Design: Motored physical inventory counts (total and selective)

Source of requirements: `odd/tasks/motored-conteos-inventario.md` (owner decisions 2026-10-08). This document does not reopen any decided point. It defines HOW to build them. No SDD proposal artifact exists for this feature; the ODD feature document plays that role.

Alembic head re-checked on 2026-10-08: `d7a3c5e91f20` (`backend/alembic_motored/versions/d7a3c5e91f20_coordinador_repuestos_role.py:26-27`). No revision uses it as `down_revision`.

---

## 1. Evidence map (existing code this module builds on)

### 1.1 Inventory ingest and the "latest carga" per store

| Fact | Evidence |
|---|---|
| INVENTARIO file columns include `Costo prom. uni.` (mandatory since 2026-10-01). | `backend/app/motored/services/ingesta/inventario.py:85-94` |
| Each file row is resolved to a `sucursal_id` through the bodega code first, then the name. | `inventario.py:152-188`, `services/ingesta/resolucion.py:174-182` |
| A secondary bodega resolves to its principal's sucursal by following `bodega.bodega_principal`. | `resolucion.py:88-111`, `resolucion.py:143-150`, `models/bodega.py:23-26` |
| `inventario_detalle` holds one row per raw physical bodega line: `bodega` (raw code), `existencia`, `costo_unitario` (nullable, can be <= 0). | `models/inventario_detalle.py:28-44`, built in `inventario.py:329-354` |
| Readers must filter `carga_archivo.estado != 'ANULADO'` and exclude costs NULL or <= 0. | `models/inventario_detalle.py:7-17` |
| Applying a carga DELETES every `inventario_detalle` row of each `(fecha_corte, sucursal)` in that carga and re-inserts it. | `inventario.py:357-384` (delete at `:371-377`) |
| `inventario_snapshot` holds the consolidated stock per `(fecha_corte, sucursal, referencia)`; same-date reloads replace it. | `models/inventario_snapshot.py:23-41`, `inventario.py:284-311` |
| The retention job purges `inventario_detalle` and `inventario_snapshot` older than the window. | `services/retencion.py:157-190` |
| `carga_archivo`: `estado` (varchar), `periodo_desde/hasta` (declared `fecha_corte`), `aplicado_en`. | `models/carga_archivo.py:77`, `:83-84`, `:93` |
| Existing "latest inventory" helper is GLOBAL (`max(fecha_corte)` over every store), not per store. | `services/tablero_asesores_consultas.py:324-332` |
| Median of costs > 0 per referencia in one `fecha_corte` (fallback chain used by the KPI board). | `tablero_asesores_consultas.py:25-28`, `:194-208` |
| Associated stores: `sucursal.principal_id` rolls a store into its principal only at READ time; each keeps its own data. | `models/sucursal.py:19-24`, `:75-80` |
| `sucursal.bodega_principal` names the store's principal bodega code. | `models/sucursal.py:70` |

Consequence for this design: the "latest applied INVENTARIO carga for a store" is the newest `fecha_corte` (then newest `aplicado_en`) among `inventario_detalle` rows of that `sucursal_id` whose carga is not `ANULADO`. Because a later upload with the same `fecha_corte` deletes those rows (`inventario.py:371-377`) and retention purges old ones, a conteo MUST copy its rows, never reference them.

### 1.2 Referencia lookup by code

| Fact | Evidence |
|---|---|
| `referencia.codigo` is UNIQUE, stored trimmed, case preserved. | `models/referencia.py:5-7`, `:46`, `:49` |
| Migration guaranteed no duplicates under `upper(trim(codigo))`. | `alembic_motored/versions/f3a8d1c5b704_referencia_codigo_unico.py:13-19`, `:37-40` |
| The Lore bot resolves typed codes with exact `upper(trim(codigo))` against ACTIVE referencias; more than one hit means unresolved. | `api/bot_demanda_perdida.py:170-190` |
| The ingest cache resolves ALL referencias (active or not) by `codigo.strip()`. | `resolucion.py:128-133`, `:255-261` |

Decision: scans normalize with `strip().upper()` and match `upper(trim(codigo))` against ALL referencias (inactive included, because inventory may hold inactive items, same reason as `resolucion.py:128-130`).

### 1.3 Roles

| Fact | Evidence |
|---|---|
| Enum `motored_role`; a new value needs its own revision with `autocommit_block()`. | `d7a3c5e91f20_coordinador_repuestos_role.py:7-17`, `:32-37` |
| Python enum `MotoredRole`; column `Enum(MotoredRole, name="motored_role")`. | `models/usuario.py:44-58`, `:94` |
| Path allow-lists per confined role, enforced inside `get_current_motored_user`. | `deps.py:60-123`, `:126-149`, `:226` |
| `require_roles(*roles)`. | `deps.py:230-245` |
| Frontend role constants, home paths and confinement helpers. | `frontend/lib/motored/session.js:10-28`, `:50-53` |
| `VALID_ROLES` and the per-role redirect. | `frontend/app/motored/motored-layout.js:34-36`, `:51-66` |
| Sidebar items and `roles`. | `frontend/components/motored/MotoredSidebar.js:61-94`, `:168` |
| Roles/permissions matrix (drift-guarded by `motored-roles-permisos.test.jsx`). | `frontend/lib/motored/permisosPorRol.js:21-29`, `:39-58` |
| Role options in user creation; role label on Inicio. | `frontend/components/motored/UsuarioCreateForm.js:14-16`, `frontend/components/motored/inicio/textos.js:9-11` |
| Precedent tests for a confined role. | `backend/tests/motored/test_coordinador_repuestos_role.py`, `backend/tests/motored/pg_real/test_coordinador_repuestos_pg.py`, `frontend/__tests__/motored-coordinador-repuestos.test.jsx` |

### 1.4 Public, no-login endpoints

| Fact | Evidence |
|---|---|
| Public router without `get_current_motored_user`; `_RutaPublica` adds `Cache-Control: no-store` and `X-Robots-Tag` even on errors. | `api/publico_informe.py:1-13`, `:24-52` |
| DB-backed attempt counter on the link row: 5 failures, 15-minute lock, committed BEFORE the 401; `SELECT ... FOR UPDATE`. | `services/informe_publico.py:29-32`, `:60-64`, `:88-120` |
| Survey: slowapi per-IP limits (`10/minute`) plus an IN-MEMORY per-cédula counter. | `api/encuesta_publica.py:29-34`, `:102-127`; `services/encuesta_intentos.py:30-37` |
| slowapi keyed by remote address. | `backend/app/core/limiter.py:1-4` |
| Link token = `secrets.token_urlsafe(32)`; public URL built from `MOTORED_PUBLIC_URL`. | `services/reporte_asesor_link.py:31-32`, `:130`, `:171-178` |
| Public frontend pages are public because they are NOT wrapped in `MotoredLayout`. | `frontend/app/motored/informe/[token]/page.js:1-5` |
| Cédula normalization (digits only). | `backend/app/motored/schemas/vendedor.py:29-40` |

### 1.5 Configuración

| Fact | Evidence |
|---|---|
| Typed key registry; group `OPERACION` for business settings; tabs in `SECCIONES`. | `services/parametros_claves.py:43`, `:51-58` |
| `objeto_numerico` with ordering constraints between fields (`menores`). | `parametros_claves.py:275-301` |
| Registry assembly. | `parametros_claves.py:630-682` |
| Values are versioned from the 1st of a month. | `parametros_claves.py:764-778` |
| Frontend tabs. | `frontend/components/motored/configuracion/secciones.js:2-10` |

### 1.6 Telegram / Lore

| Fact | Evidence |
|---|---|
| Backend sends via Bot API with `LORE_BOT_TOKEN`; plain text only, no `reply_markup`; never raises, never logs the token. | `services/avisos_telegram.py:1-50` |
| Batch send with 429 backoff, ~1 msg/s, ledger commit per send, advisory locks. | `services/reporte_asesor_envio.py:418-453`, `:515-538`, `:543-558`, `:89-91` |
| Lore auth: shared secret + `X-Lore-Telegram-Id`; candidates = all usuarios with that `telegram_id`; `X-Lore-Usuario-Id` only chooses among them. | `deps_bot.py:88-124`, `:159-171`, `:178-231` |
| Lore secret must differ from Sonia/Motored secrets (isolation rule). | `deps_bot.py:61-73` |
| `usuario.telegram_id`, `cedula`, `cedula_aprobada`. | `models/usuario.py:97`, `:108-112` |
| A Telegram Mini App already exists on the UM side (not Lore): generic HMAC validator `verify_telegram_initdata(init_data, bot_token, max_age_seconds)`. | `backend/app/core/security.py:57-85`, used by `backend/app/api/v1/auth.py:301-304`; page `frontend/app/tg/page.js:6-27`, `:53` |
| No Motored/Lore Mini App exists. Lore handlers are python-telegram-bot `CommandHandler`/`CallbackQueryHandler`. | `lore-bot/lore/main.py:217-230` |

### 1.7 Background loops

| Fact | Evidence |
|---|---|
| Lazy start of every Motored loop from `require_motored_ready`. | `deps.py:248-275` |
| Loop pattern: `ensure_started()` never raises, sleep-before-tick, broken tick logged, advisory lock in a separate session. | `services/trabajos/supervisor_reporte_asesor.py:55-67`, `:93-114`, `:171-180` |

### 1.8 Live updates and deployment

| Fact | Evidence |
|---|---|
| No SSE or WebSocket in Motored; polling is the precedent ("No WebSocket/SSE exists"). | `frontend/components/motored/cargas/CargaDetalle.js:5-11`, `frontend/components/motored/kpis/useRecalculo.js:39` |
| Single uvicorn process (no `--workers`), `--proxy-headers --forwarded-allow-ips='*'`. | `backend/scripts/start.sh:25` |
| Traefik routes `Host(asc360.online) && PathPrefix(/api)` to the backend. | `docker-compose.coolify.yml:93-100` |
| Motored engine uses SQLAlchemy defaults (pool 5 + overflow 10); sessions `autoflush=False`; every request also runs `SELECT 1`. | `backend/app/motored/database.py:37-47`, `deps.py:152-167` |

### 1.9 Sales data for ABC

| Fact | Evidence |
|---|---|
| `venta_mensual` has UNITS only (no money). | `models/venta_mensual.py:38-57` |
| `venta_detalle` has `valor_bruto`, `valor_descuentos`, `fecha`, `sucursal_id`, `referencia_id`; index `(sucursal_id, fecha)`. | `models/venta_detalle.py:28-31`, `:36-54` |
| Sale money of a line = `valor_bruto - valor_descuentos`. | `tablero_asesores_consultas.py:174`, `services/kpi_resumen.py:12` |

### 1.10 Excel and QR

| Fact | Evidence |
|---|---|
| openpyxl builders returning bytes; codes/cédulas as text cells; Bogotá timestamps. | `services/encuesta_excel.py:55-60`, `:80-91` |
| Download helper with RFC 5987 `Content-Disposition` and `no-store`. | `api/corridas_comun.py:143-159`, `services/corridas/exportacion_hmcl.py:157` |
| `openpyxl==3.1.5` and `qrcode[pil]==8.2` already in the backend. | `backend/requirements.txt:22`, `:24` |
| No QR or barcode library in the frontend. | `frontend/package.json:16-28` |

---

## 2. Technical approach

A new bounded module `conteos` inside Motored, split by consumer:

```
backend/app/motored/
  models/conteo*.py, ubicacion_inventario.py           data model (section 4)
  services/conteos/
    snapshot.py        Iniciar: resolve latest carga, copy rows, cost fallback, staleness
    acceso.py          slug, short code, session tokens, attempt counters
    lecturas.py        code normalization, idempotent batch insert, void
    reconteo.py        end of round 1, candidates, different-pair assignment
    cierre.py          close, result materialization, KPI
    panel.py           live aggregates (stage 2)
    excel_ajuste.py    adjustment workbook (stage 4)
    abc.py, selectivo.py   ABC and weekly list (stage 3)
    miniapp.py         initData exchange, asesor sessions (stage 3)
  services/trabajos/supervisor_conteos.py               weekly loop (stage 3)
  api/conteos.py              leader/admin/gerencia (JWT, /api/motored/conteos)
  api/publico_conteos.py      pairs (no login, /api/motored/publico/conteos)
  api/miniapp_conteos.py      Lore Mini App (initData, /api/motored/miniapp/conteos)
  api/ruta_publica.py         `_RutaPublica` extracted from publico_informe.py and shared
frontend/
  app/motored/conteos/...                     leader screens (MotoredLayout)
  app/motored/c/[slug]/page.js                pair counting (public, no MotoredLayout)
  app/motored/lore/conteo/page.js             Lore Mini App (public, no MotoredLayout)
  components/motored/conteos/...              leader containers/presentational
  components/motored/conteo-pareja/...        shared counting UI (pairs + Mini App)
  lib/motored/conteosApi.js, conteoParejaApi.js, conteoMiniappApi.js
lore-bot/lore/handlers/conteo.py              `/conteo` replies with a web_app button (stage 3)
```

Principles:
- The app never changes stock. Every write is to `conteo*` tables.
- One conteo = one frozen snapshot. A store's "system quantity" for a count is whatever was copied at Iniciar.
- Blind count is enforced by response schemas: no pair or Mini App response model contains a system quantity, cost or difference field.
- Pair and Mini App surfaces are public routes with their own token auth, outside `get_current_motored_user`, following `publico_informe.py`.
- Polling, not SSE (section 9.4).

---

## 3. Architecture decisions

### ADR-1: Copy the inventory rows into the conteo at Iniciar
**Choice**: `INSERT ... SELECT` from `inventario_detalle` into `conteo_snapshot_linea` inside the Iniciar transaction, aggregated per `(referencia_id, bodega)`, with the frozen unit cost.
**Alternatives**: (a) store only `carga_id` and read `inventario_detalle` live; (b) read `inventario_snapshot`.
**Rationale**: (a) breaks when a same-date reload deletes the rows (`inventario.py:371-377`), when the carga is annulled, or when retention purges them (`retencion.py:157-190`). (b) has no bodega and no cost (`inventario_snapshot.py:33-41`), and the owner requires valuation per referencia and bodega at "Costo prom. uni.".

### ADR-2: Resolve and copy in ONE SQL statement
**Choice**: a CTE picks the newest `(fecha_corte, aplicado_en)` carga of the store (not ANULADO) and the same statement copies its rows, filtered by `carga_id` and `sucursal_id`.
**Alternatives**: two statements (resolve, then copy).
**Rationale**: under READ COMMITTED, an INVENTARIO apply committing between the two statements could delete the resolved rows and yield an empty snapshot. One statement sees one consistent snapshot. Zero copied rows still raises `409 SIN_INVENTARIO`.

### ADR-3: Unified device session table for pairs and asesores
**Choice**: `conteo_sesion` (tipo `PAREJA` or `ASESOR`) plus `conteo_integrante` (1-3 people per session, name and cédula). Every reading points to its session.
**Alternatives**: separate pair and asesor tables; cédulas as columns on the session.
**Rationale**: the same readings, reconteo and "different pair" logic serve both total and selective counts. The different-pair rule compares cédula sets, which a child table makes a simple join.

### ADR-4: "Different pair" = disjoint cédula sets
**Choice**: a reconteo for referencia R may be assigned to session S only if no cédula of S belongs to any session that has a non-voided round-1 reading of R. Exception: the leader authorizes the same pair when no eligible session is connected; the override is stored (who, when, reason).
**Alternatives**: compare session ids.
**Rationale**: the same two people can open a second device session; comparing ids would let them recount their own work.

### ADR-5: Client-generated reading ids, batched POSTs
**Choice**: each reading has a client UUID (primary key). The device queues readings (localStorage) and flushes every ~1.5 s or 20 readings; the server does `INSERT ... ON CONFLICT (id) DO NOTHING`.
**Alternatives**: one request per scan; server-generated ids.
**Rationale**: idempotent retries over unstable store Wi-Fi, no lost or doubled units, and 10-20x fewer requests against a 15-connection pool.

### ADR-6: The whole referencia master is downloadable by a joined device
**Choice**: `GET /publico/conteos/catalogo` returns `[code, name]` of ALL referencias (not store-specific), cached with an ETag. The device validates scans instantly and offline; the server stays authoritative.
**Alternatives**: server-only resolution (no instant feedback); a store-specific list (leaks what the system expects in that store).
**Rationale**: instant beep on a scanner gun matters for throughput; the global master reveals nothing about the store's expected stock, so the blind count holds.

### ADR-7: Short slug + rotating 6-digit code; only the code hash is stored
**Choice**: URL `/motored/c/{slug}` (10 chars, 50 bits) for QR and copy-paste; joining also needs a 6-digit code. The code is stored as `HMAC-SHA256(MOTORED_SECRET_KEY, conteo_id || code)` and shown only when generated or rotated.
**Alternatives**: a 43-char token alone; plaintext code.
**Rationale**: laptops need a typeable link. The code proves physical presence and can be rotated without affecting connected pairs. Since only the hash is stored, losing the leader's screen means "rotate to see a new code", which is harmless (sessions survive rotation).

### ADR-8: Polling with a version short-circuit
**Choice**: leader panel polls every 5 s while visible (30 s hidden). The request carries the last `version` (= `max(conteo_lectura.seq)` + reconteo/session change markers). If unchanged, the server answers `{sin_cambios: true}` after an index-only lookup.
**Alternatives**: SSE; WebSocket; Redis pub/sub.
**Rationale**: section 9.4.

### ADR-9: Thresholds frozen on the conteo at Iniciar
**Choice**: copy the vigente `conteo_umbrales_pesos` into `conteo.umbral_reconteo_pesos/umbral_critico_pesos`.
**Rationale**: an ADMIN edit in Configuración mid-count must not change which referencias need reconteo or show red.

### ADR-10: One selective conteo per store per day; unfinished lines carry over
**Choice**: the weekly list is a `SELECTIVO` conteo whose snapshot is frozen when the first asesor opens it that morning. At the configured close hour it closes; uncounted items move to a new conteo for the next opening (new snapshot). Differences create a next-day verification conteo.
**Alternatives**: one weekly conteo with one snapshot; per-line snapshots.
**Rationale**: the owner requires "against that morning's inventory" with the store OPEN. One snapshot per conteo keeps every comparison against a single frozen morning and keeps the TOTAL and SELECTIVO code paths identical.

### ADR-11: Role identifier `LIDER_INVENTARIOS`
**Choice**: enum value `LIDER_INVENTARIOS`, label "Líder de inventarios".
**Rationale**: ASCII and the existing naming style (`COORDINADOR_REPUESTOS` drops "DE").

---

## 4. Data model

All tables in the Motored database (`MotoredBase`). UUID PKs with `default=uuid.uuid4`. Timestamps `timestamptz` unless noted. Enumerations are `String` + `CHECK`, never Postgres enums (same reason as `carga_archivo.estado`, `models/carga_archivo.py:7-8`): new states need no type migration.

### 4.1 `conteo` (stage 1)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tipo | String(10) NOT NULL | CHECK IN ('TOTAL','SELECTIVO') |
| sucursal_id | UUID NOT NULL FK sucursal ON DELETE RESTRICT | physical store; never rolled up to `principal_id` |
| estado | String(16) NOT NULL | CHECK IN ('PROGRAMADO','EN_CONTEO','EN_RECONTEO','CERRADO','ANULADO') |
| fecha_programada | Date NOT NULL | |
| origen | String(12) NOT NULL | 'MANUAL' or 'AUTOMATICO' (selective generator) |
| semana_iso | String(8) NULL | 'YYYY-Www', selective only |
| verifica_conteo_id | UUID NULL FK conteo ON DELETE RESTRICT | selective day-2 verification |
| arrastra_conteo_id | UUID NULL FK conteo ON DELETE RESTRICT | selective carry-over source |
| creado_por, iniciado_por, cerrado_por, anulado_por | UUID NULL FK usuario | `iniciado_por` is the leader of record |
| motivo_anulacion, motivo_cierre_forzado | Text NULL | |
| snapshot_carga_id | UUID NULL FK carga_archivo ON DELETE SET NULL | the copy survives the carga |
| snapshot_fecha_corte | Date NULL | kept even if the carga row disappears |
| snapshot_aplicado_en | timestamptz NULL | shown at Iniciar |
| snapshot_tomado_en | timestamptz NULL | |
| snapshot_advertencias | JSONB NULL | e.g. `{"antiguedad_dias": 3, "confirmada_por": "<usuario_id>"}` |
| umbral_reconteo_pesos, umbral_critico_pesos | Numeric(16,2) NULL | frozen at Iniciar (ADR-9) |
| enlace_slug | String(16) NULL UNIQUE | pairs' link (TOTAL only) |
| codigo_hash | String(64) NULL | HMAC of the 6-digit code (ADR-7) |
| codigo_rotado_en | timestamptz NULL | |
| acceso_fallidos_hora | Integer NOT NULL default 0 | global per-conteo failure counter |
| acceso_ventana_inicio | timestamptz NULL | start of the counter's 1-hour window |
| iniciado_en, ronda_terminada_en, cerrado_en, anulado_en | timestamptz NULL | |
| refs_universo, refs_exactas | Integer NULL | KPI at close |
| exactitud_pct | Numeric(6,2) NULL | |
| valor_sistema, valor_diferencia_neta, valor_diferencia_abs | Numeric(18,2) NULL | |
| created_at, updated_at | timestamptz | |

Constraints and indexes:
- `uq_conteo_total_abierto`: UNIQUE (sucursal_id) WHERE tipo='TOTAL' AND estado IN ('EN_CONTEO','EN_RECONTEO'). One running total count per store; several stores in parallel are fine.
- `uq_conteo_selectivo_semana`: UNIQUE (sucursal_id, semana_iso) WHERE tipo='SELECTIVO' AND origen='AUTOMATICO' AND verifica_conteo_id IS NULL AND arrastra_conteo_id IS NULL AND estado <> 'ANULADO'. Makes the weekly generator idempotent.
- `ck_conteo_snapshot_si_iniciado`: estado IN ('PROGRAMADO','ANULADO') OR snapshot_tomado_en IS NOT NULL.
- `ck_conteo_slug_solo_total`: tipo='TOTAL' OR enlace_slug IS NULL.
- `ix_conteo_estado_fecha` (estado, fecha_programada); `ix_conteo_sucursal_cerrado` (sucursal_id, cerrado_en DESC).

### 4.2 `conteo_snapshot_linea` (stage 1)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| conteo_id | UUID NOT NULL FK conteo ON DELETE CASCADE | |
| referencia_id | UUID NOT NULL FK referencia ON DELETE RESTRICT | |
| bodega | String(20) NOT NULL | raw physical bodega code (same as `inventario_detalle.bodega`) |
| existencia | Numeric(14,2) NOT NULL | can be negative (kept as exported) |
| costo_unitario | Numeric(16,2) NULL | frozen |
| costo_fuente | String(12) NOT NULL | 'BODEGA','REFERENCIA','MEDIANA','PRECIO','SIN_COSTO' |

- UNIQUE (conteo_id, referencia_id, bodega). It also serves lookups by (conteo_id, referencia_id).
- Selective conteos copy only the listed referencias.

### 4.3 `ubicacion_inventario` (stage 1; label printing in stage 2)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| sucursal_id | UUID NOT NULL FK sucursal RESTRICT | locations persist across counts so printed labels are reused |
| codigo | String(30) NOT NULL | normalized upper; label barcode value is `UBI-` + codigo |
| nombre | String(60) NOT NULL | "Estante A3" |
| bodega | String(20) NULL | NULL = the store's principal bodega (`sucursal.bodega_principal`) |
| activa | Boolean NOT NULL default true | |
| origen | String(8) NOT NULL | 'LIDER' or 'PAREJA' (typed ad hoc during a count) |
| created_at, created_by (NULL FK usuario) | | |

- UNIQUE (sucursal_id, codigo).
- Creation rejects a `codigo` whose `UBI-` form equals a referencia code (guards the scanner's location detection).

### 4.4 `conteo_sesion` and `conteo_integrante` (stage 1)

`conteo_sesion`:

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| conteo_id | UUID NOT NULL FK conteo CASCADE | |
| tipo | String(8) NOT NULL | 'PAREJA' or 'ASESOR' |
| token_hash | String(64) NOT NULL UNIQUE | sha256 of the device token |
| estado | String(14) NOT NULL | 'CONECTADA','DESCONECTADA','CERRADA' |
| dispositivo | String(10) NOT NULL | 'ESCRITORIO','MOVIL','MINIAPP' |
| ubicacion_actual_id | UUID NULL FK ubicacion_inventario ON DELETE SET NULL | |
| usuario_id | UUID NULL FK usuario | ASESOR sessions |
| telegram_id | BigInteger NULL | ASESOR sessions |
| conectada_en, ultima_actividad_en, desconectada_en | timestamptz | |
| desconectada_por | UUID NULL FK usuario | NULL = the device left by itself |

- CHECK tipo='PAREJA' OR usuario_id IS NOT NULL.
- `ix_conteo_sesion_conteo_estado` (conteo_id, estado).

`conteo_integrante`:

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| sesion_id | UUID NOT NULL FK conteo_sesion CASCADE | |
| orden | SmallInteger NOT NULL | 1..3 |
| nombre | String(120) NOT NULL | |
| cedula | String(20) NOT NULL | normalized with `limpiar_cedula` (`schemas/vendedor.py:29-40`); never returned by any API |

- UNIQUE (sesion_id, orden); `ix_conteo_integrante_sesion` (sesion_id).

### 4.5 `conteo_lectura` (stage 1)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | client-generated (ADR-5) |
| seq | BigInteger GENERATED ALWAYS AS IDENTITY, UNIQUE | monotonic version for polling |
| conteo_id | UUID NOT NULL FK conteo CASCADE | |
| sesion_id | UUID NOT NULL FK conteo_sesion CASCADE | |
| ubicacion_id | UUID NOT NULL FK ubicacion_inventario RESTRICT | location first |
| referencia_id | UUID NULL FK referencia RESTRICT | NULL = code not in the master |
| codigo_leido | String(100) NOT NULL | normalized `strip().upper()` |
| cantidad | Numeric(12,2) NOT NULL | CHECK cantidad > 0 AND cantidad <= 99999 |
| ronda | SmallInteger NOT NULL | CHECK IN (1,2) |
| reconteo_id | UUID NULL FK conteo_reconteo CASCADE | CHECK ronda=1 OR reconteo_id IS NOT NULL |
| metodo | String(8) NOT NULL | 'ESCANER','CAMARA','MANUAL' |
| leida_en | timestamptz NOT NULL | device clock |
| recibida_en | timestamptz NOT NULL default now() | server clock |
| anulada_en | timestamptz NULL | voided by its own session |

Indexes:
- `ix_conteo_lectura_agregado` (conteo_id, ronda, referencia_id) INCLUDE (cantidad) WHERE anulada_en IS NULL: live panel and close aggregates.
- `ix_conteo_lectura_conteo_seq` (conteo_id, seq DESC): `max(seq)` index-only for the version check.
- `ix_conteo_lectura_sesion_seq` (sesion_id, seq DESC): a session's recent readings and per-session totals.
- `ix_conteo_lectura_conteo_ubicacion` (conteo_id, ubicacion_id) WHERE anulada_en IS NULL: progress per location; reconteo location lists.

### 4.6 `conteo_reconteo` (stage 1)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| conteo_id | UUID NOT NULL FK conteo CASCADE | |
| referencia_id | UUID NULL FK referencia | NULL with `codigo` for codes not in the master |
| codigo | String(100) NOT NULL | |
| estado | String(10) NOT NULL | 'PENDIENTE','ASIGNADO','TERMINADO','CANCELADO' |
| origen | String(8) NOT NULL | 'UMBRAL' (automatic) or 'LIDER' (manual) |
| diferencia_ronda1, valor_ronda1 | Numeric | leader-only, frozen at end of round 1 |
| sesion_id | UUID NULL FK conteo_sesion | assignee |
| asignado_por | UUID NULL FK usuario | |
| misma_pareja_autorizada | Boolean NOT NULL default false | leader override (ADR-4) |
| motivo_autorizacion | Text NULL | required when the override is true |
| asignado_en, terminado_en, cancelado_en | timestamptz NULL | |

- UNIQUE (conteo_id, codigo) WHERE estado <> 'CANCELADO'.
- CHECK estado NOT IN ('ASIGNADO','TERMINADO') OR sesion_id IS NOT NULL.
- CHECK NOT misma_pareja_autorizada OR motivo_autorizacion IS NOT NULL.

### 4.7 `conteo_acceso_intento` (stage 1)

| Column | Type | Notes |
|---|---|---|
| conteo_id | UUID FK conteo CASCADE | PK part |
| cliente | String(64) | PK part; sha256 of the client IP (no raw IP stored) |
| fallidos | Integer NOT NULL | |
| ventana_inicio | timestamptz NOT NULL | |
| bloqueado_hasta | timestamptz NULL | |

### 4.8 `conteo_resultado` (stage 1, written at close; read by stage 4)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| conteo_id | UUID NOT NULL FK conteo CASCADE | |
| sucursal_id | UUID NOT NULL FK sucursal | denormalized for history |
| referencia_id | UUID NULL FK referencia | |
| codigo | String(100) NOT NULL | |
| bodega | String(20) NOT NULL | |
| existencia_sistema | Numeric(14,2) NOT NULL | 0 for surplus items absent from the snapshot |
| cantidad_contada | Numeric(14,2) NOT NULL | final (round 2 if a finished reconteo exists) |
| diferencia | Numeric(14,2) NOT NULL | counted - system |
| costo_unitario | Numeric(16,2) NULL | |
| costo_fuente | String(12) NOT NULL | |
| valor_diferencia | Numeric(18,2) NULL | NULL when SIN_COSTO |
| ubicaciones | ARRAY(String(60)) NOT NULL default '{}' | location names where counted |
| con_reconteo, critico | Boolean NOT NULL | |
| confirmada | Boolean NULL | selective only: repeated in the verification conteo |
| cerrado_en | timestamptz NOT NULL | denormalized |

- UNIQUE (conteo_id, codigo, bodega).
- `ix_conteo_resultado_historial` (sucursal_id, referencia_id, cerrado_en DESC): "last count" lookups for the selective generator.

### 4.9 Stage 3 tables

`conteo_abc` (rebuilt per store each week, delete + insert in one transaction):

| Column | Type | Notes |
|---|---|---|
| sucursal_id | UUID FK sucursal | PK part |
| referencia_id | UUID FK referencia | PK part |
| clase | String(1) NOT NULL | CHECK IN ('A','B','C') |
| venta_valor | Numeric(18,2) NOT NULL | Σ(valor_bruto - valor_descuentos) in the window |
| participacion_acum | Numeric(7,4) NOT NULL | cumulative share |
| ventana_desde, ventana_hasta | Date NOT NULL | |
| calculado_en | timestamptz NOT NULL | |

`conteo_item` (the list of a SELECTIVO conteo):

| Column | Type | Notes |
|---|---|---|
| conteo_id | UUID FK conteo CASCADE | PK part |
| referencia_id | UUID FK referencia | PK part |
| motivo | String(16) NOT NULL | 'ABC','DIFERENCIA','NEGATIVO','VENTA_SIN_STOCK','ARRASTRE','VERIFICACION' |
| clase_abc | String(1) NULL | |
| prioridad | Integer NOT NULL | ordering in the Mini App |
| estado | String(10) NOT NULL | 'PENDIENTE','CONTADO' |

`miniapp_cedula_intento`: PK `telegram_id` BigInteger, `fallidos`, `ventana_inicio`, `bloqueado_hasta`. Brute-force guard for the shared-Telegram cédula prompt.

The selective SCHEDULE is not a separate table. A referencia's due date is derived: last `conteo_resultado.cerrado_en` for (store, referencia) plus its class frequency. It is materialized only as the weekly `conteo` + `conteo_item` rows, which are the auditable schedule. The selective counts BY ASESOR are `conteo_sesion` rows of tipo `ASESOR` (usuario_id, telegram_id) with one `conteo_integrante` holding the usuario's approved cédula (or the cédula typed on a shared Telegram).

### 4.10 How the frozen snapshot works when stores start at different times

Each Iniciar runs alone, in its own transaction, for its own store:

```sql
WITH ultima AS (
  SELECT d.carga_id, d.fecha_corte, c.aplicado_en
  FROM inventario_detalle d JOIN carga_archivo c ON c.id = d.carga_id
  WHERE d.sucursal_id = :sucursal AND c.estado <> 'ANULADO'
  ORDER BY d.fecha_corte DESC, c.aplicado_en DESC NULLS LAST
  LIMIT 1
), copiadas AS (
  INSERT INTO conteo_snapshot_linea (id, conteo_id, referencia_id, bodega, existencia, costo_unitario, costo_fuente)
  SELECT gen_random_uuid(), :conteo, d.referencia_id, d.bodega, sum(d.existencia),
         CASE WHEN sum(d.existencia) FILTER (WHERE d.costo_unitario > 0) > 0
              THEN sum(d.existencia * d.costo_unitario) FILTER (WHERE d.costo_unitario > 0)
                   / sum(d.existencia) FILTER (WHERE d.costo_unitario > 0)
              ELSE max(d.costo_unitario) FILTER (WHERE d.costo_unitario > 0) END,
         'BODEGA'
  FROM inventario_detalle d JOIN ultima u ON u.carga_id = d.carga_id
  WHERE d.sucursal_id = :sucursal
  GROUP BY d.referencia_id, d.bodega
  RETURNING 1
)
SELECT u.carga_id, u.fecha_corte, u.aplicado_en, (SELECT count(*) FROM copiadas) FROM ultima u;
```

(`gen_random_uuid()` needs PostgreSQL >= 13; the dev/prod compose files run 16. If the Motored server is older, generate ids in Python and use two steps under `SELECT ... FOR SHARE` on the carga row.) A follow-up `UPDATE` fills missing costs (`costo_fuente`), in order:
1. `REFERENCIA`: weighted cost > 0 of the same referencia in other bodegas of this snapshot;
2. `MEDIANA`: median cost > 0 of the referencia across ALL stores in the same carga (`percentile_cont`, same rule as `tablero_asesores_consultas.py:194-208`);
3. `PRECIO`: `referencia.precio_normal > 0`;
4. `SIN_COSTO`: valued 0, flagged.

Timeline example: store A starts at 18:00 and copies carga X (fecha_corte 10-08). At 19:00 someone re-uploads INVENTARIO for 10-08 (carga Y): the apply deletes and re-inserts `inventario_detalle` for every store in Y (`inventario.py:371-377`). A's snapshot is untouched because it is a copy. Store B starts at 19:30 and copies Y. Each conteo shows its own `snapshot_carga_id`, `snapshot_fecha_corte` and `snapshot_aplicado_en`.

Staleness: if `snapshot_fecha_corte < hoy_bogota - conteo_dias_max_antiguedad_inventario`, Iniciar answers `409 INVENTARIO_ANTIGUO` with the carga facts; the leader can retry with `confirmar_antiguedad: true`, which is recorded in `snapshot_advertencias`.

Bodegas: the system side is per `(referencia, bodega)`. Counted quantities get a bodega through their location (`ubicacion_inventario.bodega`, default `sucursal.bodega_principal`). Reconteo, critical alerts and the accuracy KPI compare at REFERENCIA level for the store (sum of bodegas vs sum of locations), as decided. The adjustment Excel is per (referencia, bodega). See risk R1.

---

## 5. State machines

### 5.1 TOTAL conteo

```
            crear                 iniciar (snapshot, slug, code)        terminar ronda 1
 (none) ──────────► PROGRAMADO ─────────────────────────► EN_CONTEO ───────────────────► EN_RECONTEO
                        │                                     │                              │
                        │ anular                              │ anular                       │ cerrar (no ASIGNADO left,
                        ▼                                     ▼                              │  or forzar + motivo)
                     ANULADO ◄────────────────────────────────┴──────────── anular ◄─────────┤
                                                                                             ▼
                                                                                          CERRADO
```

| Transition | Who | Guards / effects |
|---|---|---|
| crear | ADMIN, LIDER | store active |
| iniciar | ADMIN, LIDER | `SELECT ... FOR UPDATE`; estado PROGRAMADO; `uq_conteo_total_abierto`; snapshot copy (ADR-2); freeze thresholds; generate slug + code |
| terminar ronda 1 | ADMIN, LIDER | round-1 readings close; compute differences; create `UMBRAL` reconteos where abs(value) > umbral_reconteo OR (quantity difference != 0 AND SIN_COSTO) |
| cerrar | ADMIN, LIDER | no reconteo ASIGNADO, or `forzar` with motivo (cancels them); write `conteo_resultado`, KPI; revoke link; set every session CERRADA |
| anular | ADMIN, LIDER | motivo required; keeps readings; revokes link |

Pairs may join in EN_CONTEO and EN_RECONTEO (a fresh pair is often needed for reconteos). Round-1 readings are rejected after EN_RECONTEO (`RONDA_CERRADA`). The leader can still add manual reconteos for missed referencias.

### 5.2 Reconteo

```
 PENDIENTE ──asignar(sesion)──► ASIGNADO ──pair "terminé"──► TERMINADO
     ▲                             │
     └──── liberar / desconexión ──┘
 PENDIENTE | ASIGNADO ──cancelar (leader) / cierre forzado──► CANCELADO
```

- `asignar` checks ADR-4. With `autorizar_misma_pareja=true` the server additionally requires that no ELIGIBLE session is connected and stores the reason.
- Disconnecting a session returns its ASIGNADO reconteos to PENDIENTE (round-2 readings already taken are kept but ignored unless the reconteo finishes).
- Final quantity per referencia: TERMINADO reconteo -> sum of its round-2 readings (all locations); otherwise round 1.
- "The first pair never sees it": tasks are returned only to the assigned session, and round-2 readings are accepted only from that session and only for that reconteo's code.

### 5.3 Device session

`CONECTADA` -> `DESCONECTADA` (leader disconnect or the device leaves; readings kept) ; `CONECTADA` -> `CERRADA` (conteo closed or annulled). A request with a non-CONECTADA session gets `401 SESION_INACTIVA`; the page returns to the join screen.

### 5.4 SELECTIVO conteo (stage 3)

```
 PROGRAMADO ──first asesor opens (snapshot of the listed refs)──► EN_CONTEO ──all items CONTADO or close hour──► CERRADO
     │                                                                                                         │
     └── anular / expired without opening (moves items to next day) ──► ANULADO                                ├─ uncounted items ─► new SELECTIVO (ARRASTRE) next opening
                                                                                                               └─ items with difference ─► new SELECTIVO (VERIFICACION) next day
```

No EN_RECONTEO state: the day-2 verification conteo is the reconteo. A difference is CONFIRMED when the verification shows a non-zero difference with the same sign (`conteo_resultado.confirmada`); the confirmed value is the day-2 one. Confirmed differences appear in the leader panel.

---

## 6. API

Conventions: JSON; errors `{"detail": {"code": "...", ...}}` like the bot; money as decimal strings; times ISO-8601 UTC.

### 6.1 Leader API (`api/conteos.py`, prefix `/api/motored/conteos`)

Reads: `require_roles("ADMIN","LIDER_INVENTARIOS","GERENCIA")`. Writes: `require_roles("ADMIN","LIDER_INVENTARIOS")`. Path confinement: `/api/motored/conteos` added to the allow-lists of `LIDER_INVENTARIOS` and `GERENCIA` (section 8.5).

| Method and path | Stage | Purpose |
|---|---|---|
| GET `/sucursales` | 1 | active stores + latest inventory carga per store (`fecha_corte`, `aplicado_en`, `edad_dias`) |
| GET `/?estado=&sucursal_id=&tipo=&desde=&hasta=` | 1 | list |
| POST `/` | 1 | schedule a TOTAL conteo |
| PATCH `/{id}` | 1 | reschedule (PROGRAMADO only) |
| POST `/{id}/iniciar` | 1 | snapshot + access |
| GET `/{id}` | 1 | detail |
| GET `/{id}/qr.png` | 1 | QR of the pair URL (server-side `qrcode`; the code is never inside) |
| POST `/{id}/codigo/rotar` | 1 | new code |
| GET `/{id}/sesiones` | 1 | pairs |
| POST `/{id}/sesiones/{sid}/desconectar` | 1 | disconnect |
| POST `/{id}/terminar-ronda` | 1 | EN_CONTEO -> EN_RECONTEO |
| GET `/{id}/diferencias?filtro=todas|reconteo|criticas&page=` | 1 | leader-only differences |
| POST `/{id}/reconteos` | 1 | manual reconteo for codes |
| POST `/{id}/reconteos/{rid}/asignar` | 1 | assign (ADR-4) |
| POST `/{id}/reconteos/asignar-automatico` | 1 | round-robin over eligible connected sessions |
| POST `/{id}/reconteos/{rid}/cancelar` | 1 | cancel |
| POST `/{id}/cerrar` | 1 | close |
| POST `/{id}/anular` | 1 | annul |
| GET `/{id}/panel?version=` | 2 | live panel |
| GET/POST/PATCH `/ubicaciones?sucursal_id=` | 2 | location master (pairs can already create them in stage 1) |
| GET `/ubicaciones/etiquetas.pdf?sucursal_id=` | 2 | printable labels |
| GET `/{id}/ajuste.xlsx` | 4 | ERP adjustment Excel |
| GET `/kpi?sucursal_id=&desde=&hasta=` | 4 | accuracy history |
| GET `/selectivos?semana=` | 3 | weekly lists and confirmed differences |

Sketches:

```http
POST /api/motored/conteos
{"sucursal_id": "…", "fecha_programada": "2026-10-12"}
→ 201 {"id": "…", "estado": "PROGRAMADO", "tipo": "TOTAL", "sucursal": {"id": "…", "nombre": "…"}}

POST /api/motored/conteos/{id}/iniciar
{"confirmar_antiguedad": false}
→ 409 {"detail": {"code": "INVENTARIO_ANTIGUO", "fecha_corte": "2026-10-05",
                   "aplicado_en": "…", "edad_dias": 3, "maximo_dias": 1}}
→ 409 {"detail": {"code": "SIN_INVENTARIO"}}
→ 409 {"detail": {"code": "CONTEO_TOTAL_ABIERTO"}}            (partial unique index)
→ 200 {"estado": "EN_CONTEO",
       "snapshot": {"carga_id": "…", "nombre_archivo": "…", "fecha_corte": "2026-10-08",
                    "aplicado_en": "…", "lineas": 4210, "referencias": 3987,
                    "valor_sistema": "812345678.00", "sin_costo": 12},
       "umbrales": {"reconteo": "50000.00", "critico": "500000.00"},
       "acceso": {"url": "https://asc360.online/motored/c/K7Q2M9XH4P",
                  "slug": "K7Q2M9XH4P", "codigo": "482913", "qr_url": "/api/motored/conteos/{id}/qr.png"}}

POST /api/motored/conteos/{id}/codigo/rotar   → 200 {"codigo": "093117", "rotado_en": "…"}

GET /api/motored/conteos/{id}/sesiones
→ 200 [{"id": "…", "tipo": "PAREJA", "estado": "CONECTADA", "dispositivo": "ESCRITORIO",
        "integrantes": [{"nombre": "Ana Ruiz", "cedula_mask": "****4821"}, {"nombre": "Luis Gil", "cedula_mask": "****0193"}],
        "ubicacion_actual": {"id": "…", "nombre": "Estante A3"},
        "lecturas": 512, "referencias": 230, "ultima_actividad_en": "…",
        "reconteos_asignados": 3}]

POST /api/motored/conteos/{id}/reconteos/{rid}/asignar
{"sesion_id": "…", "autorizar_misma_pareja": false, "motivo": null}
→ 409 {"detail": {"code": "MISMA_PAREJA"}}                  (shares a cédula with a round-1 session)
→ 409 {"detail": {"code": "HAY_PAREJA_ELEGIBLE"}}           (override refused: an eligible pair is connected)
→ 200 {"id": "…", "estado": "ASIGNADO", "sesion_id": "…"}

POST /api/motored/conteos/{id}/cerrar
{"forzar": false, "motivo": null}
→ 409 {"detail": {"code": "RECONTEOS_ABIERTOS", "asignados": 4}}
→ 200 {"estado": "CERRADO", "kpi": {"refs_universo": 3990, "refs_exactas": 3712, "exactitud_pct": "93.03",
        "valor_sistema": "812345678.00", "valor_diferencia_neta": "-1234500.00", "valor_diferencia_abs": "4567800.00"}}

GET /api/motored/conteos/{id}/panel?version=88123
→ 200 {"sin_cambios": true, "version": 88123}
→ 200 {"version": 88140, "estado": "EN_CONTEO",
       "progreso": {"refs_snapshot": 3987, "refs_snapshot_contadas": 2101, "refs_fuera_snapshot": 14,
                    "unidades_contadas": "18233", "pct_refs": "52.70"},
       "ubicaciones": [{"id": "…", "nombre": "Estante A3", "lecturas": 211, "ultima_lectura_en": "…"}],
       "sesiones": [ … as /sesiones … ],
       "criticas": [{"codigo": "…", "nombre": "…", "sistema": "12", "contado": "2", "diferencia": "-10",
                     "valor": "-640000.00", "parcial": true, "ubicaciones": ["Estante A3"]}],
       "candidatas_reconteo": 37, "valor_diferencia_parcial": "-2310000.00"}
```

### 6.2 Public pair API (`api/publico_conteos.py`, prefix `/api/motored/publico/conteos`)

Router: `dependencies=[Depends(require_motored_ready)]`, `route_class=RutaPublica` (no-store, noindex). No `get_current_motored_user`. After joining, every call carries `X-Conteo-Sesion: <token>`, resolved by a dependency `sesion_de_pareja` (sha256 lookup, session CONECTADA, conteo EN_CONTEO or EN_RECONTEO), which also throttles `ultima_actividad_en` writes (only when older than 20 s).

| Method and path | Purpose | Limits |
|---|---|---|
| POST `/{slug}/unirse` | join with code + members | slowapi `10/minute`; DB counters (section 8.2) |
| GET `/sesion` | state: conteo estado, store name, current location, assigned reconteo tasks | |
| GET `/catalogo` | `[[code, name], ...]` of all referencias, ETag | `If-None-Match` -> 304 |
| GET `/ubicaciones` | the store's active locations (name, code) | |
| PUT `/ubicacion` | set current location by `codigo` (scanned `UBI-…`) or create one by `nombre` | |
| POST `/lecturas` | batch of up to 100 readings | `120/minute` per IP |
| POST `/lecturas/{id}/anular` | void own reading (open round only) | |
| GET `/lecturas/recientes?limite=20` | own last readings (code, name, qty, location) | |
| POST `/reconteos/{rid}/terminar` | finish an assigned reconteo | |
| POST `/salir` | leave (DESCONECTADA) | |

```http
POST /api/motored/publico/conteos/K7Q2M9XH4P/unirse
{"codigo": "482913", "autoriza_datos": true, "dispositivo": "MOVIL",
 "integrantes": [{"nombre": "Ana Ruiz", "cedula": "1.130.124.821"}, {"nombre": "Luis Gil", "cedula": "79123193"}]}
→ 401 {"detail": {"code": "ACCESO_INVALIDO"}}       (wrong slug, wrong code, closed conteo: same answer)
→ 429 {"detail": {"code": "DEMASIADOS_INTENTOS"}}
→ 201 {"sesion_token": "…43 chars…", "sesion_id": "…", "sucursal": "Tienda Centro",
       "estado_conteo": "EN_CONTEO"}

POST /api/motored/publico/conteos/lecturas         (X-Conteo-Sesion)
{"lecturas": [{"id": "0c6f…", "codigo": " abc-123 ", "cantidad": "1", "ubicacion_id": "…",
               "metodo": "ESCANER", "leida_en": "…", "reconteo_id": null}]}
→ 200 {"aceptadas": ["0c6f…"], "duplicadas": [],
       "rechazadas": [{"id": "…", "motivo": "CODIGO_DESCONOCIDO|RONDA_CERRADA|RECONTEO_NO_ASIGNADO|UBICACION_INVALIDA|CANTIDAD_INVALIDA"}],
       "referencias": {"ABC-123": "Pastilla freno delantera"},
       "sesion": {"estado": "CONECTADA", "estado_conteo": "EN_CONTEO", "reconteos": [ … ]}}
```

Unknown codes: the device asks "¿Registrar igual?"; a confirmed one is sent with `"forzar_desconocido": true` and stored with `referencia_id = NULL`. The leader sees them under "Códigos sin maestro".

Reconteo tasks returned to the assigned session: `{"id", "codigo", "nombre", "ubicaciones": ["Estante A3", "Bodega 2"]}`. Never a quantity.

### 6.3 Lore Mini App API (`api/miniapp_conteos.py`, prefix `/api/motored/miniapp/conteos`, stage 3)

Same public router pattern, plus a dependency that returns 503 when `LORE_BOT_TOKEN` is empty.

| Method and path | Purpose |
|---|---|
| POST `/sesion` | exchange `init_data` (+ optional `cedula`) for an asesor session token |
| GET `/hoy` | today's SELECTIVO conteos of the asesor's stores (`usuario_sucursal`) |
| POST `/{conteo_id}/abrir` | first opener freezes the snapshot; returns the items (code, name, last known locations), never quantities |
| POST `/{conteo_id}/lecturas` | same contract as 6.2 |
| POST `/{conteo_id}/terminar` | asesor finished their part |

```http
POST /api/motored/miniapp/conteos/sesion
{"init_data": "query_id=…&user=%7B%22id%22%3A…%7D&auth_date=…&signature=…&hash=…", "cedula": null}
→ 401 {"detail": {"code": "INIT_DATA_INVALIDO"}}
→ 403 {"detail": {"code": "NO_REGISTRADO"}}            (no active approved asesor with that telegram_id)
→ 409 {"detail": {"code": "CEDULA_REQUERIDA"}}         (shared Telegram, more than one candidate)
→ 200 {"sesion_token": "…", "asesor": {"nombre": "…"}, "sucursales": [{"id": "…", "nombre": "…"}]}
```

Verification: reuse the generic `verify_telegram_initdata` (`core/security.py:57-85`) with `LORE_BOT_TOKEN` and `max_age_seconds=3600`, imported under a local alias (same precedent as `verify_shared_secret` in `deps_bot.py:92-101`). It builds the data-check-string from every field except `hash`, sorted, joined by `\n`; secret key = `HMAC_SHA256(key="WebAppData", msg=bot_token)`; compares with `compare_digest`; rejects stale `auth_date`. Only `user.id` from the VERIFIED payload is used; `initDataUnsafe` is never trusted. Candidates come from `listar_usuarios_por_telegram` (`deps_bot.py:159-171`) filtered to active, approved `ASESOR_MOSTRADOR` (and ADMIN for testing). With several candidates, the typed cédula must equal one candidate's approved cédula; failures count in `miniapp_cedula_intento` (5 per 15 min). The resulting session is a `conteo_sesion` per conteo opened, tipo `ASESOR`, with the usuario's cédula as its single `conteo_integrante`.

### 6.4 Lore pieces (stage 3)

- `avisos_telegram.enviar_mensaje(..., reply_markup=None)`: optional dict, backward compatible.
- Morning message (supervisor) to each distinct `telegram_id` of the store's asesores: "Hoy toca conteo selectivo: N referencias." with `{"inline_keyboard": [[{"text": "Abrir conteo", "web_app": {"url": "<MOTORED_PUBLIC_URL>/motored/lore/conteo"}}]]}`. Inline `web_app` buttons work only in private chats, which is how asesores talk to Lore. One message per Telegram account, even when shared.
- `lore-bot/lore/handlers/conteo.py`: `/conteo` replies with the same button (static URL from lore config; auth happens in the Mini App through initData, so the bot needs no backend call).

---

## 7. Counting rules

1. **Blind count.** Pair and Mini App response models contain no `existencia`, `sistema`, `diferencia`, `costo` or `valor` fields. A test walks the OpenAPI schemas of `/publico/conteos/*` and `/miniapp/conteos/*` and fails if any such field appears.
2. **Normalization.** `codigo.strip().upper()`, matched against `upper(trim(referencia.codigo))` over all referencias. A scan starting with `UBI-` is a location change, not a reading.
3. **Location first.** A reading without a current location is rejected client-side and server-side (`UBICACION_INVALIDA`).
4. **Quantities.** Default +1 per scan; the last reading's quantity is editable (sent as a new reading plus a void of the old one, so the log stays append-only); manual entry = code + quantity.
5. **Summing.** Counted per referencia = Σ non-voided readings of the effective round across ALL locations. System per referencia = Σ snapshot lines across bodegas.
6. **Valuation.** Value difference per referencia = Σ over bodegas of (counted_b - system_b) × frozen cost_b. Counted units are attributed to the location's bodega. Surplus items with no snapshot line take the fallback cost chain (4.10) resolved at close.
7. **Reconteo trigger** (at end of round 1): abs(value difference) > `umbral_reconteo_pesos`, or quantity difference != 0 with `SIN_COSTO`. Plus manual ones.
8. **Critical**: abs(value difference) > `umbral_critico_pesos`. Shown red at the top. During EN_CONTEO it is flagged `parcial` (other locations may still be pending); after round 1 it is definitive.
9. **Accuracy KPI** (at close, per store):
   - universe = referencias with system != 0 or counted > 0 (unknown codes count as referencias);
   - `exactitud_pct` = 100 × exact / universe, where exact means final difference = 0;
   - `valor_diferencia_neta` = Σ value; `valor_diferencia_abs` = Σ |value|;
   - `valor_sistema` = Σ existencia × cost over lines with existencia > 0, which allows "difference as % of stock value";
   - selective KPI uses confirmed differences only.
10. **Selective list** (stage 3, weekly per store):
    - always included: a non-zero difference in the store's last closed count of that referencia; negative system stock; sold in the last 7 days while the latest snapshot stock <= 0;
    - then due referencias by class frequency (A 30, B 90, C 180 days since last count), ordered by class, then sales value, then oldest count;
    - capped at `conteo_selectivo_tamano` (default 40). See risk R3 for overflow.
11. **ABC**: per physical store, Σ(valor_bruto - valor_descuentos) from `venta_detalle` in the window, cargas not ANULADO, positive totals only, cumulative share cut at 80 / 95 (A/B/C = 80/15/5).

---

## 8. Security

### 8.1 Token entropy
- Pair link slug: 10 chars from a 32-symbol unambiguous alphabet (`secrets.choice`, same approach as `services/vinculacion.py:83`) = 50 bits. Not sufficient alone: the code is also required.
- Code: 6 digits from `secrets.randbelow(10**6)`, stored as `HMAC-SHA256(MOTORED_SECRET_KEY, conteo_id + ":" + code)`. Comparison with `hmac.compare_digest`.
- Device and Mini App session tokens: `secrets.token_urlsafe(32)` (256 bits), stored as sha256; sent in a header, never in a URL, never logged.

### 8.2 Brute-force limits on the short code
- slowapi `10/minute` per IP on `/unirse` (`core/limiter.py`). Note: uvicorn runs with `--forwarded-allow-ips='*'` (`scripts/start.sh:25`), so the IP comes from forwarded headers and may be client-influenced. IP limits are a first filter only.
- DB per (conteo, sha256(IP)): 5 failures in 15 min -> 15-min lock (`conteo_acceso_intento`), committed before answering 401, with `SELECT ... FOR UPDATE` like `informe_publico.py:88-120`.
- DB global per conteo: 30 failures per hour -> automatic code rotation, flag shown to the leader ("Se cambió el código por intentos fallidos"). Connected pairs are unaffected.
- Bound: at most ~30 guesses per hour against 10^6 codes, on top of a 50-bit slug. Over a 10-hour count, the success odds stay below 0.03 % even with the slug known.
- One generic error (`ACCESO_INVALIDO`) for wrong slug, wrong code and closed conteo: no oracle.

### 8.3 Cédulas (Ley 1581)
- Normalized with `limpiar_cedula`; stored in `conteo_integrante.cedula` for traceability; used only server-side (different-pair rule).
- Never returned by any endpoint. Leader views show `****` + last 4 (same masking as `reporte_asesor_envio.py:757-758`). Never logged; never in the ERP Excel.
- The join form requires `autoriza_datos: true` with a short purpose notice (precedent: `encuesta_publica.py:80`).
- Retention: kept with the conteo history; a purge policy is a later decision (risk R7).

### 8.4 Telegram initData
Section 6.3. Additionally: Mini App sessions are bound to one usuario and one conteo, and expire at the conteo's close.

### 8.5 Path rules for the new role
- `deps.py`: `LIDER_INVENTARIOS_ROLE = "LIDER_INVENTARIOS"`, `LIDER_INVENTARIOS_ALLOWED_PREFIXES = ("/api/motored/auth", "/api/motored/conteos")`, added to `_CONFINED_ROLE_PREFIXES`. It is an allow-list, so every other endpoint is denied by default.
- GERENCIA: add `"/api/motored/conteos"` to its tuple in `_CONFINED_ROLE_PREFIXES`; writes stay blocked by `require_roles`.
- Configuración remains ADMIN-only (thresholds and selective rules).

### 8.6 Public routes outside `get_current_motored_user`
`/api/motored/publico/conteos/*` and `/api/motored/miniapp/conteos/*` never use the JWT dependency. Path confinement therefore does not apply to them, and each one authenticates through its own dependency (`sesion_de_pareja`, `sesion_de_asesor`). Every response is `no-store` and `noindex`. The frontend pages set `robots: {index: false}` and are not wrapped in `MotoredLayout`. No cookies are used, so there is no CSRF surface.

---

## 9. Performance

### 9.1 Expected volumes
- Snapshot: the INVENTARIO file had ~56k rows across all stores (`inventario.py:37-42`), so a store holds roughly 2k-8k (referencia, bodega) lines.
- Readings: +1 per scan; a store with 20k units yields up to ~20k readings (fewer with quantity entry). Several stores at once: up to ~100k readings per day.
- Concurrency: up to ~6 stores × 2-6 pairs = ~36 devices.

### 9.2 Request load
- Pairs flush batches about every 1.5 s while scanning: ≤ ~25 req/s peak, each a single multi-row INSERT (~5-15 ms).
- Heartbeat: one `GET /sesion` every 30 s per device.
- The pool is 5 + 10 (`database.py:37-41`). The estimated average busy connections stay below 1. Batching is mandatory to keep it there (ADR-5).

### 9.3 Live panel query plan
```sql
WITH contado AS (
  SELECT referencia_id, codigo_leido, sum(cantidad) AS c
  FROM conteo_lectura
  WHERE conteo_id = :c AND ronda = 1 AND anulada_en IS NULL      -- ix_conteo_lectura_agregado
  GROUP BY referencia_id, codigo_leido),
sistema AS (
  SELECT referencia_id, sum(existencia) AS s, sum(existencia * coalesce(costo_unitario, 0)) AS v
  FROM conteo_snapshot_linea WHERE conteo_id = :c                -- uq (conteo_id, referencia_id, bodega)
  GROUP BY referencia_id)
SELECT … FROM sistema FULL JOIN contado USING (referencia_id)
ORDER BY abs(valor) DESC LIMIT 20;
```
Two index range scans and hash aggregates over ≤ 20k rows each: tens of milliseconds. The version check (`SELECT max(seq) FROM conteo_lectura WHERE conteo_id = :c`) is index-only on `ix_conteo_lectura_conteo_seq`. Counts per location and per session use their own indexes. The panel returns aggregates and the top 20 only; the full differences table is paged (`/diferencias`).

### 9.4 Polling vs SSE
Recommendation: polling.
- There is no SSE or WebSocket in Motored today, and polling is the established pattern (`CargaDetalle.js:5-11`).
- SSE would still need server-side change detection (DB polling per stream, or new Redis pub/sub wiring), would hold long-lived connections through Traefik and a single uvicorn process, and adds reconnect handling. The benefit at a 5 s freshness target is nil.
- Cost: leader panel 5 s while visible, 30 s hidden (`document.visibilityState`), paused when the conteo is closed. With ~6 leader/gerencia screens: ~1.2 req/s; most answers in steady state are the index-only short-circuit; during active counting a full aggregate every 5 s per screen costs ~0.06 busy connections.
- Given the past Postgres connection timeouts under KPI load: no endpoint here touches `venta_detalle` or KPI summaries; the ABC rebuild (stage 3) runs weekly in the loop, per store, outside opening hours.

### 9.5 Other
- The catalogue is computed once per process and cached for 10 minutes (in memory, keyed by `max(referencia.updated_at)`), served gzip with an ETag; devices keep it in localStorage.
- `ultima_actividad_en` writes are throttled (20 s) to avoid hot-row updates.
- No counter column on the `conteo` row is updated per reading (it would serialize every pair of a store on one row lock); `seq` replaces it.

---

## 10. Frontend

Constraints from project conventions: container-presentational split; every new `<select>` styles each `<option>` explicitly (dark theme); tooltips on non-obvious fields; tablet 768-1024 px must work and be verified with real screenshots; no backticks in `themeCss` comments.

### 10.1 Leader screens (`app/motored/conteos`, inside `MotoredLayout`)
- **List / schedule** (`/motored/conteos`): tabs "Totales" / "Selectivos" (stage 3); table by store with estado, fecha, exactitud; "Programar conteo" (store, date). Each store shows the age of its latest inventory carga.
- **Start** (`/motored/conteos/[id]`, PROGRAMADO): carga facts (file, fecha_corte, aplicado_en), staleness warning modal with explicit confirmation, "Iniciar conteo".
- **Access card** (after Iniciar): QR image (`qr.png`), copyable link, large code digits, "Cambiar código". The code is kept in `sessionStorage` per conteo; if missing: "Generar código nuevo".
- **Pairs table**: members (masked cédulas), device, current location, readings, last activity, Disconnect.
- **Reconteo control** (EN_RECONTEO): candidates with difference and value (leader only), assignment dropdown of eligible sessions, "Asignar automáticamente", same-pair override dialog (reason required), status chips.
- **Close**: summary + KPI preview; force-close dialog with reason; after close (stage 4) "Descargar ajuste (Excel)".
- **Live panel** (stage 2): progress bar, critical list pinned on top in red with a short sound on new criticals, per-location progress, pairs activity, `usePolling(version)` hook.
- GERENCIA sees the same pages with every action hidden; the backend enforces it.

### 10.2 Pair counting screen (`app/motored/c/[slug]/page.js`, public)
- **Join**: code, two members (name, cédula), consent checkbox. The session token goes to `localStorage` keyed by slug, so a reload resumes.
- **Location first**: a top bar with the current location. Scanning `UBI-…` or picking/creating one is required before the first reading. Changing location flushes the queue.
- **Desktop (USB scanner as keyboard)**: one always-focused input (refocus on blur, `autocomplete="off"`, `inputMode="none"` on desktop). Each scan ends with Enter, and Enter submits. A "Cantidad" field edits the last reading. Recent readings list with "Deshacer".
- **Mobile**: mobile-first layout with large buttons. Camera scanning via the `barcode-detector` package (a BarcodeDetector API ponyfill over zxing-wasm that uses the native detector where available, e.g. Android Chrome), loaded with dynamic `import()` only when the camera is opened, formats `code_128`, `code_39`, `ean_13`. Alternative: `@zxing/browser` (heavier, maintenance mode). `html5-qrcode` is not recommended (unmaintained). Bluetooth scanners behave like the desktop keyboard input. Manual entry always available. Package versions must be checked at implementation time.
- **Feedback**: Web Audio beeps (ok / unknown code / error), `navigator.vibrate` on mobile, color flash.
- **Offline queue**: readings in `localStorage` with client UUIDs; flush every 1.5 s or 20 readings; retry with backoff; a "N pendientes de enviar" badge.
- **Reconteo tasks**: a tab listing assigned codes with their locations and a "Terminé" button; round-2 readings are tagged with `reconteo_id`.
- **Disconnected**: on `401 SESION_INACTIVA`, clear the token and show "El líder cerró tu sesión".

### 10.3 Mini App screen (`app/motored/lore/conteo/page.js`, public, stage 3)
Loads `telegram-web-app.js` (pattern of `frontend/app/tg/page.js:6-27`), posts `initData`, asks the cédula when told `CEDULA_REQUERIDA`, lists today's items (code, name, last known locations) and reuses the counting components (camera + manual). Uses Telegram theme colors and `MainButton` "Terminar".

### 10.4 Configuración tab "Conteos de inventario"
Add `{ id: 'conteos', label: 'Conteos de inventario' }` to `secciones.js` and `"conteos"` to `SECCIONES` in `parametros_claves.py`. Keys (group `OPERACION`, section `conteos`):

| Key | Type | Default | Stage |
|---|---|---|---|
| `conteo_umbrales_pesos` | objeto_numerico {reconteo, critico}, reconteo < critico | {50000, 500000} (placeholders, owner to confirm) | 1 |
| `conteo_dias_max_antiguedad_inventario` | entero 0..30 | 1 | 1 |
| `conteo_selectivo_activo` | bool | false | 3 |
| `conteo_abc_cortes_pct` | objeto_numerico {a_hasta, b_hasta}, a < b, max 100 | {80, 95} | 3 |
| `conteo_frecuencia_dias` | objeto_numerico {A, B, C} | {30, 90, 180} | 3 |
| `conteo_selectivo_tamano` | entero 5..500 | 40 | 3 |
| `conteo_selectivo_dia` | opcion LUNES..DOMINGO | LUNES | 3 |
| `conteo_selectivo_hora_apertura` / `_hora_cierre` | hora | 08:00 / 18:00 | 3 |
| `conteo_abc_meses_ventas` | entero 1..24 | 6 | 3 |

Each field gets a tooltip.

### 10.5 Role wiring (frontend)
- `session.js`: `ROLE_LIDER_INVENTARIOS`, `CONTEOS_PATH`, `CONTEOS_ROLES = ['ADMIN','LIDER_INVENTARIOS','GERENCIA']`, `isLiderInventariosPath`, `homePathFor` -> `CONTEOS_PATH` for the leader.
- `motored-layout.js`: `VALID_ROLES` gains the role; `redireccionPara` confines it.
- `MotoredSidebar.js`: a group "Inventarios" with "Conteos de inventario"; `mi-cuenta` gains the role.
- `permisosPorRol.js`: role entry + pantalla `conteos`.
- `UsuarioCreateForm.js`: option + label. `inicio/textos.js`: label.

---

## 11. File changes

| File | Action | Stage |
|---|---|---|
| `backend/alembic_motored/versions/<rev>_lider_inventarios_role.py` | Create (enum value, `autocommit_block`) | 1 |
| `backend/alembic_motored/versions/<rev>_conteos_base.py` | Create (conteo, conteo_snapshot_linea, ubicacion_inventario) | 1 |
| `backend/alembic_motored/versions/<rev>_conteos_lecturas.py` | Create (sesion, integrante, lectura, reconteo, acceso_intento, resultado) | 1 |
| `backend/alembic_motored/versions/<rev>_conteos_selectivos.py` | Create (conteo_abc, conteo_item, miniapp_cedula_intento) | 3 |
| `backend/app/motored/models/usuario.py` | Modify (enum value) | 1 |
| `backend/app/motored/models/conteo.py`, `conteo_snapshot_linea.py`, `ubicacion_inventario.py`, `conteo_sesion.py`, `conteo_lectura.py`, `conteo_reconteo.py`, `conteo_resultado.py`, `conteo_acceso_intento.py` | Create | 1 |
| `backend/app/motored/models/__init__.py` | Modify (register models) | 1 |
| `backend/app/motored/deps.py` | Modify (allow-lists; stage 3: `supervisor_conteos.ensure_started()`) | 1, 3 |
| `backend/app/motored/services/parametros_claves.py` | Modify (section + keys) | 1, 3 |
| `backend/app/motored/services/conteos/*.py` | Create | 1-4 |
| `backend/app/motored/api/ruta_publica.py` | Create (shared `RutaPublica`); `api/publico_informe.py` Modify (import it) | 1 |
| `backend/app/motored/api/conteos.py`, `publico_conteos.py` | Create | 1 |
| `backend/app/motored/api/miniapp_conteos.py` | Create | 3 |
| `backend/app/motored/api/router.py` | Modify (include routers) | 1, 3 |
| `backend/app/motored/services/avisos_telegram.py` | Modify (`reply_markup`) | 3 |
| `backend/app/motored/services/trabajos/supervisor_conteos.py` | Create | 3 |
| `lore-bot/lore/handlers/conteo.py`, `lore-bot/lore/main.py` | Create / Modify | 3 |
| `frontend/lib/motored/session.js`, `permisosPorRol.js`, `app/motored/motored-layout.js`, `components/motored/MotoredSidebar.js`, `UsuarioCreateForm.js`, `inicio/textos.js` | Modify | 1 |
| `frontend/components/motored/configuracion/secciones.js` (+ `SeccionConteos.js`) | Modify / Create | 1 |
| `frontend/app/motored/conteos/**`, `components/motored/conteos/**`, `lib/motored/conteosApi.js` | Create | 1-4 |
| `frontend/app/motored/c/[slug]/page.js`, `components/motored/conteo-pareja/**`, `lib/motored/conteoParejaApi.js` | Create | 1 |
| `frontend/app/motored/lore/conteo/page.js`, `lib/motored/conteoMiniappApi.js` | Create | 3 |
| `frontend/package.json` | Modify (`barcode-detector`) | 1 (WU14) |
| `backend/requirements*.txt` | Modify if a Code128 library is chosen for labels (risk R5) | 2 |

---

## 12. Delivery plan

Each work unit (WU) is one feature-branch commit with tests and docs, about ≤ 400 authored changed lines (advisory). Python checks must also pass on 3.11 (production runtime; `docker python:3.11-slim`). Never commit with red tests.

### Stage 1: total count (scanner and manual, blind, locations, pairs, reconteo, close)

Migrations in order: **M1** `lider_inventarios_role` (down_revision `d7a3c5e91f20`) -> **M2** `conteos_base` -> **M3** `conteos_lecturas`.

| WU | Scope | Tests |
|---|---|---|
| WU1 | Role `LIDER_INVENTARIOS`: M1, `MotoredRole`, `deps.py` allow-lists (leader + GERENCIA prefix), frontend wiring (10.5). | unit: confinement like `test_coordinador_repuestos_role.py`; pg_real: enum value usable; jest: roles matrix drift test, sidebar, layout redirect, user form |
| WU2 | M2 + models `conteo`, `conteo_snapshot_linea`, `ubicacion_inventario`. | pg_real: upgrade/downgrade, `uq_conteo_total_abierto`, CHECKs |
| WU3 | M3 + models for sessions, members, readings, reconteo, attempts, results. | pg_real: identity `seq`, reading CHECKs, reconteo partial unique, cascades |
| WU4 | Configuración: section `conteos`, stage-1 keys, `SeccionConteos` with tooltips. | unit: registry validation (`reconteo < critico`); jest: tab renders and saves |
| WU5 | `services/conteos/snapshot.py`: schedule, Iniciar (single-statement copy, cost fallback, staleness), annul; slug/code generation in `acceso.py`. | pg_real: per-store latest carga, ANULADO skipped, later same-date reload leaves the snapshot intact, two stores started at different times, cost fallback order; unit: staleness verdict |
| WU6 | Leader API part 1: `/sucursales`, list, create, reschedule, detail, iniciar, `qr.png`, rotate code; `RutaPublica` extraction; router wiring. | unit API with dependency overrides: RBAC (GERENCIA read-only, leader confined), 409 codes |
| WU7 | Pair access: `/unirse`, attempt counters + auto-rotation, `sesion_de_pareja` dependency, `/sesion`, `/salir`; leader `/sesiones` + disconnect. | unit: generic 401, lock after 5, global cap rotates the code, rotation keeps sessions, disconnected -> 401; pg_real: `FOR UPDATE` counter commit |
| WU8 | Readings: `/catalogo` (ETag), `/ubicaciones`, `PUT /ubicacion`, `POST /lecturas` (idempotent, ≤100), void, recent. | unit: OpenAPI blind-count guard, normalization, `UBI-` routing, unknown codes; pg_real: `ON CONFLICT DO NOTHING` duplicates |
| WU9 | Reconteo: terminar-ronda, differences, threshold candidates, manual add, assignment with disjoint-cédula rule + override, auto-assign, pair tasks, terminar. | pg_real: same people on a new device rejected, override only without eligible sessions, round-2 readings only from the assignee, disconnection frees tasks |
| WU10 | Close: guards, force, `conteo_resultado` materialization (final quantity rule, bodega attribution, cost fallback), KPI. | pg_real: KPI on a known fixture, surplus without snapshot line, SIN_COSTO, multi-bodega attribution |
| WU11 | Leader UI: list, schedule, start with staleness modal, access card (QR, link, code). | jest |
| WU12 | Leader UI: pairs table, reconteo control, close dialog. | jest |
| WU13 | Pair UI part 1: public route, join + consent, session persistence, location bar, desktop scanner input, manual entry, offline queue, sounds. | jest (simulated keyboard bursts + Enter, queue flush/retry, 401 handling) |
| WU14 | Pair UI part 2: mobile layout, camera scanning (dynamic import), vibration, reconteo tasks tab. | jest with a mocked detector; manual check on Android and iPhone; tablet screenshots |

### Stage 2: live panel
WU15 `/panel` with the version short-circuit + critical list; WU16 `usePolling` + panel UI (progress, criticals, locations, pairs, sound); WU17 location master screen + label PDF (Code128). Tests: pg_real aggregate correctness and `sin_cambios`; jest polling/visibility.

### Stage 3: automatic selective counts
M4 `conteos_selectivos`. WU18 stage-3 config keys; WU19 `abc.py` (pg_real on `venta_detalle`); WU20 `selectivo.py` list generation (always-included, due rules, cap) + carry-over + verification; WU21 `supervisor_conteos.py` (weekly generation, morning message, close hour; advisory lock `7_203_581_301`; switch); WU22 Mini App API (initData, cédula prompt, attempts); WU23 Mini App page; WU24 `reply_markup` + Lore `/conteo` handler (lore-bot tests); WU25 leader "Selectivos" tab with confirmed differences.

### Stage 4: ERP adjustment list and accuracy history
WU26 `excel_ajuste.py` + `/ajuste.xlsx` (sheets: Resumen, Ajustes with diferencia != 0 using the owner's columns, Sin maestro; codes as text cells); WU27 `/kpi` history endpoint + accuracy page (per store, trend, store comparison). Tests: unit workbook content (openpyxl read-back), jest.

---

## 13. Testing strategy

| Layer | What | Approach |
|---|---|---|
| Unit (pytest) | registry keys, staleness verdict, code normalization, token/HMAC helpers, initData verification (known vector), different-pair rule (pure function), Excel content | pure functions; FastAPI dependency overrides for RBAC and public auth |
| pg_real | snapshot SQL, partial unique indexes, identity `seq`, `ON CONFLICT`, aggregates, KPI, ABC window queries, `FOR UPDATE` counters | the existing `backend/tests/motored/pg_real` harness (PostgreSQL-specific SQL cannot run on session doubles) |
| jest | role wiring, Configuración tab, leader screens, pair screen (scanner input, queue, sounds mocked), Mini App bootstrap (mocked `Telegram.WebApp`) | Testing Library |
| Manual | camera scanning on Android/iPhone, USB scanner on Windows laptops, Telegram Mini App on both OSes, tablet layouts | screenshots in the feature document |

RED first for every behavior with a deterministic runner. Threat matrix: N/A (no routing, shell, subprocess, VCS automation or process-integration boundary is added; the security surface is covered by section 8).

---

## 14. Open technical risks and owner decisions

Risks:
- **R1 Multi-bodega stores.** Counted units are attributed to a bodega through the location (default: the principal bodega). If a store has stock in two bodegas but no location carries the second one, the Excel shows a surplus in one bodega and a shortage in the other while the store-level comparison matches.
- **R2 Mini App camera.** 1D barcode scanning inside Telegram's iOS webview is not verified. Telegram's own `showScanQrPopup` reads QR codes only. Manual entry is the guaranteed fallback.
- **R3 Selective list rules not fully defined.** The overflow rule, the meaning of "repeats" and the ABC sales window are proposals (owner decision 3).
- **R4 Snapshot freshness is procedural.** The count is only as good as the latest INVENTARIO upload; the staleness warning is the safeguard.
- **R5 Label printing needs a Code128 encoder.** Cheap USB scanners are often 1D-only, so QR labels are not enough. This means a new dependency (`python-barcode`, or `jsbarcode` in the frontend), decided in stage 2.
- **R6 Rate limiting by IP is weak** behind `--forwarded-allow-ips='*'`. The DB per-conteo caps are the real bound.
- **R7 Cédula retention.** No purge policy yet.

Owner decisions needed:
1. Default money thresholds for reconteo and critical (placeholders: $50.000 / $500.000).
2. R1: whether any store physically holds two bodegas, so that locations must be tagged with a bodega.
3. R3, selective details:
   - when always-included items exceed the list size, fill first and carry the rest over (proposed), or grow the list?
   - is "repeats" = same-sign non-zero difference (proposed)?
   - is the ABC sales window 6 months (proposed)?
4. Can a LÍDER DE INVENTARIOS act on every store, or only on assigned stores (`usuario_sucursal`)? Proposed: every store.
