/**
 * GERENCIA role (budgets/management, T1): valid session role, lands on the
 * advisor dashboard, sees only the dashboard (plus account), is offered when
 * creating users, and never bounces into a screen the backend would 403.
 * The backend is the real enforcement; these guards are UX only.
 */
import React from 'react';
import { render, screen, waitFor, renderHook } from '@testing-library/react';

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

  it('lands on the advisor dashboard after login and after a forced change', () => {
    expect(homePathFor('GERENCIA')).toBe(TABLERO_PATH);
    expect(landingPathFor({ role: 'GERENCIA' })).toBe(TABLERO_PATH);
  });

  it('keeps the other roles landing on Maestros', () => {
    for (const role of ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA']) {
      expect(homePathFor(role)).toBe('/motored/maestros');
    }
  });
});

describe('GERENCIA sidebar', () => {
  it('shows the dashboard and the account page only', () => {
    render(<MotoredSidebar user={{ nombre: 'G', role: 'GERENCIA' }} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent.trim());

    expect(labels).toEqual(['Tablero asesores', 'Cambiar mi contraseña', 'Salir']);
  });

  it.each(['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'ASESOR_MOSTRADOR'])('keeps Maestros for %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    expect(screen.getByRole('button', { name: 'Maestros' })).toBeInTheDocument();
  });

  it('keeps Maestros hidden from SERVICIO_CLIENTE', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'SERVICIO_CLIENTE' }} />);
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

describe('gates never loop GERENCIA through Maestros', () => {
  it.each([
    ['useAdminGate', useAdminGate],
    ['usePedidosGate', usePedidosGate],
    ['useDetractoresGate', useDetractoresGate],
  ])('%s sends GERENCIA to the dashboard', async (_name, hook) => {
    login('GERENCIA');
    renderHook(() => hook());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith(TABLERO_PATH));
    expect(pushMock).not.toHaveBeenCalledWith('/motored/maestros');
  });
});
