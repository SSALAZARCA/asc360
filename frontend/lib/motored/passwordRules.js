/**
 * Client-side rules for NEW Motored passwords, kept in one place. The server
 * (`password_policy.py`) stays the source of truth and also checks the common
 * password list and the email rule; its messages are shown as they come.
 */
export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_LENGTH = 72;
export const PASSWORD_HINT = `Mínimo ${PASSWORD_MIN_LENGTH} caracteres, con letras y números.`;
export const ADMIN_FORCED_CHANGE_NOTE = 'El usuario deberá cambiar esta contraseña al ingresar.';
export const FORCED_CHANGE_BANNER = 'Por seguridad, debes cambiar tu contraseña antes de continuar.';

/** First broken rule for a new password (and its confirmation, when given); '' when fine. */
export function newPasswordProblem(password, confirmation) {
  if (password.length < PASSWORD_MIN_LENGTH) return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres`;
  if (!/\p{L}/u.test(password)) return 'La contraseña debe incluir al menos una letra.';
  if (!/[0-9]/.test(password)) return 'La contraseña debe incluir al menos un número.';
  if (confirmation !== undefined && password !== confirmation) return 'Las contraseñas no coinciden';
  return '';
}
