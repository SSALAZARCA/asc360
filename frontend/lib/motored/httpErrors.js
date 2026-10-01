/**
 * Friendly Spanish messages for Motored HTTP failures. The backend is not
 * uniform: slowapi answers 429 with `{"error": ...}`, the unavailable guard
 * answers 503 with an object `detail`. Never surface an object to the UI.
 */
export const RATE_LIMIT_MESSAGE = 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.';
export const UNAVAILABLE_MESSAGE = 'El servicio no está disponible en este momento. Inténtalo más tarde.';
export const NETWORK_MESSAGE = 'No pudimos conectarnos. Revisa tu conexión.';

const UNAVAILABLE_STATUSES = [502, 503, 504];

/** Message for a failed response: status-specific first, then a string detail, then `fallback`. */
export function httpErrorMessage(status, body, fallback) {
  const detail = body && body.detail;
  // slowapi's 429 has no `detail`; the account/cedula lockouts do, and say more.
  if (status === 429) return typeof detail === 'string' && detail ? detail : RATE_LIMIT_MESSAGE;
  if (UNAVAILABLE_STATUSES.includes(status)) return UNAVAILABLE_MESSAGE;
  if (typeof detail === 'string' && detail) return detail;
  // Coded business errors (Fase 4): `detail: { code, message, detalle? }`.
  if (detail && typeof detail === 'object' && typeof detail.message === 'string' && detail.message) {
    return detail.message;
  }
  return fallback;
}

/**
 * An `Error` for a failed response: the Spanish message plus `status` and,
 * for a coded body (`detail: { code, message, detalle? }`), `code` and
 * `detalle`, so a screen can branch on the rule that rejected the action.
 */
export function codedError(status, body, fallback) {
  const error = new Error(httpErrorMessage(status, body, fallback));
  error.status = status;
  const detail = body && body.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    if (detail.code !== undefined) error.code = detail.code;
    if (detail.detalle !== undefined) error.detalle = detail.detalle;
  }
  return error;
}

/** The message of `error`, followed by its code in parentheses when it has one. */
export function mensajeConCodigo(error, fallback = 'No se pudo completar la acción.') {
  const message = (error && error.message) || fallback;
  return error && error.code ? `${message} (${error.code})` : message;
}
