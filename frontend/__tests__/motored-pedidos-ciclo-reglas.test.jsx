/**
 * Motored Fase 4 (F3): the pure rules of the pedido lifecycle UI
 * (`acciones.js`) and the lifecycle calls of `pedidosApi`.
 */
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { ACTION_ICONS } from '../components/motored/actionIcons';
import {
  accionesVisibles, hoyBogota, sinCantidad, tiendaDeCabecera, validarEnvio,
} from '../components/motored/pedidos/acciones';
import {
  cerrarLote, cerrarTienda, corregirEnvio, enviarLote, enviarTienda, exportarTienda, exportarZip, reabrirTienda,
} from '../lib/motored/pedidosApi';

const todas = (over = {}) => ({
  cerrar: false, reabrir: false, editar: false, enviar: false, corregir_envio: false, exportar: false, ...over,
});

describe('accionesVisibles (UX-08: the actions follow the tienda state)', () => {
  const nombres = (acciones, unidades = '10.00') => accionesVisibles(acciones, unidades).map((a) => a.accion);

  it('offers only Cerrar on a draft', () => {
    expect(nombres(todas({ cerrar: true, editar: true }))).toEqual(['Cerrar']);
  });

  it('offers Reabrir, Exportar and Marcar como enviado on a closed tienda', () => {
    expect(nombres(todas({ reabrir: true, enviar: true, exportar: true })))
      .toEqual(['Reabrir', 'Exportar', 'Marcar como enviado']);
  });

  it('offers Exportar and Corregir número on a sent tienda', () => {
    expect(nombres(todas({ corregir_envio: true, exportar: true }))).toEqual(['Exportar', 'Corregir número']);
  });

  it('offers nothing when the backend allows nothing', () => {
    expect(accionesVisibles(todas(), '10.00')).toEqual([]);
    expect(accionesVisibles(undefined, '10.00')).toEqual([]);
  });

  it('keeps Marcar como enviado but disables it when there is nothing to order (A1)', () => {
    const lista = accionesVisibles(todas({ reabrir: true, enviar: true, exportar: true }), '0.00');
    const enviar = lista.find((a) => a.accion === 'Marcar como enviado');
    expect(enviar.deshabilitada).toBe(true);
    expect(enviar.motivo).toMatch(/nada que pedir/i);
    expect(lista.find((a) => a.accion === 'Reabrir').deshabilitada).toBe(false);
  });

  it('leaves Marcar como enviado enabled when there are units', () => {
    const lista = accionesVisibles(todas({ enviar: true }), '12.00');
    expect(lista[0].deshabilitada).toBe(false);
  });
});

describe('sinCantidad', () => {
  it.each([['0.00', true], ['0', true], [0, true], ['5.00', false], [null, false], [undefined, false]])(
    '%p -> %p', (valor, esperado) => expect(sinCantidad(valor)).toBe(esperado),
  );
});

describe('tiendaDeCabecera', () => {
  it('adapts the tienda page header to the shape of a Tiendas table row', () => {
    const cab = {
      sucursal_id: 's1', nombre: 'Manizales', estado_pedido: 'CERRADO', fecha_corte: '2026-10-01',
      totales: { unidades_a_pedir: '800.00' }, acciones: todas({ reabrir: true }),
      envio: { numero_orden: '12345' },
    };
    expect(tiendaDeCabecera(cab)).toEqual({
      sucursal_id: 's1', nombre: 'Manizales', estado_pedido: 'CERRADO', unidades_a_pedir: '800.00',
      acciones: todas({ reabrir: true }), envio: { numero_orden: '12345' },
    });
  });
});

describe('hoyBogota', () => {
  it('uses the Bogota calendar day, not the UTC one', () => {
    // 2026-10-02 02:30 UTC is still 2026-10-01 21:30 in Bogota (UTC-5).
    expect(hoyBogota(new Date('2026-10-02T02:30:00Z'))).toBe('2026-10-01');
    expect(hoyBogota(new Date('2026-10-02T12:00:00Z'))).toBe('2026-10-02');
  });
});

describe('validarEnvio', () => {
  const rango = { desde: '2026-10-01', hasta: '2026-10-05' };

  it('accepts a number and a date inside the range', () => {
    expect(validarEnvio({ numero: '12345', fecha: '2026-10-02' }, rango)).toBe('');
    expect(validarEnvio({ numero: ' 7 ', fecha: '2026-10-05' }, rango)).toBe('');
  });

  it('rejects a blank number', () => {
    expect(validarEnvio({ numero: '   ', fecha: '2026-10-02' }, rango)).toMatch(/número de orden/i);
  });

  it('rejects a number longer than 50 characters', () => {
    expect(validarEnvio({ numero: 'x'.repeat(51), fecha: '2026-10-02' }, rango)).toMatch(/50/);
    expect(validarEnvio({ numero: 'x'.repeat(50), fecha: '2026-10-02' }, rango)).toBe('');
  });

  it('rejects a missing date, a future date and a date before the cut', () => {
    expect(validarEnvio({ numero: '1', fecha: '' }, rango)).toMatch(/fecha/i);
    expect(validarEnvio({ numero: '1', fecha: '2026-10-06' }, rango)).toMatch(/posterior a hoy/i);
    expect(validarEnvio({ numero: '1', fecha: '2026-09-30' }, rango)).toMatch(/anterior al corte/i);
  });
});

