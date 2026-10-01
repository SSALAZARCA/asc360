/**
 * Motored Fase 4 (F2b): the pure rules of the inline edit of "Cantidad a
 * pedir" (what the screen accepts before calling the server, the optimistic
 * value of a line) and the PATCH client.
 */
import { installFetch, jsonRes, setSession, L_NORMAL, L_EDITADA, lineaEditada } from './helpers/pedidosFetch';
import {
  MAX_CANTIDAD, cantidadEntera, lineaConCantidad, validarCantidad,
} from '../components/motored/pedidos/cantidad';
import { editarLinea } from '../lib/motored/pedidosApi';

const L_FUERA_BASE = { ...L_NORMAL, pedido_final: '30.00', fuera_de_empaque: true };

describe('validarCantidad', () => {
  it.each([['0', 0], ['60', 60], ['  12 ', 12], ['9999999', 9999999], ['007', 7]])(
    'accepts the whole number %j as %d', (texto, valor) => {
      expect(validarCantidad(texto)).toEqual({ valor });
    },
  );

  it.each([
    ['', /Escriba la cantidad/],
    ['   ', /Escriba la cantidad/],
    ['2.5', /números enteros/],
    ['2,5', /números enteros/],
    ['-1', /números enteros/],
    ['abc', /números enteros/],
    ['1e3', /números enteros/],
    ['10000000', /máximo es 9\.999\.999/],
  ])('rejects %j with a Spanish message', (texto, mensaje) => {
    const resultado = validarCantidad(texto);
    expect(resultado.valor).toBeUndefined();
    expect(resultado.error).toMatch(mensaje);
  });

  it('keeps the limit in sync with the backend (E-CORRIDA-053)', () => {
    expect(MAX_CANTIDAD).toBe(9999999);
  });
});

describe('cantidadEntera', () => {
  it.each([['48.00', '48'], ['0.00', '0'], ['1010', '1010'], [60, '60']])('shows %j as %j', (valor, texto) => {
    expect(cantidadEntera(valor)).toBe(texto);
  });

  it('is empty when the value is missing', () => {
    expect(cantidadEntera(null)).toBe('');
    expect(cantidadEntera(undefined)).toBe('');
  });
});

describe('lineaConCantidad (optimistic value)', () => {
  it('changes the quantity, its value in pesos and the pack warning, and nothing else', () => {
    const nueva = lineaConCantidad(L_NORMAL, 30);
    expect(nueva.pedido_final).toBe('30.00');
    expect(nueva.valor_pedido).toBe('450000.00');
    expect(nueva.fuera_de_empaque).toBe(true);
    expect(nueva).toEqual({ ...L_NORMAL, pedido_final: '30.00', valor_pedido: '450000.00', fuera_de_empaque: true });
  });

  it('clears the warning on a pack multiple and on zero', () => {
    expect(lineaConCantidad(L_FUERA_BASE, 36).fuera_de_empaque).toBe(false);
    expect(lineaConCantidad(L_FUERA_BASE, 0).fuera_de_empaque).toBe(false);
  });

  it('values a line without price at zero', () => {
    expect(lineaConCantidad({ ...L_NORMAL, precio: null }, 5).valor_pedido).toBe('0.00');
  });

  it('does not mutate the line it receives', () => {
    const copia = { ...L_EDITADA };
    lineaConCantidad(L_EDITADA, 11);
    expect(L_EDITADA).toEqual(copia);
  });
});

describe('editarLinea (PATCH client)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    setSession('COMPRAS');
  });

  it('sends the new quantity and the value the screen saw', async () => {
    const calls = installFetch({ 'PATCH /corridas/c1/lineas/1': lineaEditada(L_NORMAL, 60) });
    const body = await editarLinea('c1', 1, { pedido_final: 60, esperado: '48.00' });
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe('PATCH');
    expect(calls[0].body).toEqual({ pedido_final: 60, esperado: '48.00' });
    expect(body.linea.pedido_final).toBe('60.00');
    expect(body.totales_tienda.unidades_a_pedir).toBe('1022.00');
  });

  it('rejects with the coded error of the server', async () => {
    installFetch({
      'PATCH /corridas/c1/lineas/1': jsonRes({ detail: { code: 'E-CORRIDA-066', message: 'La cantidad cambió.' } }, 409),
    });
    await expect(editarLinea('c1', 1, { pedido_final: 60, esperado: '48.00' })).rejects.toMatchObject({
      status: 409, code: 'E-CORRIDA-066', message: 'La cantidad cambió.',
    });
  });
});
