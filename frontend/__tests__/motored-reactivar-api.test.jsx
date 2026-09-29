/**
 * API helpers for the "Reactivar" row action (odd/motored-acciones-con-iconos, T5).
 * Mocks `global.fetch` directly, same convention as `motored-referencias-api.test.jsx`.
 */
import { reactivateMaestro, reactivateUsuario } from '../lib/motored/api';
import { MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

const BASE = 'http://localhost:8000/api/motored';

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
});

it('reactivateMaestro POSTs to /maestros/{entidad}/{id}/reactivar', async () => {
  await reactivateMaestro('sucursales', 's1');

  expect(global.fetch.mock.calls[0][0]).toBe(`${BASE}/maestros/sucursales/s1/reactivar`);
  expect(global.fetch.mock.calls[0][1].method).toBe('POST');
});

it('reactivateUsuario POSTs to /usuarios/{id}/reactivar', async () => {
  await reactivateUsuario('u1');

  expect(global.fetch.mock.calls[0][0]).toBe(`${BASE}/usuarios/u1/reactivar`);
  expect(global.fetch.mock.calls[0][1].method).toBe('POST');
});
