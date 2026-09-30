import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({
  listUsuarios: jest.fn().mockResolvedValue([]),
  listSolicitudesPendientes: jest.fn().mockResolvedValue([]),
  aprobarUsuario: jest.fn(),
  rechazarUsuario: jest.fn(),
  generarCodigoTelegram: jest.fn(),
  desvincularTelegram: jest.fn(),
  createUsuario: jest.fn(),
  deactivateUsuario: jest.fn(),
  reactivateUsuario: jest.fn(),
  resetPasswordUsuario: jest.fn(),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/usuarios',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div />;
  M.displayName = 'M';
  return M;
});

import UsuariosPage from '../app/motored/usuarios/page';

describe('Usuarios — SERVICIO_CLIENTE role option', () => {
  it('offers SERVICIO_CLIENTE with a readable label and an explicitly styled option', async () => {
    sessionStorage.setItem('motored_user', JSON.stringify({ id: 'a', nombre: 'Ad', role: 'ADMIN' }));
    sessionStorage.setItem('motored_token', 't');
    render(<UsuariosPage />);

    const option = await waitFor(() => {
      const el = screen.getByRole('option', { name: 'Servicio al cliente' });
      return el;
    });
    expect(option).toHaveValue('SERVICIO_CLIENTE');
    expect(option.style.color).toBe('rgb(26, 26, 24)');
    expect(screen.getByRole('option', { name: 'ADMIN' })).toBeInTheDocument();
  });
});
