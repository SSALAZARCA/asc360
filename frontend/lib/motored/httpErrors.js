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
  return fallback;
}
