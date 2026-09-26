/**
 * Tests for the 3 new `lib/motored/api.js` helpers wrapping the ADMIN-only
 * Ventas Perdidas panel endpoints (sdd/motored-ventas-perdidas-panel,
 * Phase 6, tasks 6.1/6.2; design D6; backend already shipped in
 * `backend/app/motored/api/demanda_perdida.py`, Phases 4-5):
 *   - `listarBotLineas(filtros)` -> GET /demanda-perdida/bot-lineas
 *   - `editarBotLinea(id, cantidad)` -> PATCH /demanda-perdida/bot-lineas/{id}
 *   - `anularBotLinea(id)` -> POST /demanda-perdida/bot-lineas/{id}/anular
 *
 * Mirrors `motored-bulk-upload-excel.test.jsx`'s convention: mock
 * `global.fetch` directly (not `lib/motored/api` itself, since these ARE the
 * functions under test) and assert on the exact URL/method/body built, plus
 * error propagation matching `motoredFetchJson`'s existing shape (same one
 * every other `api.js` function already uses -- throws `Error(body.detail)`
 * on a non-2xx response, `Error('HTTP ' + status)` when there's no
 * `detail`).
 */
import { listarBotLineas, editarBotLinea, anularBotLinea } from '../lib/motored/api';
import { MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

const BASE = 'http://localhost:8000/api/motored';

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ([]),
  });
});

describe('listarBotLineas', () => {
  it('builds the query string from desde/hasta only when the rest are omitted', async () => {
    await listarBotLineas({ desde: '2026-08-27', hasta: '2026-09-26' });

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/demanda-perdida/bot-lineas?desde=2026-08-27&hasta=2026-09-26`);
    expect(options.method ?? 'GET').toBe('GET');
  });

  it('includes sucursalId/usuarioId/estado as sucursal_id/usuario_id/estado when provided', async () => {
    await listarBotLineas({
      desde: '2026-08-27',
      hasta: '2026-09-26',
      sucursalId: 'suc-1',
      usuarioId: 'user-1',
      estado: 'ACTIVA',
    });

    const [url] = global.fetch.mock.calls[0];
    const params = new URL(url).searchParams;
    expect(params.get('desde')).toBe('2026-08-27');
    expect(params.get('hasta')).toBe('2026-09-26');
    expect(params.get('sucursal_id')).toBe('suc-1');
    expect(params.get('usuario_id')).toBe('user-1');
    expect(params.get('estado')).toBe('ACTIVA');
  });

  it('omits a filter key entirely when its value is falsy, instead of sending an empty param', async () => {
    await listarBotLineas({ desde: '2026-08-27', hasta: '2026-09-26', sucursalId: '', estado: undefined });

    const [url] = global.fetch.mock.calls[0];
    const params = new URL(url).searchParams;
    expect(params.has('sucursal_id')).toBe(false);
    expect(params.has('estado')).toBe(false);
  });

  it('sends the bearer token via Authorization, same as every other api.js function', async () => {
    await listarBotLineas({ desde: '2026-08-27', hasta: '2026-09-26' });

    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers.Authorization).toBe('Bearer fake-token');
  });

  it('propagates a non-2xx error using body.detail, same as motoredFetchJson', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: { code: 'RANGO_MAXIMO_31_DIAS' } }),
    });

    await expect(listarBotLineas({ desde: '2026-08-27', hasta: '2026-09-26' })).rejects.toThrow();
  });

  it('propagates HTTP {status} when the error body has no detail', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({}),
    });

    await expect(listarBotLineas({ desde: '2026-08-27', hasta: '2026-09-26' })).rejects.toThrow('HTTP 403');
  });
});

describe('editarBotLinea', () => {
  it('sends PATCH to /demanda-perdida/bot-lineas/{id} with { cantidad } as the body', async () => {
    await editarBotLinea('linea-1', 5);

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/demanda-perdida/bot-lineas/linea-1`);
    expect(options.method).toBe('PATCH');
    expect(JSON.parse(options.body)).toEqual({ cantidad: 5 });
  });

  it('propagates a non-2xx error the same way sibling PATCH-based api.js functions do', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: { code: 'LINEA_ANULADA' } }),
    });

    await expect(editarBotLinea('linea-1', 5)).rejects.toThrow();
  });
});

describe('anularBotLinea', () => {
  it('sends POST to /demanda-perdida/bot-lineas/{id}/anular with no body', async () => {
    await anularBotLinea('linea-1');

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/demanda-perdida/bot-lineas/linea-1/anular`);
    expect(options.method).toBe('POST');
    expect(options.body).toBeUndefined();
  });

  it('propagates a non-2xx error the same way sibling POST-action api.js functions do', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: { code: 'LINEA_NO_ENCONTRADA' } }),
    });

    await expect(anularBotLinea('linea-1')).rejects.toThrow();
  });
});
