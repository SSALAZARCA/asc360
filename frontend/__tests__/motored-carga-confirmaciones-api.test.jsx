/**
 * `subirCarga`/`subirCargaArchivo` envian las confirmaciones del reemplazo de
 * referencias solo cuando se piden: sin opciones el request es el de siempre.
 * Mockea `global.fetch` (misma convencion que `motored-referencias-api.test.jsx`).
 */
import { subirCarga, subirCargaArchivo } from '../lib/motored/api';
import { MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
});

const archivo = () => new File(['x'], 'r.xlsx');

describe('subirCarga', () => {
  it('sin opciones envia solo las filas', async () => {
    await subirCarga('sucursal', [{ nombre: 'A' }]);

    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({ filas: [{ nombre: 'A' }] });
  });

  it('con opciones agrega las banderas del backend', async () => {
    await subirCarga('referencia', [], { confirmarReemplazo: true, confirmarInactivacionMasiva: true });

    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
      filas: [], confirmar_reemplazo: true, confirmar_inactivacion_masiva: true,
    });
  });

  it('manda codigos_inactivar solo cuando hay elegidos', async () => {
    await subirCarga('referencia', [], { confirmarReemplazo: true, codigosInactivar: ['A', 'B'] });
    await subirCarga('referencia', [], { confirmarReemplazo: true, codigosInactivar: [] });

    expect(JSON.parse(global.fetch.mock.calls[0][1].body).codigos_inactivar).toEqual(['A', 'B']);
    expect(JSON.parse(global.fetch.mock.calls[1][1].body)).not.toHaveProperty('codigos_inactivar');
  });
});

describe('subirCargaArchivo', () => {
  it('sin opciones no agrega query string', async () => {
    await subirCargaArchivo('sucursal', archivo());

    expect(global.fetch.mock.calls[0][0]).toMatch(/\/maestros\/sucursal\/carga\/excel$/);
  });

  it('con opciones las manda como query', async () => {
    await subirCargaArchivo('referencia', archivo(), { confirmarReemplazo: true, confirmarInactivacionMasiva: false });

    const url = new URL(global.fetch.mock.calls[0][0]);
    expect(url.pathname).toMatch(/\/maestros\/referencia\/carga\/excel$/);
    expect(url.searchParams.get('confirmar_reemplazo')).toBe('true');
    expect(url.searchParams.has('confirmar_inactivacion_masiva')).toBe(false);
  });

  it('los codigos elegidos viajan en el formulario como lista JSON, no en la URL', async () => {
    await subirCargaArchivo('referencia', archivo(), { confirmarReemplazo: true, codigosInactivar: ['A', 'B'] });

    const [url, init] = global.fetch.mock.calls[0];
    expect(new URL(url).searchParams.has('codigos_inactivar')).toBe(false);
    expect(JSON.parse(init.body.get('codigos_inactivar'))).toEqual(['A', 'B']);
  });

  it('sin elegidos no agrega el campo', async () => {
    await subirCargaArchivo('referencia', archivo(), { confirmarReemplazo: true, codigosInactivar: [] });

    expect(global.fetch.mock.calls[0][1].body.has('codigos_inactivar')).toBe(false);
  });
});