describe('lifecycle icons', () => {
  it('has an icon for Corregir número', () => {
    expect(ACTION_ICONS['Corregir número']).toBeTruthy();
  });
});

describe('pedidosApi - lifecycle', () => {
  beforeEach(() => { sessionStorage.clear(); setSession('COMPRAS'); });

  it('closes one tienda', async () => {
    const calls = installFetch({ 'POST /corridas/c1/sucursales/s1/cerrar': jsonRes({ estado_pedido: 'CERRADO' }) });
    await expect(cerrarTienda('c1', 's1')).resolves.toEqual({ estado_pedido: 'CERRADO' });
    expect(calls[0].body).toBeNull();
  });

  it('closes the named tiendas, or every draft when no list is given', async () => {
    const calls = installFetch({ 'POST /corridas/c1/cerrar': jsonRes({ cerradas: [], ya_cerradas: 0 }) });
    await cerrarLote('c1', ['s1', 's2']);
    await cerrarLote('c1');
    expect(calls[0].body).toEqual({ sucursal_ids: ['s1', 's2'] });
    expect(calls[1].body).toBeNull();
  });

  it('reopens with the motivo', async () => {
    const calls = installFetch({ 'POST /corridas/c1/sucursales/s1/reabrir': jsonRes({ estado_pedido: 'BORRADOR' }) });
    await reabrirTienda('c1', 's1', 'Corrección');
    expect(calls[0].body).toEqual({ motivo: 'Corrección' });
  });

  it('sends one tienda and a batch', async () => {
    const calls = installFetch({
      'POST /corridas/c1/sucursales/s1/enviar': jsonRes({}),
      'POST /corridas/c1/enviar': jsonRes({ enviadas: [] }),
    });
    await enviarTienda('c1', 's1', { numero_pedido_proveedor: '12345', fecha_envio: '2026-10-02' });
    await enviarLote('c1', [{ sucursal_id: 's1', numero_pedido_proveedor: '1', fecha_envio: '2026-10-02' }]);
    expect(calls[0].body).toEqual({ numero_pedido_proveedor: '12345', fecha_envio: '2026-10-02' });
    expect(calls[1].body).toEqual({ envios: [{ sucursal_id: 's1', numero_pedido_proveedor: '1', fecha_envio: '2026-10-02' }] });
  });

  it('corrects the order number with a PATCH carrying only the number', async () => {
    const calls = installFetch({ 'PATCH /corridas/c1/sucursales/s1/envio': jsonRes({}) });
    await corregirEnvio('c1', 's1', '99999');
    expect(calls[0].method).toBe('PATCH');
    expect(calls[0].body).toEqual({ numero_pedido_proveedor: '99999' });
  });
});

describe('pedidosApi - export', () => {
  const archivo = (cabeceras = {}) => ({
    ok: true, status: 200, headers: { get: (k) => cabeceras[k.toLowerCase()] ?? null },
    blob: async () => ({}), clone() { return this; },
  });

  beforeEach(() => {
    sessionStorage.clear();
    setSession('COMPRAS');
    global.URL.createObjectURL = jest.fn(() => 'blob:x');
    global.URL.revokeObjectURL = jest.fn();
    jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });
  afterEach(() => jest.restoreAllMocks());

  it('downloads the xlsx of one tienda under the server file name', async () => {
    const calls = installFetch({
      'GET /corridas/c1/sucursales/s1/exportar': archivo({ 'content-disposition': 'attachment; filename="Pedido_SIC1234_Manizales_2026-10-01.xlsx"' }),
    });
    await expect(exportarTienda('c1', 's1')).resolves.toEqual({ nombre: 'Pedido_SIC1234_Manizales_2026-10-01.xlsx', omitidas: [] });
    expect(calls).toHaveLength(1);
  });

  it('downloads the zip of the whole corrida and returns the skipped tiendas', async () => {
    const omitidas = [{ sucursal_id: 's9', nombre: 'Cali', motivo: 'Aún en borrador' }];
    installFetch({
      'GET /corridas/c1/exportar': archivo({
        'content-disposition': 'attachment; filename="Pedidos_PED-1.zip"',
        'x-tiendas-omitidas': encodeURIComponent(JSON.stringify(omitidas)),
      }),
    });
    await expect(exportarZip('c1')).resolves.toEqual({ nombre: 'Pedidos_PED-1.zip', omitidas });
  });

  it('asks for the named tiendas with a repeated sucursal_id parameter', async () => {
    const calls = installFetch({ 'GET /corridas/c1/exportar': archivo() });
    await exportarZip('c1', ['s1', 's2']);
    expect(calls[0].query.getAll('sucursal_id')).toEqual(['s1', 's2']);
  });
});
