/**
 * `aplicarCarga` runs synchronously on the server: a real monthly VENTAS file
 * (~43k rows) takes longer than the default 30 s request timeout, and the
 * browser aborted while the server kept applying. The apply call must wait
 * minutes, not seconds.
 */
import { aplicarCarga } from '../lib/motored/api';
import { MOTORED_TOKEN_KEY } from '../lib/motored/motoredFetch';

beforeEach(() => {
  jest.useFakeTimers();
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'fake-token');
  global.fetch = jest.fn(() => new Promise(() => {}));
});

afterEach(() => {
  jest.useRealTimers();
});

it('does not abort the apply request after the default 30 seconds', () => {
  aplicarCarga('carga-1');
  const { signal } = global.fetch.mock.calls[0][1];

  jest.advanceTimersByTime(60 * 1000);

  expect(signal.aborted).toBe(false);
});

it('still aborts the apply request eventually', () => {
  aplicarCarga('carga-1');
  const { signal } = global.fetch.mock.calls[0][1];

  jest.advanceTimersByTime(11 * 60 * 1000);

  expect(signal.aborted).toBe(true);
});

it('asks the server to confirm the purge only when told to', () => {
  aplicarCarga('carga-1', { confirmarVaciado: true });
  aplicarCarga('carga-2');

  expect(global.fetch.mock.calls[0][0]).toMatch(/\/cargas\/carga-1\/aplicar\?confirmar_vaciado=true$/);
  expect(global.fetch.mock.calls[1][0]).toMatch(/\/cargas\/carga-2\/aplicar$/);
});
