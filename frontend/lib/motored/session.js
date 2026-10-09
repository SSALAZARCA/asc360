/**
 * Motored session helpers shared by login, layout, sidebar and mi-cuenta:
 * where each role lands, the forced-change flag and storing a fresh session.
 */
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from './motoredFetch';

export const MI_CUENTA_PATH = '/motored/mi-cuenta';
export const PASSWORD_CHANGE_REQUIRED_CODE = 'PASSWORD_CHANGE_REQUIRED';

export const ROLE_GERENCIA = 'GERENCIA';

/** Parts coordinator: KPI's, the "Gestión repuestos" section and, as a count
 * leader (owner decision 2026-10-09), the "Inventarios" pages. */
export const COORDINADOR_REPUESTOS = 'COORDINADOR_REPUESTOS';

/** KPI's page: the home of COORDINADOR_REPUESTOS. */
export const KPIS_PATH = '/motored/tablero-asesores';

/** "Gestión repuestos" section: pages and the roles that may open them. */
export const GESTION_REPUESTOS_PATH = '/motored/gestion-repuestos';
export const INGRESOS_FACTURAS_PATH = '/motored/gestion-repuestos/ingresos-facturas';
export const TRASLADOS_PATH = '/motored/gestion-repuestos/traslados';

/** Administrative analyst: the "Gestión repuestos" section only (no KPI's). */
export const ANALISTA_ADMINISTRATIVO = 'ANALISTA_ADMINISTRATIVO';
export const GESTION_REPUESTOS_ROLES = ['ADMIN', 'COMPRAS', 'GERENCIA', COORDINADOR_REPUESTOS, ANALISTA_ADMINISTRATIVO];

// Pages an ANALISTA_ADMINISTRATIVO may open (UX only; the backend allow-list
// is the real enforcement).
const ANALISTA_ADMINISTRATIVO_PATHS = [GESTION_REPUESTOS_PATH, MI_CUENTA_PATH];

export function isAnalistaAdministrativoPath(pathname) {
  return ANALISTA_ADMINISTRATIVO_PATHS.some((p) => pathname === p || pathname?.startsWith(`${p}/`));
}

/** "Inventarios" section: its pages and the roles that may open Conteos. */
export const INVENTARIOS_PATH = '/motored/inventarios';
export const CONTEOS_PATH = '/motored/inventarios/conteos';

// Pages a COORDINADOR_REPUESTOS may open (UX only; the backend confinement
// `deps._CONFINED_ROLE_PREFIXES` is the real enforcement). It also leads
// inventory counts, so it opens the "Inventarios" pages.
const COORDINADOR_REPUESTOS_PATHS = [KPIS_PATH, GESTION_REPUESTOS_PATH, INVENTARIOS_PATH, MI_CUENTA_PATH];

export function isCoordinadorRepuestosPath(pathname) {
  return COORDINADOR_REPUESTOS_PATHS.some((p) => pathname === p || pathname?.startsWith(`${p}/`));
}

/** Inventory-count leader: the "Conteos de inventario" module only. */
export const LIDER_INVENTARIOS = 'LIDER_INVENTARIOS';

/** Roles that lead a count (owner decision 2026-10-09: the parts coordinator
 * leads too, with exactly the LIDER_INVENTARIOS powers). */
export const ROLES_LIDER_CONTEO = [LIDER_INVENTARIOS, COORDINADOR_REPUESTOS];

export const CONTEOS_ROLES = ['ADMIN', ...ROLES_LIDER_CONTEO, ROLE_GERENCIA];

// Owner rule: while stage 1 is being built, the sidebar group "Inventarios"
// shows to ADMIN only, so nothing half-built is exposed. It widens to
// CONTEOS_ROLES (ADMIN, LIDER_INVENTARIOS, COORDINADOR_REPUESTOS and GERENCIA)
// when the owner finishes testing; COORDINADOR_REPUESTOS joins it then.
export const CONTEOS_ROLES_VISIBLES = ['ADMIN'];

// Pages a LIDER_INVENTARIOS may open (UX only; the backend allow-list
// `deps.LIDER_INVENTARIOS_ALLOWED_PREFIXES` is the real enforcement).
const LIDER_INVENTARIOS_PATHS = [INVENTARIOS_PATH, MI_CUENTA_PATH];

export function isLiderInventariosPath(pathname) {
  return LIDER_INVENTARIOS_PATHS.some((p) => pathname === p || pathname?.startsWith(`${p}/`));
}

/** Welcome page: the home of every role with screens. */
export const INICIO_PATH = '/motored/inicio';

/**
 * Roles with no screens yet (owner decision 2026-10-05): they only reach the
 * account page, which shows them this notice. The backend answers 403 on
 * every other Motored endpoint (`deps.ROLES_SIN_ACCESO`).
 */
export const ROLES_SIN_ACCESO = ['SUCURSAL', 'CONSULTA'];
export const ACCESO_NO_HABILITADO_NOTICE = 'Tu acceso todavía no está habilitado';

export function rolSinAcceso(role) {
  return ROLES_SIN_ACCESO.includes(role);
}

/** Home page of a role (where it lands after login, after the forced change
 * and when a page gate turns it away): the account page for a role without
 * screens, KPI's for COORDINADOR_REPUESTOS, Conteos for LIDER_INVENTARIOS,
 * Ingresos facturas for ANALISTA_ADMINISTRATIVO,
 * Inicio for everyone else (ADMIN,
 * COMPRAS, GERENCIA and SERVICIO_CLIENTE; a missing or unknown role is then
 * sent to login by the layout). */
export function homePathFor(role) {
  if (rolSinAcceso(role)) return MI_CUENTA_PATH;
  if (role === LIDER_INVENTARIOS) return CONTEOS_PATH;
  if (role === ANALISTA_ADMINISTRATIVO) return INGRESOS_FACTURAS_PATH;
  return role === COORDINADOR_REPUESTOS ? KPIS_PATH : INICIO_PATH;
}

/** Where a fresh session must go: the account page while a password change is pending. */
export function landingPathFor(user) {
  return user?.must_change_password ? MI_CUENTA_PATH : homePathFor(user?.role);
}

export function storeSession(data) {
  sessionStorage.setItem(MOTORED_TOKEN_KEY, data.access_token);
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify(data.user));
  window.dispatchEvent(new Event('storage'));
}
