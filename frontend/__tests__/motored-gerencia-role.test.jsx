/**
 * GERENCIA role (budgets/management, T1/T3): valid session role, lands on
 * Maestros (Presupuestos), sees Maestros and the dashboard (plus account), is offered when
 * creating users, and never bounces into a screen the backend would 403.
 * The backend is the real enforcement; these guards are UX only.
 */
import React from 'react';
import { render, screen, waitFor, renderHook, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/tablero-asesores';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

import MotoredLayout from '../app/motored/motored-layout';
import MotoredSidebar from '../components/motored/MotoredSidebar';
import UsuarioCreateForm from '../components/motored/UsuarioCreateForm';
import { homePathFor, landingPathFor } from '../lib/motored/session';
import useAdminGate from '../lib/motored/useAdminGate';
import usePedidosGate from '../lib/motored/usePedidosGate';
import useDetractoresGate from '../lib/motored/useDetractoresGate';

const TABLERO_PATH = '/motored/tablero-asesores';
const MAESTROS_PATH = '/motored/maestros';

function login(role, extra = {}) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'G', role, ...extra }));
  sessionStorage.setItem('motored_token', 'tok');
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = TABLERO_PATH;
});

describe('GERENCIA session', () => {
  it('is a valid layout role (a missing role would wipe the session)', async () => {
    login('GERENCIA');
    render(<MotoredLayout><div>Contenido tablero</div></MotoredLayout>);

    expect(await screen.findByText('Contenido tablero')).toBeInTheDocument();
    expect(sessionStorage.getItem('motored_user')).not.toBeNull();
    expect(pushMock).not.toHaveBeenCalledWith('/motored/login');
  });

  it('lands on Maestros (Presupuestos) after login and after a forced change', () => {
    expect(homePathFor('GERENCIA')).toBe(MAESTROS_PATH);
    expect(landingPathFor({ role: 'GERENCIA' })).toBe(MAESTROS_PATH);
  });

  it('keeps the other roles landing on Maestros', () => {
    for (const role of ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA']) {
      expect(homePathFor(role)).toBe('/motored/maestros');
    }
  });
});

describe('GERENCIA sidebar', () => {
  it('shows Maestros, the dashboard and the account page only', () => {
    render(<MotoredSidebar user={{ nombre: 'G', role: 'GERENCIA' }} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent.trim());

    expect(labels).toEqual(["KPI's", 'Pedidos', 'Cambiar mi contraseña', 'Salir']);
    fireEvent.click(screen.getByRole('button', { name: 'Pedidos' }));
    const opened = screen.getAllByRole('button').map((b) => b.textContent.trim());
    expect(opened).toEqual(["KPI's", 'Pedidos', 'Maestros', 'Cambiar mi contraseña', 'Salir']);
  });

  it.each(['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'ASESOR_MOSTRADOR'])('keeps Maestros for %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pedidos' }));
    expect(screen.getByRole('button', { name: 'Maestros' })).toBeInTheDocument();
  });

  it('keeps Maestros hidden from SERVICIO_CLIENTE', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'SERVICIO_CLIENTE' }} />);
    expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Maestros' })).not.toBeInTheDocument();
  });
});

describe('GERENCIA in the create-user form', () => {
  it('offers a Gerencia option with an explicit style (dark theme)', () => {
    render(<UsuarioCreateForm onCreate={jest.fn()} />);
    const option = screen.getByRole('option', { name: 'Gerencia' });

    expect(option).toHaveValue('GERENCIA');
    expect(option.style.color).toBe('rgb(26, 26, 24)');
  });
});

describe('gates send GERENCIA to its home (Maestros, which has no gate)', () => {
  it.each([
    ['useAdminGate', useAdminGate],
    ['usePedidosGate', usePedidosGate],
    ['useDetractoresGate', useDetractoresGate],
  ])('%s sends GERENCIA to Maestros', async (_name, hook) => {
    login('GERENCIA');
    renderHook(() => hook());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith(MAESTROS_PATH));
  });
});
