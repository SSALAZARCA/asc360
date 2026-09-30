/** Usuarios list: "Bloqueado hasta HH:MM" badge and the ADMIN "Desbloquear" action (T9). */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockListUsuarios = jest.fn();
const mockDesbloquear = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listUsuarios: (...a) => mockListUsuarios(...a),
  listSolicitudesPendientes: jest.fn().mockResolvedValue([]),
  desbloquearUsuario: (...a) => mockDesbloquear(...a),
}));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }), usePathname: () => '/motored/usuarios' }));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div />;
  M.displayName = 'M';
  return M;
});

import UsuariosPage from '../app/motored/usuarios/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const base = { role: 'COMPRAS', activo: true, status: 'approved', phone: null, telegram_vinculado: false };
const LOCKED = { ...base, id: 'u1', nombre: 'Luisa Bloqueada', email: 'l@x.co', bloqueado_hasta: '2099-01-01T20:45:00+00:00' };
const FREE = { ...base, id: 'u2', nombre: 'Pedro Libre', email: 'p@x.co', bloqueado_hasta: null };

beforeEach(() => {
  mockListUsuarios.mockReset().mockResolvedValue([LOCKED, FREE]);
  mockDesbloquear.mockReset().mockResolvedValue({ ...LOCKED, bloqueado_hasta: null });
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'admin', role: 'ADMIN' }));
});

describe('UsuariosPage lockout', () => {
  it('shows the badge in Colombia time only for the locked user', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Luisa Bloqueada')).toBeInTheDocument());
    expect(screen.getAllByText(/Bloqueado hasta/)).toHaveLength(1);
    expect(screen.getByText(/Bloqueado hasta 15:45/)).toBeInTheDocument(); // 20:45 UTC = 15:45 Bogota
  });

  it('offers Desbloquear only on the locked row and reloads after it', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Luisa Bloqueada')).toBeInTheDocument());
    const buttons = screen.getAllByRole('button', { name: 'Desbloquear' });
    expect(buttons).toHaveLength(1);

    fireEvent.click(buttons[0]);

    await waitFor(() => expect(mockDesbloquear).toHaveBeenCalledWith('u1'));
    await waitFor(() => expect(mockListUsuarios).toHaveBeenCalledTimes(2));
  });
});
