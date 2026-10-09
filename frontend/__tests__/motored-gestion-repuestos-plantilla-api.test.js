/** Template download client: URL, fallback file name and the backend detail on error. */
const mockFetch = jest.fn();
jest.mock('../lib/motored/motoredFetch', () => ({
  motoredFetch: (...a) => mockFetch(...a),
  motoredFetchJson: jest.fn(),
}));

import { descargarPlantillaIngreso } from '../lib/motored/gestionRepuestosApi';

beforeEach(() => {
  jest.clearAllMocks();
  global.URL.createObjectURL = jest.fn(() => 'blob:x');
  global.URL.revokeObjectURL = jest.fn();
});

test('asks for the template of that invoice and store and names the file', async () => {
  const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  mockFetch.mockResolvedValue({
    ok: true, blob: async () => new Blob(['x']),
    headers: { get: () => null },
  });
  const r = await descargarPlantillaIngreso('RH 208629', 'suc-1');
  expect(mockFetch).toHaveBeenCalledWith('/gestion-repuestos/ingresos-facturas/plantilla?factura=RH+208629&sucursal=suc-1');
  expect(r.nombre).toBe('Entrada_compra_RH208629.xlsx');
  expect(click).toHaveBeenCalled();
  click.mockRestore();
});

test('rejects with the Spanish detail of the backend', async () => {
  mockFetch.mockResolvedValue({
    ok: false, status: 409, json: async () => ({ detail: 'La tienda no tiene bodega principal configurada.' }),
  });
  await expect(descargarPlantillaIngreso('RH 1', 's')).rejects.toThrow('no tiene bodega principal');
});
