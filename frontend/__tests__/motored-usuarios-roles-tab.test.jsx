/** Usuarios page: a "Roles y permisos" tab next to the user management, ADMIN only page. */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({
  listUsuarios: jest.fn().mockResolvedValue([]),
  listSolicitudesPendientes: jest.fn().mockResolvedValue([]),
  aprobarUsuario: jest.fn(), rechazarUsuario: jest.fn(), generarCodigoTelegram: jest.fn(),
  desvincularTelegram: jest.fn(), createUsuario: jest.fn(), deactivateUsuario: jest.fn(),
  reactivateUsuario: jest.fn(), resetPasswordUsuario: jest.fn(),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/usuarios',
}));
jest.mock('../components/motored/MotoredSidebar', () => ({
  __esModule: true,
  ...jest.requireActual('../components/motored/MotoredSidebar'),
  default: () => <div />,
}));

import UsuariosPage from '../app/motored/usuarios/page';

beforeEach(() => {
  sessionStorage.setItem('motored_user', JSON.stringify({ id: 'a', nombre: 'Ad', role: 'ADMIN' }));
  sessionStorage.setItem('motored_token', 't');
});

it('shows user management first and the matrix after choosing the tab', async () => {
  render(<UsuariosPage />);

  const tab = await screen.findByRole('tab', { name: 'Roles y permisos' });
  expect(screen.getByRole('tab', { name: 'Gestión de usuarios' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.queryByRole('table', { name: /Roles y permisos/ })).toBeNull();

  fireEvent.click(tab);

  expect(await screen.findByRole('table', { name: /Roles y permisos/ })).toBeInTheDocument();
  expect(tab).toHaveAttribute('aria-selected', 'true');
  await waitFor(() => expect(screen.queryByText('Solicitudes pendientes')).toBeNull());
});
