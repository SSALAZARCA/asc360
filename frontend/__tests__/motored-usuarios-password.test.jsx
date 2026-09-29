/**
 * Usuarios screen: "Cambiar contraseña" action (ADMIN resets the password
 * of a user with web access) -- feature odd/motored-salir-y-cambio-password, T3.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListUsuarios = jest.fn();
const mockListSolicitudesPendientes = jest.fn();
const mockResetPasswordUsuario = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listUsuarios: (...args) => mockListUsuarios(...args),
  listSolicitudesPendientes: (...args) => mockListSolicitudesPendientes(...args),
  resetPasswordUsuario: (...args) => mockResetPasswordUsuario(...args),
  createUsuario: jest.fn(),
  deactivateUsuario: jest.fn(),
  aprobarUsuario: jest.fn(),
  rechazarUsuario: jest.fn(),
  generarCodigoTelegram: jest.fn(),
  desvincularTelegram: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/usuarios',
}));

jest.mock('../components/motored/MotoredSidebar', () => {
  const MockMotoredSidebar = () => <div data-testid="mock-motored-sidebar" />;
  MockMotoredSidebar.displayName = 'MockMotoredSidebar';
  return MockMotoredSidebar;
});

import UsuariosPage from '../app/motored/usuarios/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const ADMIN = {
  id: 'admin-1', nombre: 'Ana Admin', email: 'ana@x.com', role: 'ADMIN',
  activo: true, status: 'approved', telegram_vinculado: false,
};
const COMPRAS = {
  id: 'compras-1', nombre: 'Carla Compras', email: 'carla@x.com', role: 'COMPRAS',
  activo: true, status: 'approved', telegram_vinculado: false,
};
const ASESOR = {
  id: 'asesor-1', nombre: 'Juan Asesor', email: null, role: 'ASESOR_MOSTRADOR',
  activo: true, status: 'approved', telegram_vinculado: true,
};

const NUEVA = 'nueva-clave-segura';

beforeEach(() => {
  mockListUsuarios.mockReset().mockResolvedValue([ADMIN, COMPRAS, ASESOR]);
  mockListSolicitudesPendientes.mockReset().mockResolvedValue([]);
  mockResetPasswordUsuario.mockReset().mockResolvedValue(COMPRAS);
  pushMock.mockClear();
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'admin-1', nombre: 'Ana Admin', role: 'ADMIN' }));
});

async function abrirFormularioDe(nombre) {
  render(<UsuariosPage />);
  await waitFor(() => expect(screen.getByText(nombre)).toBeInTheDocument());
  const fila = screen.getByText(nombre).closest('tr');
  fireEvent.click(within(fila).getByRole('button', { name: 'Cambiar contraseña' }));
}

function completar(nueva, confirmar) {
  fireEvent.change(screen.getByLabelText('Nueva contraseña'), { target: { value: nueva } });
  fireEvent.change(screen.getByLabelText('Confirmar contraseña'), { target: { value: confirmar } });
}

describe('UsuariosPage — cambiar contraseña', () => {
  it('offers the action on rows with web access, not on rows without email', async () => {
    render(<UsuariosPage />);
    await waitFor(() => expect(screen.getByText('Carla Compras')).toBeInTheDocument());

    const filaCompras = screen.getByText('Carla Compras').closest('tr');
    const filaAdmin = screen.getByText('Ana Admin').closest('tr');
    const filaAsesor = screen.getByText('Juan Asesor').closest('tr');

    expect(within(filaCompras).getByRole('button', { name: 'Cambiar contraseña' })).toBeInTheDocument();
    expect(within(filaAdmin).getByRole('button', { name: 'Cambiar contraseña' })).toBeInTheDocument();
    expect(within(filaAsesor).queryByRole('button', { name: 'Cambiar contraseña' })).not.toBeInTheDocument();
  });

  it('opens a form with two password inputs that start empty', async () => {
    await abrirFormularioDe('Carla Compras');

    expect(screen.getByLabelText('Nueva contraseña')).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText('Confirmar contraseña')).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText('Nueva contraseña')).toHaveValue('');
    expect(screen.getByLabelText('Confirmar contraseña')).toHaveValue('');
  });

  it('rejects a password shorter than 8 characters without calling the API', async () => {
    await abrirFormularioDe('Carla Compras');

    completar('corta', 'corta');
    fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));

    expect(screen.getByText(/al menos 8 caracteres/)).toBeInTheDocument();
    expect(mockResetPasswordUsuario).not.toHaveBeenCalled();
  });

  it('rejects mismatched passwords without calling the API', async () => {
    await abrirFormularioDe('Carla Compras');

    completar(NUEVA, 'otra-clave-distinta');
    fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));

    expect(screen.getByText(/no coinciden/)).toBeInTheDocument();
    expect(mockResetPasswordUsuario).not.toHaveBeenCalled();
  });

  it('sends the new password for the chosen user, then confirms and clears the form', async () => {
    await abrirFormularioDe('Carla Compras');

    completar(NUEVA, NUEVA);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));

    await waitFor(() => expect(mockResetPasswordUsuario).toHaveBeenCalledWith('compras-1', NUEVA));
    await waitFor(() => expect(screen.getByText(/Contraseña actualizada/)).toBeInTheDocument());
    expect(screen.queryByLabelText('Nueva contraseña')).not.toBeInTheDocument();
    expect(screen.queryByText(NUEVA)).not.toBeInTheDocument();
  });

  it('shows the server error and never echoes the password', async () => {
    mockResetPasswordUsuario.mockRejectedValue(new Error('Usuario no encontrado'));
    await abrirFormularioDe('Carla Compras');

    completar(NUEVA, NUEVA);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));

    await waitFor(() => expect(screen.getByText('Usuario no encontrado')).toBeInTheDocument());
    expect(screen.queryByText(new RegExp(NUEVA))).not.toBeInTheDocument();
  });

  it('Cancelar closes the form without calling the API', async () => {
    await abrirFormularioDe('Carla Compras');

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(screen.queryByLabelText('Nueva contraseña')).not.toBeInTheDocument();
    expect(mockResetPasswordUsuario).not.toHaveBeenCalled();
  });
});
