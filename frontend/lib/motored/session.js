/**
 * Motored session helpers shared by login, layout, sidebar and mi-cuenta:
 * where each role lands, the forced-change flag and storing a fresh session.
 */
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from './motoredFetch';

export const MI_CUENTA_PATH = '/motored/mi-cuenta';
export const PASSWORD_CHANGE_REQUIRED_CODE = 'PASSWORD_CHANGE_REQUIRED';

export const ROLE_GERENCIA = 'GERENCIA';

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
 * screens, Inicio for everyone else (ADMIN, COMPRAS, GERENCIA and
 * SERVICIO_CLIENTE; a missing or unknown role is then sent to login by the
 * layout). */
export function homePathFor(role) {
  return rolSinAcceso(role) ? MI_CUENTA_PATH : INICIO_PATH;
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
