import { renderHook, waitFor } from '@testing-library/react';
import useAdminGate from '../lib/motored/useAdminGate';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: pushMock }) }));

beforeEach(() => {
  pushMock.mockClear();
  sessionStorage.clear();
});

describe('useAdminGate — SERVICIO_CLIENTE', () => {
  it('sends SERVICIO_CLIENTE to the survey page, not to a forbidden page', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'u', role: 'SERVICIO_CLIENTE' }));
    const { result } = renderHook(() => useAdminGate());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/encuesta-satisfaccion'));
    expect(pushMock).not.toHaveBeenCalledWith('/motored/maestros');
    expect(result.current.allowed).toBe(false);
  });
});
