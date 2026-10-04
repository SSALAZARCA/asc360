/**
 * Motored session helpers shared by login, layout, sidebar and mi-cuenta:
 * where each role lands, the forced-change flag and storing a fresh session.
 */
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from './motoredFetch';
import { ROLE_SERVICIO_CLIENTE, SURVEY_ADMIN_PATH } from './servicioCliente';

export const MI_CUENTA_PATH = '/motored/mi-cuenta';
export const PASSWORD_CHANGE_REQUIRED_CODE = 'PASSWORD_CHANGE_REQUIRED';

/** Home page of a role (where it lands after login or after the forced change). */
export const ROLE_GERENCIA = 'GERENCIA';
export const GERENCIA_HOME_PATH = '/motored/tablero-asesores';

export function homePathFor(role) {
  if (role === ROLE_SERVICIO_CLIENTE) return SURVEY_ADMIN_PATH;
  if (role === ROLE_GERENCIA) return GERENCIA_HOME_PATH;
  return '/motored/maestros';
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
