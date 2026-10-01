/**
 * Motored Fase 4 (sdd/motored-pedidos-ui, F1, verify G5 plumbing): coded
 * errors. The backend answers `detail: {code, message, detalle?}`; the
 * message must reach the UI and the error must carry status, code, detalle.
 */
import { httpErrorMessage, mensajeConCodigo } from '../lib/motored/httpErrors';

const mockFetch = jest.fn();
global.fetch = (...a) => mockFetch(...a);

import { motoredFetchJson } from '../lib/motored/motoredFetch';

const res = (body, status) => ({
  ok: status < 400, status, json: async () => body, clone() { return this; },
});

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('httpErrorMessage with an object detail', () => {
  it('reads detail.message', () => {
    const body = { detail: { code: 'E-CORRIDA-051', message: 'Hay tiendas cerradas.' } };
    expect(httpErrorMessage(409, body, 'fallback')).toBe('Hay tiendas cerradas.');
  });

  it('falls back when the object detail has no message', () => {
    expect(httpErrorMessage(409, { detail: { code: 'X' } }, 'fallback')).toBe('fallback');
  });

  it('keeps the string detail and the status-specific messages', () => {
    expect(httpErrorMessage(400, { detail: 'Texto plano' }, 'fb')).toBe('Texto plano');
    expect(httpErrorMessage(503, { detail: { message: 'ignorado' } }, 'fb'))
      .toMatch(/no está disponible/);
    expect(httpErrorMessage(429, {}, 'fb')).toMatch(/Demasiados intentos/);
  });
});

describe('mensajeConCodigo', () => {
  it('appends the code in parentheses when the error has one', () => {
    const error = Object.assign(new Error('Sin cupo.'), { code: 'E-CORRIDA-040' });
    expect(mensajeConCodigo(error)).toBe('Sin cupo. (E-CORRIDA-040)');
  });

  it('returns the bare message without a code and a default without a message', () => {
    expect(mensajeConCodigo(new Error('Falló'))).toBe('Falló');
    expect(mensajeConCodigo({}, 'No se pudo.')).toBe('No se pudo.');
  });
});

describe('motoredFetchJson coded errors', () => {
  it('throws the server message with status, code and detalle attached', async () => {
    const detalle = { tiendas: ['Pereira (CERRADO)'] };
    mockFetch.mockResolvedValue(res({
      detail: { code: 'E-CORRIDA-051', message: 'No se puede anular.', detalle },
    }, 409));
    const error = await motoredFetchJson('/corridas/1/anular').catch((e) => e);
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe('No se puede anular.');
    expect(error.status).toBe(409);
    expect(error.code).toBe('E-CORRIDA-051');
    expect(error.detalle).toEqual(detalle);
  });

  it('attaches the status to a plain string detail (no code)', async () => {
    mockFetch.mockResolvedValue(res({ detail: 'Corrida no encontrada.' }, 404));
    const error = await motoredFetchJson('/corridas/x').catch((e) => e);
    expect(error.message).toBe('Corrida no encontrada.');
    expect(error.status).toBe(404);
    expect(error.code).toBeUndefined();
  });

  it('still returns the body on success', async () => {
    mockFetch.mockResolvedValue(res({ ok: 1 }, 200));
    await expect(motoredFetchJson('/x')).resolves.toEqual({ ok: 1 });
  });
});
