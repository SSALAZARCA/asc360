/**
 * Referencias pagination (`odd/tasks/motored-referencias-paginacion.md`, T2):
 * API helpers for the dedicated read endpoints. Mocks `global.fetch`
 * directly (same convention as `motored-api-descargar-blob.test.jsx`).
 */
import { buscarReferencias, listLineasComerciales, buscarSustitutas } from '../lib/motored/api';
import { MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

const BASE = 'http://localhost:8000/api/motored';

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
});

function calledUrl() {
  return new URL(global.fetch.mock.calls[0][0]);
}

describe('buscarReferencias', () => {
  it('sends page and page_size to the paginated endpoint', async () => {
    await buscarReferencias({ page: 2, pageSize: 100 });

    const url = calledUrl();
    expect(`${url.origin}${url.pathname}`).toBe(`${BASE}/maestros/referencias/buscar`);
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('page_size')).toBe('100');
  });

  it('sends only the filters that have a value', async () => {
    await buscarReferencias({ page: 1, pageSize: 50, q: ' filtro ', lineaComercial: '', activa: false });

    const params = calledUrl().searchParams;
    expect(params.get('q')).toBe('filtro');
    expect(params.get('activa')).toBe('false');
    expect(params.has('linea_comercial')).toBe(false);
    expect(params.has('proveedor_id')).toBe(false);
  });

  it('omits activa when no estado filter is chosen', async () => {
    await buscarReferencias({ page: 1, pageSize: 50, activa: null, lineaComercial: 'REPUESTOS' });

    const params = calledUrl().searchParams;
    expect(params.has('activa')).toBe(false);
    expect(params.get('linea_comercial')).toBe('REPUESTOS');
  });
});

describe('listLineasComerciales', () => {
  it('calls the distinct líneas endpoint', async () => {
    await listLineasComerciales();

    expect(global.fetch.mock.calls[0][0]).toBe(`${BASE}/maestros/referencias/lineas-comerciales`);
  });
});

describe('buscarSustitutas', () => {
  it('sends proveedor_id, q and exclude_id', async () => {
    await buscarSustitutas({ proveedorId: 'p1', q: 'abc', excludeId: 'r1' });

    const url = calledUrl();
    expect(url.pathname).toBe('/api/motored/maestros/referencias/sustitutas');
    expect(url.searchParams.get('proveedor_id')).toBe('p1');
    expect(url.searchParams.get('q')).toBe('abc');
    expect(url.searchParams.get('exclude_id')).toBe('r1');
  });

  it('omits exclude_id when creating a new referencia', async () => {
    await buscarSustitutas({ proveedorId: 'p1', q: 'abc', excludeId: null });

    expect(calledUrl().searchParams.has('exclude_id')).toBe(false);
  });
});
