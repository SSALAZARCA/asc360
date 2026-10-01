/**
 * Motored Fase 4 (F5b): pure rules of the scenario launcher (escenario.js)
 * and the three API calls it needs. Typed values (bool, opcion, entero,
 * decimal, k_fms), what counts as a change (SC-03), the overrides body and the
 * Spanish wording of every engine key.
 */
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { compararCorridas, getParametroVigente, listarClavesMotor } from '../lib/motored/pedidosApi';
import {
  armarOverrides, borradorDesde, esCambio, etiquetaClave, parsearBorrador, resumenOverrides, textoValor,
} from '../components/motored/pedidos/escenario';

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('ADMIN');
});

describe('F5b API calls', () => {
  it('reads the catalog of engine keys with the MOTOR group', async () => {
    const calls = installFetch({ 'GET /parametros/claves': jsonRes([]) });
    await listarClavesMotor();
    expect(calls[0].path).toBe('/parametros/claves');
    expect(calls[0].query.get('grupo')).toBe('MOTOR');
  });

  it('reads the current value of one key', async () => {
    const calls = installFetch({ 'GET /parametros/factor_demanda_perdida/vigente': jsonRes({ clave: 'factor_demanda_perdida', valor: '1' }) });
    const vigente = await getParametroVigente('factor_demanda_perdida');
    expect(calls[0].path).toBe('/parametros/factor_demanda_perdida/vigente');
    expect(vigente.valor).toBe('1');
  });

  it('compares a scenario with a real corrida and keeps solo_diferencias=false in the query', async () => {
    const calls = installFetch({ 'GET /corridas/e1/comparar': jsonRes({ filas: [] }) });
    await compararCorridas('e1', { con: 'c1', sucursal_id: '', solo_diferencias: false, limite: 100, offset: 200 });
    expect(calls[0].path).toBe('/corridas/e1/comparar');
    expect(calls[0].query.get('con')).toBe('c1');
    expect(calls[0].query.get('solo_diferencias')).toBe('false');
    expect(calls[0].query.get('limite')).toBe('100');
    expect(calls[0].query.get('offset')).toBe('200');
    expect(calls[0].query.has('sucursal_id')).toBe(false);
    await compararCorridas('e1', { con: 'c1', sucursal_id: 's2', solo_diferencias: true });
    expect(calls[1].query.get('sucursal_id')).toBe('s2');
    expect(calls[1].query.get('solo_diferencias')).toBe('true');
  });
});

describe('etiquetaClave', () => {
  const CLAVES_MOTOR = [
    'incluir_demanda_perdida_en_ponderada', 'factor_demanda_perdida', 'consolidar_sustituidas', 'dias_entre_pedidos',
    'modo_mes_en_curso', 'tope_proyeccion_mes_actual', 'min_dias_mes_actual', 'excluir_transito_vencido',
    'modo_redondeo_empaque', 'corte_abc_a', 'corte_abc_b', 'umbral_f', 'umbral_m', 'k_fms', 'tolerancia_sobrestock',
    'meses_inventario_muerto', 'max_dias_antiguedad_inventario', 'max_dias_antiguedad_backorder',
    'max_dias_antiguedad_facturas', 'max_dias_antiguedad_ingresos',
  ];

  it('gives each of the 20 engine keys a business title and an explanation (no technical key shown)', () => {
    expect(CLAVES_MOTOR).toHaveLength(20);
    CLAVES_MOTOR.forEach((clave) => {
      const { titulo, ayuda } = etiquetaClave(clave);
      expect(titulo).not.toBe(clave);
      expect(titulo).not.toMatch(/_/);
      expect(ayuda.length).toBeGreaterThan(30);
    });
    expect(etiquetaClave('consolidar_sustituidas').titulo).toMatch(/sustitu/i);
  });

  it('falls back to the technical key when a key is new to the screen', () => {
    expect(etiquetaClave('clave_nueva')).toEqual({ titulo: 'clave_nueva', ayuda: '' });
  });
});

describe('borradorDesde (a stored value as the text or switch the user edits)', () => {
  it('reads each type', () => {
    expect(borradorDesde('bool', true)).toBe(true);
    expect(borradorDesde('bool', null)).toBe(false);
    expect(borradorDesde('opcion', 'CERCANO')).toBe('CERCANO');
    expect(borradorDesde('entero', 30)).toBe('30');
    expect(borradorDesde('decimal', '0.80')).toBe('0,8');
    expect(borradorDesde('decimal', 3.0)).toBe('3');
    expect(borradorDesde('k_fms', { F: '3', M: '1.5', S: '1' })).toEqual({ F: '3', M: '1,5', S: '1' });
  });

  it('gives empty text when the value is unknown', () => {
    expect(borradorDesde('entero', null)).toBe('');
    expect(borradorDesde('k_fms', null)).toEqual({ F: '', M: '', S: '' });
  });
});

