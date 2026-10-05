/**
 * Maestros writes announce the change (so health warnings refresh); reads
 * and failed writes do not.
 */
const mockFetchJson = jest.fn();
jest.mock('../lib/motored/motoredFetch', () => ({
  motoredFetch: jest.fn(),
  motoredFetchJson: (...args) => mockFetchJson(...args),
  getMotoredApiUrl: () => '',
}));

import {
  createMaestro, updateMaestro, deactivateMaestro, reactivateMaestro,
  subirCarga, subirCargaArchivo, listMaestros,
} from '../lib/motored/api';
import { EVENTO_MAESTROS_CAMBIARON } from '../lib/motored/maestrosEventos';

let avisos;
const contar = () => { avisos += 1; };

beforeEach(() => {
  avisos = 0;
  mockFetchJson.mockReset().mockResolvedValue({ ok: true });
  window.addEventListener(EVENTO_MAESTROS_CAMBIARON, contar);
});

afterEach(() => {
  window.removeEventListener(EVENTO_MAESTROS_CAMBIARON, contar);
});

it.each([
  ['create', () => createMaestro('sucursales', {})],
  ['update', () => updateMaestro('sucursales', 'id', {})],
  ['deactivate', () => deactivateMaestro('sucursales', 'id')],
  ['reactivate', () => reactivateMaestro('sucursales', 'id')],
  ['upload rows', () => subirCarga('sucursal', [])],
  ['upload file', () => subirCargaArchivo('sucursal', new Blob(['x']))],
])('%s announces the change', async (_nombre, llamar) => {
  await llamar();
  expect(avisos).toBe(1);
});

it('a read does not announce anything', async () => {
  await listMaestros('sucursales');
  expect(avisos).toBe(0);
});

it('a failed write does not announce anything', async () => {
  mockFetchJson.mockRejectedValue(new Error('422'));
  await expect(createMaestro('sucursales', {})).rejects.toThrow('422');
  expect(avisos).toBe(0);
});
