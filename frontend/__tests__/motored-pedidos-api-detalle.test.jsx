/** Motored Fase 4 (F2a): read calls of the corrida detail and tienda pages. */
const mockFetch = jest.fn();
global.fetch = (...a) => mockFetch(...a);

import {
  listarLineas, getPedidoTienda, getEventosTienda, getHistorialLinea,
} from '../lib/motored/pedidosApi';

const BASE = 'http://localhost:8000/api/motored';
const res = (body, status = 200) => ({
  ok: status < 400, status, json: async () => body, clone() { return this; },
});
const lastUrl = () => new URL(mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0]);

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem('motored_token', 'tok');
  mockFetch.mockResolvedValue(res({ items: [] }));
});

describe('listarLineas', () => {
  it('sends the tienda, the filters that are set and limite/offset', async () => {
    await listarLineas('c1', {
      sucursal_id: 's1', clase: 'AF', estado_quiebre: '', q: 'filtro', solo_editadas: true, limite: 50, offset: 100,
    });
    const url = lastUrl();
    expect(url.origin + url.pathname).toBe(`${BASE}/corridas/c1/lineas`);
    expect(Object.fromEntries(url.searchParams)).toEqual({
      sucursal_id: 's1', clase: 'AF', q: 'filtro', solo_editadas: 'true', limite: '50', offset: '100',
    });
  });

  it('can ask for the excluded lines', async () => {
    await listarLineas('c1', { sucursal_id: 's1', incluir_excluidas: true });
    expect(lastUrl().searchParams.get('incluir_excluidas')).toBe('true');
  });
});

describe('tienda pedido reads', () => {
  it('getPedidoTienda reads the tienda header', async () => {
    await getPedidoTienda('c1', 's1');
    expect(lastUrl().pathname).toBe('/api/motored/corridas/c1/sucursales/s1');
  });

  it('getEventosTienda reads the tienda timeline', async () => {
    await getEventosTienda('c1', 's1');
    expect(lastUrl().pathname).toBe('/api/motored/corridas/c1/sucursales/s1/eventos');
  });

  it('getHistorialLinea reads the edit history of one line', async () => {
    await getHistorialLinea('c1', 7);
    expect(lastUrl().pathname).toBe('/api/motored/corridas/c1/lineas/7/historial');
  });
});