describe('parsearBorrador (what the user typed as the value sent to the server)', () => {
  it('keeps booleans and options as they are', () => {
    expect(parsearBorrador('bool', true)).toEqual({ valor: true });
    expect(parsearBorrador('opcion', 'ARRIBA')).toEqual({ valor: 'ARRIBA' });
  });

  it('sends an entero as a JSON number and refuses decimals, signs and text', () => {
    expect(parsearBorrador('entero', ' 45 ')).toEqual({ valor: 45 });
    ['', '2,5', '-1', 'abc', '1e3'].forEach((texto) => {
      expect(parsearBorrador('entero', texto).error).toMatch(/entero/i);
    });
  });

  it('sends a decimal as exact text with a dot, accepting the Spanish comma', () => {
    expect(parsearBorrador('decimal', '0,85')).toEqual({ valor: '0.85' });
    expect(parsearBorrador('decimal', '3')).toEqual({ valor: '3' });
    ['', 'abc', '-2', '1,2,3', '1e3'].forEach((texto) => {
      expect(parsearBorrador('decimal', texto).error).toMatch(/número/i);
    });
  });

  it('needs the three factors of k_fms', () => {
    expect(parsearBorrador('k_fms', { F: '4', M: '1,5', S: '1' })).toEqual({ valor: { F: '4', M: '1.5', S: '1' } });
    expect(parsearBorrador('k_fms', { F: '4', M: '', S: '1' }).error).toMatch(/F, M y S/);
    expect(parsearBorrador('k_fms', { F: '4', M: 'x', S: '1' }).error).toMatch(/F, M y S/);
  });
});

describe('esCambio (SC-03: only a different value counts)', () => {
  it('compares numbers by value, not by text', () => {
    expect(esCambio('decimal', '0.80', { valor: '0.8' })).toBe(false);
    expect(esCambio('decimal', 3.0, { valor: '3' })).toBe(false);
    expect(esCambio('decimal', '0.80', { valor: '0.9' })).toBe(true);
    expect(esCambio('entero', 30, { valor: 30 })).toBe(false);
    expect(esCambio('entero', 30, { valor: 45 })).toBe(true);
  });

  it('compares switches, options and each factor of k_fms', () => {
    expect(esCambio('bool', false, { valor: false })).toBe(false);
    expect(esCambio('bool', false, { valor: true })).toBe(true);
    expect(esCambio('opcion', 'CERCANO', { valor: 'CERCANO' })).toBe(false);
    expect(esCambio('opcion', 'CERCANO', { valor: 'ARRIBA' })).toBe(true);
    const actual = { F: '3', M: '1.5', S: '1' };
    expect(esCambio('k_fms', actual, { valor: { F: '3', M: '1.50', S: '1' } })).toBe(false);
    expect(esCambio('k_fms', actual, { valor: { F: '3', M: '1.5', S: '2' } })).toBe(true);
  });

  it('is never a change when the typed value is invalid', () => {
    expect(esCambio('entero', 30, { error: 'x' })).toBe(false);
  });
});

describe('armarOverrides', () => {
  const fila = (clave, tipo, actual, borrador) => ({ clave, tipo, actual, borrador });

  it('sends only the keys whose value changed', () => {
    const { overrides, cambios, errores } = armarOverrides([
      fila('consolidar_sustituidas', 'bool', false, true),
      fila('dias_entre_pedidos', 'entero', 30, '30'),
      fila('corte_abc_a', 'decimal', '0.80', '0,85'),
    ]);
    expect(overrides).toEqual({ consolidar_sustituidas: true, corte_abc_a: '0.85' });
    expect(cambios).toBe(2);
    expect(errores).toEqual({});
  });

  it('reports invalid rows with their message and leaves them out', () => {
    const { overrides, cambios, errores } = armarOverrides([
      fila('dias_entre_pedidos', 'entero', 30, '2,5'),
      fila('consolidar_sustituidas', 'bool', false, true),
    ]);
    expect(overrides).toEqual({ consolidar_sustituidas: true });
    expect(cambios).toBe(1);
    expect(Object.keys(errores)).toEqual(['dias_entre_pedidos']);
    expect(errores.dias_entre_pedidos).toMatch(/entero/i);
  });

  it('has no changes when nothing was picked or nothing differs', () => {
    expect(armarOverrides([]).cambios).toBe(0);
    expect(armarOverrides([fila('umbral_f', 'entero', 2, '2')]).cambios).toBe(0);
  });
});

describe('textoValor (the current value in words)', () => {
  it('writes each type for a business reader', () => {
    expect(textoValor('bool', true)).toBe('Sí');
    expect(textoValor('bool', false)).toBe('No');
    expect(textoValor('opcion', 'EXCLUIDO')).toBe('EXCLUIDO');
    expect(textoValor('entero', 30)).toBe('30');
    expect(textoValor('decimal', '0.80')).toBe('0,8');
    expect(textoValor('k_fms', { F: '3', M: '1.5', S: '1' })).toBe('F 3 · M 1,5 · S 1');
  });

  it('shows a dash when there is no value', () => {
    expect(textoValor('entero', null)).toBe('—');
    expect(textoValor('k_fms', undefined)).toBe('—');
  });
});

describe('resumenOverrides (what a scenario tested, read back from its snapshot)', () => {
  it('names each parameter in business words with its tested value', () => {
    expect(resumenOverrides({
      consolidar_sustituidas: true, dias_entre_pedidos: 45, corte_abc_a: '0.85', modo_redondeo_empaque: 'ARRIBA',
      k_fms: { F: '4', M: '2', S: '1' },
    })).toEqual([
      'Sumar las ventas de la referencia sustituida: Sí',
      'Días entre pedidos: 45',
      'Corte de la clase A: 0,85',
      'Redondeo al empaque: ARRIBA',
      'Factores de cobertura por rotación: F 4 · M 2 · S 1',
    ]);
  });

  it('writes No for a switch turned off and keeps an unknown key as it came', () => {
    expect(resumenOverrides({ excluir_transito_vencido: false, clave_nueva: 3 })).toEqual([
      'Ignorar la mercancía en tránsito vencida: No', 'clave_nueva: 3',
    ]);
  });

  it('is empty for a corrida without overrides', () => {
    expect(resumenOverrides(null)).toEqual([]);
    expect(resumenOverrides({})).toEqual([]);
  });
});
