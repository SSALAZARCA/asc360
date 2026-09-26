/**
 * Tests for `lib/motored/useAdminGate.js` (sdd/motored-ventas-perdidas-panel,
 * Phase 5, tasks 5.1/5.2; design D6).
 *
 * This hook is a byte-for-byte extraction of the local `useAdminGate` that
 * already lives inline in `app/motored/usuarios/page.js` (lines 149-171 at
 * extraction time): reads `MOTORED_USER_KEY` from sessionStorage, redirects
 * to `/motored/maestros` when the parsed role isn't `'ADMIN'` (including a
 * missing session or invalid JSON), and otherwise exposes `{ allowed: true,
 * ownUserId }`. `usuarios/page.js` itself is NOT changed to consume this
 * hook in this phase (design D6's own explicit, accepted duplication) --
 * this suite only covers the NEW shared hook file.
 */
import { renderHook, waitFor } from '@testing-library/react';
import useAdminGate from '../lib/motored/useAdminGate';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const pushMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

beforeEach(() => {
  pushMock.mockClear();
  sessionStorage.clear();
});

describe('useAdminGate', () => {
  it('redirects a non-ADMIN user to /motored/maestros and never allows the gate open', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'u-1', role: 'COMPRAS' }));

    const { result } = renderHook(() => useAdminGate());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(result.current.allowed).toBe(false);
    expect(result.current.ownUserId).toBeNull();
  });

  it('redirects when there is no Motored session at all', async () => {
    const { result } = renderHook(() => useAdminGate());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(result.current.allowed).toBe(false);
  });

  it('redirects on invalid JSON in sessionStorage instead of throwing', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, '{not-json');

    const { result } = renderHook(() => useAdminGate());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(result.current.allowed).toBe(false);
  });

  it('allows an ADMIN through and exposes ownUserId, without redirecting', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'admin-1', role: 'ADMIN' }));

    const { result } = renderHook(() => useAdminGate());

    await waitFor(() => expect(result.current.allowed).toBe(true));
    expect(result.current.ownUserId).toBe('admin-1');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('exposes ownUserId=null for an ADMIN session missing an id', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'ADMIN' }));

    const { result } = renderHook(() => useAdminGate());

    await waitFor(() => expect(result.current.allowed).toBe(true));
    expect(result.current.ownUserId).toBeNull();
  });
});
