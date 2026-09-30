/**
 * Front-end constants for the SERVICIO_CLIENTE role (survey module).
 * UX only: the backend (`deps.SERVICIO_CLIENTE_ALLOWED_PREFIXES`) is the
 * real enforcement and answers 403 outside the survey routes.
 */
export const ROLE_SERVICIO_CLIENTE = 'SERVICIO_CLIENTE';
export const SURVEY_ADMIN_PATH = '/motored/encuesta-satisfaccion';

// Pages a SERVICIO_CLIENTE may open (detractors panel lands in the next slice).
const SERVICIO_CLIENTE_PATHS = [SURVEY_ADMIN_PATH, '/motored/detractores'];

export function isServicioClientePath(pathname) {
  return SERVICIO_CLIENTE_PATHS.some((p) => pathname === p || pathname?.startsWith(`${p}/`));
}
