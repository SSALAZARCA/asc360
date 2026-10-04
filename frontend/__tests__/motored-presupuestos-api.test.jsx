/**
 * Budgets API client: paths, multipart upload and the 422 row errors of an apply.
 */
const mockFetch = jest.fn();
jest.mock('../lib/motored/motoredFetch', () => ({
  motoredFetch: (...a) => mockFetch(...a),
  motoredFetchJson: async (...a) => (await mockFetch(...a)).json(),
}));

import {
  aplicarPresupuestos, guardarAsesorPresupuesto, quitarAsesorPresupuesto, getMesPresupuesto,
} from '../lib/motored/presupuestosApi';

const respuesta = (status, body) => ({ ok: status < 400, status, json: async () => body });

beforeEach(() => mockFetch.mockReset());

it('uploads the file as multipart under "file"', async () => {
  mockFetch.mockResolvedValue(respuesta(200, { meses: [] }));
  const file = new File(['x'], 'a.xlsx');

  await aplicarPresupuestos(file);

  const [ruta, opciones] = mockFetch.mock.calls[0];
  expect(ruta).toBe('/presupuestos/aplicar');
  expect(opciones.method).toBe('POST');
  expect(opciones.body.get('file')).toBe(file);
});

it('a 422 apply rejects with the message and the row errors', async () => {
  mockFetch.mockResolvedValue(respuesta(422, { detail: { mensaje: 'El presupuesto tiene errores', errores: [{ fila: 1 }] } }));

  await expect(aplicarPresupuestos(new File(['x'], 'a.xlsx'))).rejects.toMatchObject({
    message: 'El presupuesto tiene errores', status: 422, errores: [{ fila: 1 }],
  });
});

it('a 409 apply rejects with the server message', async () => {
  mockFetch.mockResolvedValue(respuesta(409, { detail: 'Otra persona está modificando' }));

  await expect(aplicarPresupuestos(new File(['x'], 'a.xlsx'))).rejects.toMatchObject({ message: 'Otra persona está modificando', status: 409 });
});

it('builds the month, edit and removal paths', async () => {
  mockFetch.mockResolvedValue(respuesta(200, {}));

  await getMesPresupuesto('2026-10');
  await guardarAsesorPresupuesto('2026-10', '1 2', { sucursal_id: 's', monto: 5 });
  await quitarAsesorPresupuesto('2026-10', '123', 'baja total');
  await quitarAsesorPresupuesto('2026-10', '123');

  expect(mockFetch.mock.calls.map((c) => c[0])).toEqual([
    '/presupuestos/meses/2026-10',
    '/presupuestos/meses/2026-10/asesores/1%202',
    '/presupuestos/meses/2026-10/asesores/123?nota=baja%20total',
    '/presupuestos/meses/2026-10/asesores/123',
  ]);
  expect(mockFetch.mock.calls[1][1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ sucursal_id: 's', monto: 5 }) });
});
