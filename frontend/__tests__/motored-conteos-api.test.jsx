/**
 * Inventory counts API client (odd/motored-conteos-inventario, WU11/WU12):
 * each helper hits the leader endpoint with the right method and body, a
 * failed answer becomes an Error with the backend `mensaje`, its `code` and
 * the extra facts of the 409s (`datos`), and the Excel downloads go through
 * the authenticated blob path.
 */
import {
  asignarReconteo, cerrarConteo, descargarAjustes, desverificarPendiente, iniciarConteo, listarConteos,
  obtenerPendientesConteo, verificarPendiente,
  obtenerDiferencias, obtenerPanel, obtenerQrObjectUrl, programarConteo,
} from '../lib/motored/conteosApi';

const BASE = 'http://localhost:8000/api/motored';

function respuesta(status, body, extra = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve(new Blob(['x'])),
    headers: { get: () => null },
    clone() { return this; },
    ...extra,
  };
}

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem('motored_token', 'tok');
  global.fetch = jest.fn();
});

describe('conteosApi', () => {
  it('lists with the estado filter', async () => {
    fetch.mockResolvedValue(respuesta(200, []));
    await listarConteos({ estado: 'EN_CONTEO' });
    expect(fetch.mock.calls[0][0]).toBe(`${BASE}/conteos?estado=EN_CONTEO`);
  });

  it('asks the panel with the last version, or without one', async () => {
    fetch.mockResolvedValue(respuesta(200, { version: 42, sin_cambios: true }));
    expect(await obtenerPanel('c1', 42)).toEqual({ version: 42, sin_cambios: true });
    await obtenerPanel('c1');
    expect(fetch.mock.calls[0][0]).toBe(`${BASE}/conteos/c1/panel?version=42`);
    expect(fetch.mock.calls[1][0]).toBe(`${BASE}/conteos/c1/panel`);
  });

  it('lists everything without a filter', async () => {
    fetch.mockResolvedValue(respuesta(200, []));
    await listarConteos();
    expect(fetch.mock.calls[0][0]).toBe(`${BASE}/conteos`);
  });

  it('schedules with store, leader and date', async () => {
    fetch.mockResolvedValue(respuesta(201, { id: 'c1' }));
    await programarConteo({ sucursal_id: 's1', lider_id: 'l1', fecha_programada: '2026-10-12' });
    const [url, opciones] = fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/conteos`);
    expect(opciones.method).toBe('POST');
    expect(JSON.parse(opciones.body)).toEqual({
      sucursal_id: 's1', lider_id: 'l1', fecha_programada: '2026-10-12',
    });
  });

  it('starts with the stale-inventory confirmation flag', async () => {
    fetch.mockResolvedValue(respuesta(200, { codigo: '482913' }));
    await iniciarConteo('c1', { confirmarAntiguedad: true });
    const [url, opciones] = fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/conteos/c1/iniciar`);
    expect(JSON.parse(opciones.body)).toEqual({ confirmar_antiguedad: true, confirmar_pendientes: false });
  });

  it('starts with the pending-items confirmation flag', async () => {
    fetch.mockResolvedValue(respuesta(200, { codigo: '482913' }));
    await iniciarConteo('c1', { confirmarPendientes: true });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ confirmar_antiguedad: false, confirmar_pendientes: true });
  });

  it('reads, marks and unmarks the pending items of a conteo', async () => {
    fetch.mockResolvedValue(respuesta(200, { facturas: [] }));
    await obtenerPendientesConteo('c1');
    await verificarPendiente('c1', 'FACTURA', 'RH 1');
    await desverificarPendiente('c1', 'TRASLADO', 'D|B07|B01');
    const [[leer], [marcar, opcionesMarcar], [quitar, opcionesQuitar]] = fetch.mock.calls;
    expect(leer).toBe(`${BASE}/conteos/c1/pendientes`);
    expect(marcar).toBe(`${BASE}/conteos/c1/pendientes/verificar`);
    expect(JSON.parse(opcionesMarcar.body)).toEqual({ tipo: 'FACTURA', clave: 'RH 1' });
    expect(quitar).toBe(`${BASE}/conteos/c1/pendientes/desverificar`);
    expect(JSON.parse(opcionesQuitar.body)).toEqual({ tipo: 'TRASLADO', clave: 'D|B07|B01' });
  });

  it('turns a 409 into an Error with mensaje, code and datos', async () => {
    fetch.mockResolvedValue(respuesta(409, {
      detail: { code: 'INVENTARIO_ANTIGUO', mensaje: 'El inventario es viejo.', antiguedad_horas: '30.0' },
    }));
    const error = await iniciarConteo('c1').catch((e) => e);
    expect(error.message).toBe('El inventario es viejo.');
    expect(error.code).toBe('INVENTARIO_ANTIGUO');
    expect(error.status).toBe(409);
    expect(error.datos.antiguedad_horas).toBe('30.0');
  });

  it('asks for the differences with a filter', async () => {
    fetch.mockResolvedValue(respuesta(200, { items: [] }));
    await obtenerDiferencias('c1', 'criticas');
    expect(fetch.mock.calls[0][0]).toBe(`${BASE}/conteos/c1/diferencias?filtro=criticas`);
  });

  it('assigns with the same-pair override and its reason', async () => {
    fetch.mockResolvedValue(respuesta(200, {}));
    await asignarReconteo('c1', 'r1', { sesion_id: 's1', autorizar_misma_pareja: true, motivo: 'Sola' });
    const [url, opciones] = fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/conteos/c1/reconteos/r1/asignar`);
    expect(JSON.parse(opciones.body)).toEqual({ sesion_id: 's1', autorizar_misma_pareja: true, motivo: 'Sola' });
  });

  it('closes with forzar and motivo', async () => {
    fetch.mockResolvedValue(respuesta(200, {}));
    await cerrarConteo('c1', { forzar: true, motivo: 'Fin de jornada' });
    const [url, opciones] = fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/conteos/c1/cerrar`);
    expect(JSON.parse(opciones.body)).toEqual({ forzar: true, motivo: 'Fin de jornada' });
  });

  it('downloads the adjustment Excel with the token', async () => {
    const click = jest.fn();
    const crear = document.createElement.bind(document);
    jest.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = crear(tag);
      if (tag === 'a') el.click = click;
      return el;
    });
    global.URL.createObjectURL = jest.fn(() => 'blob:x');
    global.URL.revokeObjectURL = jest.fn();
    fetch.mockResolvedValue(respuesta(200, null, {
      headers: { get: () => 'attachment; filename="ajustes_A07_2026-10-09.xlsx"' },
    }));

    await descargarAjustes('c1');

    const [url, opciones] = fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/conteos/c1/ajustes.xlsx`);
    expect(opciones.headers.Authorization).toBe('Bearer tok');
    expect(click).toHaveBeenCalled();
    document.createElement.mockRestore();
  });

  it('fetches the QR as an object URL with the token', async () => {
    global.URL.createObjectURL = jest.fn(() => 'blob:qr');
    fetch.mockResolvedValue(respuesta(200, null));
    await expect(obtenerQrObjectUrl('c1')).resolves.toBe('blob:qr');
    expect(fetch.mock.calls[0][0]).toBe(`${BASE}/conteos/c1/qr.png`);
  });
});
