/**
 * Motored Fase 4 (F4): the pure rules of the budget cap UI (`tope.js`) and
 * the cap / recorte calls of `pedidosApi`.
 */
import { installFetch, jsonRes } from './helpers/pedidosFetch';
import {
  cambiosDeTopes, contarSobreTope, filtrarTiendas, hayExceso, mapaRecortes, parsearTope, propuestaFresca,
  resumenRecorte, textoRecorte, tieneRecortes, topeComoTexto,
} from '../components/motored/pedidos/tope';
import {
  aplicarRecorte, getRecorte, getTopesCorrida, getTopesPresupuesto, guardarTopes, setModoTope,
} from '../lib/motored/pedidosApi';

describe('parsearTope (UX-28: empty = sin tope, otherwise whole pesos > 0)', () => {
  it('reads an empty text as "sin tope"', () => {
    expect(parsearTope('')).toEqual({ valor: null });
    expect(parsearTope('   ')).toEqual({ valor: null });
  });

  it('reads whole pesos', () => {
    expect(parsearTope('80000000')).toEqual({ valor: 80000000 });
    expect(parsearTope(' 1500 ')).toEqual({ valor: 1500 });
  });

  it.each(['0', '000', '-5', 'abc', '1.5', '1,5', '80.000.000', '1e6', '12 34', '1234567890123456'])(
    'rejects %p with a Spanish message', (texto) => {
      const { valor, error } = parsearTope(texto);
      expect(valor).toBeUndefined();
      expect(error).toMatch(/pesos|mayor que cero/i);
    },
  );
});

describe('topeComoTexto', () => {
  it.each([
    ['80000000.00', '80000000'], ['1500', '1500'], ['2500.50', '2500.5'], [null, ''], [undefined, ''],
  ])('%p -> %p', (valor, esperado) => expect(topeComoTexto(valor)).toBe(esperado));
});

const PROPUESTA = {
  activo: true, tope: '80000000.00', valor_actual: '95000000.00', exceso: '15000000.00',
  recortes: [
    { linea_id: 7, codigo: 'C-1', nombre: 'Bujía', clase_abc: 'CF', unidad_empaque: 12, pedido_actual: '48.00', pedido_propuesto: '36.00', valor_recortado: '180000.00' },
    { linea_id: 9, codigo: 'C-2', nombre: 'Filtro', clase_abc: 'CM', unidad_empaque: 10, pedido_actual: '20.00', pedido_propuesto: '0.00', valor_recortado: '70000.00' },
  ],
  valor_final: '79750000.00', exceso_residual: '0.00', lineas_sin_precio: 0, advertencias: [], token: 'tok1',
};

describe('rules over the proposal', () => {
  it('indexes the cuts by line id', () => {
    const mapa = mapaRecortes(PROPUESTA);
    expect(Object.keys(mapa)).toEqual(['7', '9']);
    expect(mapa[7].pedido_propuesto).toBe('36.00');
  });

  it('gives no cuts without a proposal or when it is inactive', () => {
    expect(mapaRecortes(null)).toEqual({});
    expect(mapaRecortes({ activo: false, recortes: [] })).toEqual({});
    // An inactive proposal never highlights, even if it carried lines.
    expect(mapaRecortes({ activo: false, recortes: PROPUESTA.recortes })).toEqual({});
  });

  it('sums the lines to cut and the value freed', () => {
    expect(resumenRecorte(PROPUESTA)).toEqual({ lineas: 2, liberado: 250000 });
    expect(resumenRecorte({ activo: true, recortes: [] })).toEqual({ lineas: 0, liberado: 0 });
  });

  it('has an excess only when the proposal is active and the excess is above zero', () => {
    expect(hayExceso(PROPUESTA)).toBe(true);
    expect(hayExceso({ ...PROPUESTA, exceso: '0.00' })).toBe(false);
    expect(hayExceso({ ...PROPUESTA, activo: false })).toBe(false);
    expect(hayExceso(null)).toBe(false);
  });
});

describe('contarSobreTope', () => {
  const t = (sucursal_id, exceso) => ({ sucursal_id, exceso });
  it('counts the tiendas whose excess is above zero', () => {
    expect(contarSobreTope([t('a', '10.00'), t('b', '0.00'), t('c', null), t('d', '5.00')])).toBe(2);
    expect(contarSobreTope([])).toBe(0);
    expect(contarSobreTope(undefined)).toBe(0);
  });
});

