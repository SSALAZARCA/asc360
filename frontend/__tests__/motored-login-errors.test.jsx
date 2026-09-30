/**
 * Login/change-password error mapping by HTTP status, and the automatic-logout
 * flag set by motoredFetch (odd/motored-login-hardening, T4).
 */
import { login, changeOwnPassword } from '../lib/motored/api';
import { MOTORED_EXPIRED_KEY, MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

function mockFetch(status, body) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

beforeEach(() => sessionStorage.clear());

describe('login error mapping', () => {
  it.each([
    [401, { detail: 'Credenciales incorrectas' }, 'Correo o contraseña incorrectos.'],
    [429, { error: 'Rate limit exceeded: 5 per 1 minute' }, 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'],
    [503, { detail: { code: 'MOTORED_UNAVAILABLE' } }, 'El servicio no está disponible en este momento. Inténtalo más tarde.'],
    [502, {}, 'El servicio no está disponible en este momento. Inténtalo más tarde.'],
    [504, {}, 'El servicio no está disponible en este momento. Inténtalo más tarde.'],
  ])('status %s maps to a friendly message, never an object', async (status, body, message) => {
    mockFetch(status, body);
    const err = await login('a@b.co', 'pw').catch((e) => e);
    expect(err.message).toBe(message);
    expect(err.message).not.toMatch(/object/i);
  });

  it('maps a network failure to a connection message', async () => {
    global.fetch = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(login('a@b.co', 'pw')).rejects.toThrow('No pudimos conectarnos. Revisa tu conexión.');
  });

  it('keeps a string detail from other statuses', async () => {
    mockFetch(422, { detail: 'La contraseña no puede superar 72 caracteres' });
    await expect(login('a@b.co', 'x')).rejects.toThrow('La contraseña no puede superar 72 caracteres');
  });
});

describe('change own password error mapping', () => {
  it('maps 429 to the rate-limit message', async () => {
    sessionStorage.setItem(MOTORED_TOKEN_KEY, 't');
    mockFetch(429, { error: 'Rate limit exceeded' });
    await expect(changeOwnPassword('a', 'b')).rejects.toThrow('Demasiados intentos. Espera un minuto e inténtalo de nuevo.');
  });

  it('maps an object detail on 503 to text', async () => {
    mockFetch(503, { detail: { code: 'MOTORED_UNAVAILABLE' } });
    const err = await changeOwnPassword('a', 'b').catch((e) => e);
    expect(typeof err.message).toBe('string');
    expect(err.message).not.toMatch(/object/i);
  });
});

describe('automatic logout flag', () => {
  it('is set when a 401 clears an existing session', async () => {
    sessionStorage.setItem(MOTORED_TOKEN_KEY, 't');
    mockFetch(401, { detail: 'expired' });
    await changeOwnPassword('a', 'b').catch(() => {});
    expect(sessionStorage.getItem(MOTORED_EXPIRED_KEY)).toBe('1');
  });

  it('is not set by a failed login attempt', async () => {
    sessionStorage.setItem(MOTORED_TOKEN_KEY, 'stale');
    mockFetch(401, { detail: 'bad' });
    await login('a@b.co', 'pw').catch(() => {});
    expect(sessionStorage.getItem(MOTORED_EXPIRED_KEY)).toBeNull();
  });
});
