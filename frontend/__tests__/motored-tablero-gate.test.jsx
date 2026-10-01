/**
 * The dashboard has its own gate (ADMIN and COMPRAS). It must not follow
 * `usePedidosGate`: opening Pedidos to another role is a separate decision.
 */
import React from 'react';
import { render, screen, renderHook, waitFor } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { TABLERO } from './helpers/tableroAsesoresFetch';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/tablero-asesores',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});
// Pedidos opens to EVERY role: the dashboard gate must not notice.
jest.mock('../lib/motored/usePedidosGate', () => ({
  __esModule: true,
  default: () => true,
  PEDIDOS_ROLES: ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA'],
}));

import useTableroGate, { TABLERO_ROLES } from '../components/motored/tablero-asesores/useTableroGate';
import TableroAsesoresPage from '../app/motored/tablero-asesores/page';

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('useTableroGate', () => {
  it('permite ADMIN y COMPRAS y nada más', () => {
    expect(TABLERO_ROLES).toEqual(['ADMIN', 'COMPRAS']);
  });

  it.each(['ADMIN', 'COMPRAS'])('deja pasar a %s', async (role) => {
    setSession(role);
    const { result } = renderHook(() => useTableroGate());
    await waitFor(() => expect(result.current).toBe(true));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it.each(['SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'])('manda a %s a Maestros', async (role) => {
    setSession(role);
    const { result } = renderHook(() => useTableroGate());
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(result.current).toBe(false);
  });

  it('sin sesión manda a Maestros', async () => {
    renderHook(() => useTableroGate());
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
  });
});

describe('Tablero de asesores no sigue al gate de Pedidos', () => {
  it('SUCURSAL sigue fuera aunque Pedidos se abra a todos los roles', async () => {
    setSession('SUCURSAL');
    const calls = installFetch({ 'GET /tablero-asesores': jsonRes(TABLERO) });
    render(<TableroAsesoresPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(calls).toHaveLength(0);
    expect(screen.queryByText('Ana Pérez')).not.toBeInTheDocument();
  });
});
