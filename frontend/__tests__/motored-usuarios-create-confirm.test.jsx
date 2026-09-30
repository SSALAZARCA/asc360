/** Create-user form: confirm-password must match before submit (T4). */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockCreateUsuario = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listUsuarios: jest.fn().mockResolvedValue([]),
  listSolicitudesPendientes: jest.fn().mockResolvedValue([]),
  createUsuario: (...a) => mockCreateUsuario(...a),
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

beforeEach(() => {
  mockCreateUsuario.mockReset().mockResolvedValue({});
  sessionStorage.setItem('motored_user', JSON.stringify({ id: 'a1', role: 'ADMIN', nombre: 'Ad' }));
});

async function fill(pw, confirm) {
  render(<UsuariosPage />);
  await screen.findByRole('button', { name: 'Crear usuario' });
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Ana' } });
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ana@x.co' } });
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: pw } });
  fireEvent.change(screen.getByLabelText('Confirmar contraseña del usuario'), { target: { value: confirm } });
  fireEvent.click(screen.getByRole('button', { name: 'Crear usuario' }));
}

describe('create-user password fields', () => {
  it('blocks submit when confirmation differs', async () => {
    await fill('abcdefgh', 'abcdefgX');
    expect(await screen.findByRole('alert')).toHaveTextContent('Las contraseñas no coinciden');
    expect(mockCreateUsuario).not.toHaveBeenCalled();
  });

  it('submits when both match and sends only the password', async () => {
    await fill('abcdefgh', 'abcdefgh');
    await waitFor(() => expect(mockCreateUsuario).toHaveBeenCalled());
    expect(mockCreateUsuario.mock.calls[0][0]).toEqual(
      expect.objectContaining({ password: 'abcdefgh', email: 'ana@x.co' }),
    );
    expect(mockCreateUsuario.mock.calls[0][0]).not.toHaveProperty('confirmacion');
  });

  it('has hint, maxLength, autocomplete and toggle', async () => {
    render(<UsuariosPage />);
    const pw = await screen.findByLabelText('Contraseña');
    expect(pw).toHaveAttribute('autocomplete', 'new-password');
    expect(pw).toHaveAttribute('maxlength', '72');
    expect(screen.getByText(/Mínimo 8 caracteres/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Mostrar/ }).length).toBeGreaterThanOrEqual(2);
  });
});