describe('cap and recorte calls', () => {
  it('reads the cap summary of a corrida and the recorte of one tienda', async () => {
    const calls = installFetch({
      'GET /corridas/c1/topes': jsonRes({ activo: true, tiendas: [] }),
      'GET /corridas/c1/sucursales/s1/recorte': jsonRes(PROPUESTA),
    });
    await getTopesCorrida('c1');
    await getRecorte('c1', 's1');
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      'GET /corridas/c1/topes', 'GET /corridas/c1/sucursales/s1/recorte',
    ]);
  });

  it('applies a recorte with the token the user saw', async () => {
    const calls = installFetch({ 'POST /corridas/c1/sucursales/s1/recorte': jsonRes({ lineas_recortadas: 2 }) });
    await aplicarRecorte('c1', 's1', 'tok1');
    expect(calls[0].body).toEqual({ token: 'tok1' });
  });

  it('reads and saves the caps', async () => {
    const calls = installFetch({
      'GET /parametros/topes-presupuesto': jsonRes({ modo_activo: false, topes: [] }),
      'POST /parametros/topes-presupuesto': jsonRes({ actualizados: ['s1'], sin_cambios: [] }, 201),
    });
    await getTopesPresupuesto();
    await guardarTopes([{ sucursal_id: 's1', valor: 80000000 }, { sucursal_id: 's2', valor: null }]);
    expect(calls[1].body).toEqual({ topes: [{ sucursal_id: 's1', valor: 80000000 }, { sucursal_id: 's2', valor: null }] });
  });

  it('switches the mode through the generic parameter route, effective today', async () => {
    const calls = installFetch({ 'POST /parametros': jsonRes({ clave: 'modo_tope_presupuesto' }, 201) });
    await setModoTope(true, '2026-10-02');
    expect(calls[0].body).toEqual({ clave: 'modo_tope_presupuesto', valor: true, vigente_desde: '2026-10-02' });
    await setModoTope(false, '2026-10-02');
    expect(calls[1].body.valor).toBe(false);
  });
});

describe('rules of the screens that read the server answers', () => {
  const FRESCA = { activo: true, recortes: [{ linea_id: 1 }], token: 't2' };

  it('takes the fresh proposal out of a 060 error', () => {
    const fallo = Object.assign(new Error('x'), { code: 'E-CORRIDA-060', detalle: { propuesta: FRESCA } });
    expect(propuestaFresca(fallo)).toBe(FRESCA);
  });

  it.each([
    ['another code', Object.assign(new Error('x'), { code: 'E-CORRIDA-061', detalle: { propuesta: FRESCA } })],
    ['no detail', Object.assign(new Error('x'), { code: 'E-CORRIDA-060' })],
    ['a proposal without cuts list', Object.assign(new Error('x'), { code: 'E-CORRIDA-060', detalle: { propuesta: { activo: true } } })],
    ['no error', null],
  ])('gives no fresh proposal for %s', (_n, fallo) => expect(propuestaFresca(fallo)).toBeNull());

  it('has cuts only when the proposal is active and lists a line', () => {
    expect(tieneRecortes(FRESCA)).toBe(true);
    expect(tieneRecortes({ activo: true, recortes: [] })).toBe(false);
    expect(tieneRecortes({ activo: false, recortes: [{ linea_id: 1 }] })).toBe(false);
    expect(tieneRecortes(null)).toBe(false);
  });

  it('words the cut of a line with the quantity left and how much goes', () => {
    expect(textoRecorte(PROPUESTA.recortes[0])).toBe('Recorte propuesto: 36 (−12)');
    expect(textoRecorte(PROPUESTA.recortes[1])).toBe('Recorte propuesto: 0 (−20)');
  });
});

describe('cambiosDeTopes (only what the user changed is sent)', () => {
  const topes = [
    { sucursal_id: 'a', nombre: 'Manizales', valor: '80000000.00' },
    { sucursal_id: 'b', nombre: 'Pereira', valor: null },
    { sucursal_id: 'c', nombre: 'Cali', valor: '45000000.50' },
  ];

  it('ignores the fields that were not touched, or went back to what they were', () => {
    expect(cambiosDeTopes(topes, {})).toEqual({ cambios: [], errores: {} });
    expect(cambiosDeTopes(topes, { a: '80000000', b: '', c: '45000000.5' })).toEqual({ cambios: [], errores: {} });
  });

  it('collects a new cap, a changed cap and a removed cap', () => {
    const { cambios, errores } = cambiosDeTopes(topes, { a: '', b: ' 1500000 ', c: '90000000' });
    expect(cambios).toEqual([
      { sucursal_id: 'a', valor: null }, { sucursal_id: 'b', valor: 1500000 }, { sucursal_id: 'c', valor: 90000000 },
    ]);
    expect(errores).toEqual({});
  });

  it('reports each invalid field by tienda and leaves it out of the changes', () => {
    const { cambios, errores } = cambiosDeTopes(topes, { a: '0', b: 'abc', c: '1' });
    expect(cambios).toEqual([{ sucursal_id: 'c', valor: 1 }]);
    expect(Object.keys(errores)).toEqual(['a', 'b']);
    expect(errores.a).toMatch(/mayor que cero/);
  });
});

describe('filtrarTiendas', () => {
  const tiendas = [{ nombre: 'Medellín Poblado' }, { nombre: 'Manizales' }, { nombre: 'Bogotá Norte' }];

  it('matches a part of the name, ignoring case and accents', () => {
    expect(filtrarTiendas(tiendas, 'medellin').map((t) => t.nombre)).toEqual(['Medellín Poblado']);
    expect(filtrarTiendas(tiendas, ' MA ').map((t) => t.nombre)).toEqual(['Manizales']);
    expect(filtrarTiendas(tiendas, 'bogota n').map((t) => t.nombre)).toEqual(['Bogotá Norte']);
  });

  it('returns everything for an empty search and nothing for no match', () => {
    expect(filtrarTiendas(tiendas, '  ')).toHaveLength(3);
    expect(filtrarTiendas(tiendas, 'zzz')).toEqual([]);
  });
});
