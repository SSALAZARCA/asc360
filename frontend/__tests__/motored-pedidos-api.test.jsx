/** Motored Fase 4 (F1): `lib/motored/pedidosApi.js` calls and error contract. */
const mockFetch = jest.fn();
global.fetch = (...a) => mockFetch(...a);

import {
  listarCorridas, crearCorrida, getCorrida, getProgreso, anularCorrida,
} from '../lib/motored/pedidosApi';

const BASE = 'http://localhost:8000/api/motored';
const res = (body, status = 200) => ({
  ok: status < 400, status, json: async () => body, clone() { return this; },
});

function lastCall() {
  const [url, options] = mockFetch.mock.calls[mockFetch.mock.calls.length - 1];
  return { url: new URL(url), options };
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem('motored_token', 'tok');
  mockFetch.mockResolvedValue(res({ ok: true }));
});

describe('listarCorridas', () => {
  it('sends only the filters that are set, with limite/offset', async () => {
    await listarCorridas({ estado: 'BORRADOR', escenario: false, pedidos: '', limite: 50, offset: 100 });
    const { url, options } = lastCall();
    expect(url.origin + url.pathname).toBe(`${BASE}/corridas`);
    expect(Object.fromEntries(url.searchParams)).toEqual({
      estado: 'BORRADOR', escenario: 'false', limite: '50', offset: '100',
    });
    expect(options.headers.Authorization).toBe('Bearer tok');
  });

  it('omits the query string when there are no filters', async () => {
    await listarCorridas({});
    expect(lastCall().url.search).toBe('');
  });
});

describe('crearCorrida', () => {
  it('POSTs the body as JSON', async () => {
    await crearCorrida({ fecha_corte: '2026-10-01', sucursal_ids: ['a', 'b'], nota: 'x' });
    const { url, options } = lastCall();
    expect(url.pathname).toBe('/api/motored/corridas');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ fecha_corte: '2026-10-01', sucursal_ids: ['a', 'b'], nota: 'x' });
  });
});

describe('reads and anular', () => {
  it('getCorrida and getProgreso hit the id paths', async () => {
    await getCorrida('c1');
    expect(lastCall().url.pathname).toBe('/api/motored/corridas/c1');
    await getProgreso('c1');
    expect(lastCall().url.pathname).toBe('/api/motored/corridas/c1/progreso');
  });

  it('anularCorrida POSTs the motivo', async () => {
    await anularCorrida('c1', 'Datos equivocados');
    const { url, options } = lastCall();
    expect(url.pathname).toBe('/api/motored/corridas/c1/anular');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ motivo: 'Datos equivocados' });
  });
});

describe('coded errors', () => {
  it('rejects with the server message, status and code', async () => {
    mockFetch.mockResolvedValue(res({
      detail: { code: 'E-CORRIDA-001', message: 'La fecha de corte es inválida.' },
    }, 422));
    const error = await crearCorrida({ fecha_corte: 'x' }).catch((e) => e);
    expect(error.message).toBe('La fecha de corte es inválida.');
    expect(error.status).toBe(422);
    expect(error.code).toBe('E-CORRIDA-001');
  });
});
