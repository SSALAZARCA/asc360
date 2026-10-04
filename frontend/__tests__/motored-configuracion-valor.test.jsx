/**
 * Pure helpers of the Configuración page: how a stored value becomes an
 * editable draft and back (typed per spec `tipo`), and how it is shown.
 */
import {
  aBorrador, desdeBorrador, formatearValor, mesActual, vigenteDesdeDeMes,
} from '../components/motored/configuracion/valor';

const spec = (tipo, extra = {}) => ({ clave: 'x', tipo, opciones: [], campos: [], ...extra });

describe('desdeBorrador', () => {
  it('bool passes through', () => {
    expect(desdeBorrador(spec('bool'), true)).toEqual({ valor: true });
  });

  it.each([['15', 15], [' 7 ', 7], ['0', 0]])('entero %p -> %p', (texto, esperado) => {
    expect(desdeBorrador(spec('entero'), texto)).toEqual({ valor: esperado });
  });

  it.each(['', 'abc', '1.5', '-', '1e3'])('rejects the entero %p', (texto) => {
    expect(desdeBorrador(spec('entero'), texto).error).toMatch(/entero/);
  });

  it('decimal keeps text with a dot and accepts a comma', () => {
    expect(desdeBorrador(spec('decimal'), '0,80')).toEqual({ valor: '0.80' });
    expect(desdeBorrador(spec('decimal'), ' 3 ')).toEqual({ valor: '3' });
  });

  it.each(['', 'x', '1..2', '-1'])('rejects the decimal %p', (texto) => {
    expect(desdeBorrador(spec('decimal'), texto).error).toMatch(/número/);
  });

  it('opcion passes the chosen string', () => {
    expect(desdeBorrador(spec('opcion', { opciones: ['A', 'B'] }), 'B')).toEqual({ valor: 'B' });
  });

  it('lista splits lines, trims and drops blanks', () => {
    expect(desdeBorrador(spec('lista'), ' A \n\nB\n')).toEqual({ valor: ['A', 'B'] });
    expect(desdeBorrador(spec('lista_digitos'), '900\n901')).toEqual({ valor: ['900', '901'] });
  });

  it('k_fms and objeto_numerico keep every field as text', () => {
    const s = spec('objeto_numerico', { campos: ['verde_desde', 'ambar_desde'] });
    expect(desdeBorrador(s, { verde_desde: '90', ambar_desde: '70,5' }))
      .toEqual({ valor: { verde_desde: '90', ambar_desde: '70.5' } });
    expect(desdeBorrador(s, { verde_desde: '90', ambar_desde: '' }).error).toMatch(/ambar_desde/);
  });

  it('mapa_opcion builds the object and skips blank keys', () => {
    const s = spec('mapa_opcion', { opciones: ['P', 'O'] });
    expect(desdeBorrador(s, [{ clave: 'GERENTE', valor: 'P' }, { clave: ' ', valor: 'O' }]))
      .toEqual({ valor: { GERENTE: 'P' } });
  });

  it('mapa_opcion rejects a repeated key', () => {
    const s = spec('mapa_opcion', { opciones: ['P', 'O'] });
    const dup = [{ clave: 'A', valor: 'P' }, { clave: 'A', valor: 'O' }];
    expect(desdeBorrador(s, dup).error).toMatch(/repetid/);
  });

  it('tramos keeps order and sends numbers as text', () => {
    const filas = [
      { nombre: 'BASE', desde_pct: '0', tasa_pct: '1,0' },
      { nombre: 'PRO', desde_pct: '90', tasa_pct: '1.5' },
    ];
    expect(desdeBorrador(spec('tramos'), filas)).toEqual({
      valor: [
        { nombre: 'BASE', desde_pct: '0', tasa_pct: '1.0' },
        { nombre: 'PRO', desde_pct: '90', tasa_pct: '1.5' },
      ],
    });
  });

  it('tramos rejects a non numeric cell', () => {
    const filas = [{ nombre: 'A', desde_pct: 'x', tasa_pct: '1' }];
    expect(desdeBorrador(spec('tramos'), filas).error).toMatch(/número/);
  });
});

describe('aBorrador', () => {
  it('round-trips every type', () => {
    const casos = [
      [spec('bool'), true],
      [spec('entero'), 30],
      [spec('decimal'), '0.80'],
      [spec('opcion'), 'CERCANO'],
      [spec('lista'), ['A', 'B']],
      [spec('objeto_numerico', { campos: ['a', 'b'] }), { a: '1', b: '2' }],
      [spec('mapa_opcion', { opciones: ['P'] }), { G: 'P' }],
      [spec('tramos'), [{ nombre: 'B', desde_pct: '0', tasa_pct: '1' }]],
    ];
    casos.forEach(([s, valor]) => {
      expect(desdeBorrador(s, aBorrador(s, valor))).toEqual({ valor });
    });
  });

  it('numbers become text for the inputs', () => {
    expect(aBorrador(spec('entero'), 30)).toBe('30');
    expect(aBorrador(spec('lista'), ['A', 'B'])).toBe('A\nB');
  });
});

describe('formatearValor', () => {
  it.each([
    [spec('bool'), true, 'Sí'],
    [spec('bool'), false, 'No'],
    [spec('entero'), 30, '30'],
    [spec('decimal'), null, 'Sin valor'],
    [spec('lista'), ['A', 'B'], 'A, B'],
    [spec('objeto_numerico', { campos: ['a', 'b'] }), { a: 1, b: 2 }, 'a: 1 · b: 2'],
    [spec('mapa_opcion'), { G: 'P' }, 'G → P'],
    [spec('tramos'), [{ nombre: 'BASE', desde_pct: 0, tasa_pct: 1 }], 'BASE: desde 0% → 1%'],
  ])('shows %# readable', (s, valor, texto) => {
    expect(formatearValor(s, valor)).toBe(texto);
  });
});

describe('months', () => {
  it('mesActual and vigenteDesdeDeMes', () => {
    expect(mesActual(new Date(2026, 9, 4))).toBe('2026-10');
    expect(mesActual(new Date(2026, 0, 31))).toBe('2026-01');
    expect(vigenteDesdeDeMes('2026-11')).toBe('2026-11-01');
  });
});
