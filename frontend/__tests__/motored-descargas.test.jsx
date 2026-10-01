/** Motored Fase 4 (F1): authenticated downloads (`lib/motored/descargas.js`). */
const mockFetch = jest.fn();
global.fetch = (...a) => mockFetch(...a);

import { descargarArchivo, nombreDeContentDisposition, leerOmitidas } from '../lib/motored/descargas';

const headers = (map) => ({ get: (k) => map[k.toLowerCase()] ?? null });
const fileRes = (map = {}) => ({
  ok: true, status: 200, headers: headers(map), blob: async () => ({ fake: 'blob' }), clone() { return this; },
});
const errRes = (body, status) => ({
  ok: false, status, headers: headers({}), json: async () => body, clone() { return this; },
});

let clickMock;
let anchor;
beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem('motored_token', 'tok');
  global.URL.createObjectURL = jest.fn(() => 'blob:x');
  global.URL.revokeObjectURL = jest.fn();
  clickMock = jest.fn();
  const real = document.createElement.bind(document);
  jest.spyOn(document, 'createElement').mockImplementation((tag) => {
    const el = real(tag);
    if (tag === 'a') { el.click = clickMock; anchor = el; }
    return el;
  });
});
afterEach(() => jest.restoreAllMocks());

describe('nombreDeContentDisposition', () => {
  it('prefers filename* (RFC 5987) over the ASCII fallback', () => {
    const value = `attachment; filename="Pedido_Medellin.xlsx"; filename*=UTF-8''Pedido_Medell%C3%ADn.xlsx`;
    expect(nombreDeContentDisposition(value)).toBe('Pedido_Medellín.xlsx');
  });

  it('reads a plain quoted filename', () => {
    expect(nombreDeContentDisposition('attachment; filename="a b.zip"')).toBe('a b.zip');
  });

  it('returns null when there is no header or no name', () => {
    expect(nombreDeContentDisposition(null)).toBeNull();
    expect(nombreDeContentDisposition('attachment')).toBeNull();
  });
});

describe('leerOmitidas', () => {
  it('decodes the percent-encoded JSON header', () => {
    const lista = [{ sucursal_id: 'a', nombre: 'Medellín', motivo: 'Sin cantidades' }];
    const valor = encodeURIComponent(JSON.stringify(lista));
    expect(leerOmitidas(valor)).toEqual(lista);
  });

  it('is an empty list for a missing or broken header', () => {
    expect(leerOmitidas(null)).toEqual([]);
    expect(leerOmitidas('%E0%A4%A')).toEqual([]);
    expect(leerOmitidas(encodeURIComponent('{"x":1}'))).toEqual([]);
  });
});

describe('descargarArchivo', () => {
  it('downloads with the server file name and returns the skipped tiendas', async () => {
    const omitidas = [{ sucursal_id: 'a', nombre: 'Cali', motivo: 'Aún en borrador' }];
    mockFetch.mockResolvedValue(fileRes({
      'content-disposition': `attachment; filename="x.zip"; filename*=UTF-8''Pedidos_PED-1.zip`,
      'x-tiendas-omitidas': encodeURIComponent(JSON.stringify(omitidas)),
    }));
    const out = await descargarArchivo('/corridas/c1/exportar', 'respaldo.zip');
    expect(mockFetch.mock.calls[0][0]).toBe('http://localhost:8000/api/motored/corridas/c1/exportar');
    expect(mockFetch.mock.calls[0][1].headers.Authorization).toBe('Bearer tok');
    expect(anchor.download).toBe('Pedidos_PED-1.zip');
    expect(clickMock).toHaveBeenCalledTimes(1);
    expect(out).toEqual({ nombre: 'Pedidos_PED-1.zip', omitidas });
  });

  it('falls back to the default name and an empty skipped list', async () => {
    mockFetch.mockResolvedValue(fileRes());
    const out = await descargarArchivo('/x', 'respaldo.xlsx');
    expect(anchor.download).toBe('respaldo.xlsx');
    expect(out).toEqual({ nombre: 'respaldo.xlsx', omitidas: [] });
  });

  it('turns a JSON error body into a coded error and downloads nothing', async () => {
    mockFetch.mockResolvedValue(errRes({
      detail: { code: 'E-CORRIDA-055', message: 'No se puede exportar: la tienda está en borrador.' },
    }, 409));
    const error = await descargarArchivo('/x', 'a.xlsx').catch((e) => e);
    expect(error.message).toBe('No se puede exportar: la tienda está en borrador.');
    expect(error.status).toBe(409);
    expect(error.code).toBe('E-CORRIDA-055');
    expect(clickMock).not.toHaveBeenCalled();
  });
});
