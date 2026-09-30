/** Spanish labels and pure formatters for the login log screen. */
export const RESULTADO_LABELS = { EXITO: 'Éxito', FALLO: 'Fallido', BLOQUEADO: 'Bloqueado' };

export const MOTIVO_LABELS = {
  CREDENCIALES: 'Contraseña o correo incorrectos',
  INACTIVO: 'Usuario inactivo',
  PENDIENTE: 'Cuenta pendiente de aprobación',
  CUENTA_BLOQUEADA: 'Cuenta bloqueada',
};

const BOGOTA = 'America/Bogota';

/** Colombia date and time, 24h ("30/9/2026, 15:15:00"). */
export function formatFechaHoraCo(iso) {
  return iso ? new Date(iso).toLocaleString('es-CO', { timeZone: BOGOTA, hour12: false }) : '—';
}

/** Colombia time "HH:MM". */
export function formatHoraCo(iso) {
  return new Date(iso).toLocaleTimeString('es-CO', { timeZone: BOGOTA, hour12: false, hour: '2-digit', minute: '2-digit' });
}

// Order matters: Edge and Opera also say Chrome; Chrome also says Safari.
const BROWSERS = [[/Edg\//, 'Edge'], [/OPR\//, 'Opera'], [/Firefox\//, 'Firefox'], [/Chrome\//, 'Chrome'], [/Safari\//, 'Safari'], [/curl\//, 'curl']];

/** Short browser name from a user agent; "Otro" when unknown, "—" when absent. */
export function browserName(userAgent) {
  if (!userAgent) return '—';
  const found = BROWSERS.find(([pattern]) => pattern.test(userAgent));
  return found ? found[1] : 'Otro';
}
