/** Spanish labels and pure formatters for the login log screen. */
import { fechaHoraBogota, horaBogota } from '../../../lib/motored/fechas';

export const RESULTADO_LABELS = { EXITO: 'Éxito', FALLO: 'Fallido', BLOQUEADO: 'Bloqueado' };

export const MOTIVO_LABELS = {
  CREDENCIALES: 'Contraseña o correo incorrectos',
  INACTIVO: 'Usuario inactivo',
  PENDIENTE: 'Cuenta pendiente de aprobación',
  CUENTA_BLOQUEADA: 'Cuenta bloqueada',
};

/** Colombia date and time, 24h ("30/09/2026 15:15"). */
export const formatFechaHoraCo = fechaHoraBogota;

/** Colombia time "HH:MM". */
export const formatHoraCo = horaBogota;

// Order matters: Edge and Opera also say Chrome; Chrome also says Safari.
const BROWSERS = [[/Edg\//, 'Edge'], [/OPR\//, 'Opera'], [/Firefox\//, 'Firefox'], [/Chrome\//, 'Chrome'], [/Safari\//, 'Safari'], [/curl\//, 'curl']];

/** Short browser name from a user agent; "Otro" when unknown, "—" when absent. */
export function browserName(userAgent) {
  if (!userAgent) return '—';
  const found = BROWSERS.find(([pattern]) => pattern.test(userAgent));
  return found ? found[1] : 'Otro';
}
