/** Client-side check of the new-password rules (the server stays the source of truth). */
import {
  PASSWORD_MIN_LENGTH, PASSWORD_HINT, newPasswordProblem,
} from '../lib/motored/passwordRules';

describe('passwordRules', () => {
  it('exposes the agreed minimum and hint', () => {
    expect(PASSWORD_MIN_LENGTH).toBe(10);
    expect(PASSWORD_HINT).toBe('Mínimo 10 caracteres, con letras y números.');
  });

  it('checks length at the 9/10 boundary', () => {
    expect(newPasswordProblem('abcdefgh1')).toBe('La contraseña debe tener al menos 10 caracteres');
    expect(newPasswordProblem('abcdefghi1')).toBe('');
  });

  it('requires a letter', () => {
    expect(newPasswordProblem('8675309421')).toBe('La contraseña debe incluir al menos una letra.');
  });

  it('requires a digit', () => {
    expect(newPasswordProblem('soloLetrasAqui')).toBe('La contraseña debe incluir al menos un número.');
  });

  it('accepts accented letters as letters', () => {
    expect(newPasswordProblem('ñandúñandú1')).toBe('');
  });

  it('reports a mismatch only when the password itself is fine', () => {
    expect(newPasswordProblem('abcdefghi1', 'abcdefghi2')).toBe('Las contraseñas no coinciden');
    expect(newPasswordProblem('abcdefghi1', 'abcdefghi1')).toBe('');
    expect(newPasswordProblem('corta', 'otra')).toMatch(/al menos 10/);
  });
});
