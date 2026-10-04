/** Motored "Mi cuenta": change own password (T3). */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockChange = jest.fn();
jest.mock('../lib/motored/api', () => ({
  changeOwnPassword: (...a) => mockChange(...a),
  // The Telegram panel (ADMIN/COMPRAS) reads its state on mount; this suite does not care about it.
  estadoTelegram: () => new Promise(() => {}),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/mi-cuenta',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const Mock = () => <div />;
  Mock.displayName = 'MockSidebar';
  return Mock;
});

import MiCuentaContainer from '../components/motored/mi-cuenta/MiCuentaContainer';
import MiCuentaPage from '../app/motored/mi-cuenta/page';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../lib/motored/motoredFetch';
import { isServicioClientePath } from '../lib/motored/servicioCliente';

const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));

function fillAll(actual = 'vieja-clave-1', nueva = 'nueva-clave-22', confirm = nueva) {
  fill('Contraseña actual', actual);
  fill('Nueva contraseña', nueva);
  fill('Confirmar nueva contraseña', confirm);
}

beforeEach(() => {
  mockChange.mockReset();
  sessionStorage.clear();
});

describe('MiCuentaContainer', () => {
  it('uses the right autocomplete, maxLength and password type on every field', () => {
    render(<MiCuentaContainer />);
    const actual = screen.getByLabelText('Contraseña actual');
    const nueva = screen.getByLabelText('Nueva contraseña');
    expect(actual).toHaveAttribute('autocomplete', 'current-password');
    expect(nueva).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('Confirmar nueva contraseña')).toHaveAttribute('autocomplete', 'new-password');
    [actual, nueva].forEach((i) => {
      expect(i).toHaveAttribute('type', 'password');
      expect(i).toHaveAttribute('maxLength', '72');
    });
    expect(screen.getByText(/Mínimo 10 caracteres, con letras y números\./i)).toBeInTheDocument();
  });

  it('toggles visibility per field', () => {
    render(<MiCuentaContainer />);
    const nueva = screen.getByLabelText('Nueva contraseña');
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar Nueva contraseña' }));
    expect(nueva).toHaveAttribute('type', 'text');
    expect(screen.getByLabelText('Contraseña actual')).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar Nueva contraseña' }));
    expect(nueva).toHaveAttribute('type', 'password');
  });

  it('rejects a mismatch without calling the API', () => {
    render(<MiCuentaContainer />);
    fillAll('vieja-clave-1', 'nueva-clave-22', 'otra-distinta-33');
    submit();
    expect(screen.getByRole('alert')).toHaveTextContent('Las contraseñas no coinciden');
    expect(mockChange).not.toHaveBeenCalled();
  });

  it('rejects a short new password without calling the API', () => {
    render(<MiCuentaContainer />);
    fillAll('vieja-clave-1', 'corta', 'corta');
    submit();
    expect(screen.getByRole('alert')).toHaveTextContent('al menos 10 caracteres');
    expect(mockChange).not.toHaveBeenCalled();
  });

  it('stores the fresh token and user, shows success and clears the fields', async () => {
    mockChange.mockResolvedValue({ access_token: 'fresh-token', user: { id: 'u1', role: 'COMPRAS', nombre: 'Carla' } });
    render(<MiCuentaContainer />);
    fillAll();
    submit();
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Contraseña actualizada'));
    expect(mockChange).toHaveBeenCalledWith('vieja-clave-1', 'nueva-clave-22');
    expect(sessionStorage.getItem(MOTORED_TOKEN_KEY)).toBe('fresh-token');
    expect(JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY)).nombre).toBe('Carla');
    expect(screen.getByLabelText('Nueva contraseña')).toHaveValue('');
  });

  it('shows the server error in an alert and keeps the session untouched', async () => {
    mockChange.mockRejectedValue(new Error('La contraseña actual no es correcta.'));
    sessionStorage.setItem(MOTORED_TOKEN_KEY, 'old-token');
    render(<MiCuentaContainer />);
    fillAll();
    submit();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('La contraseña actual no es correcta.'));
    expect(sessionStorage.getItem(MOTORED_TOKEN_KEY)).toBe('old-token');
  });
});

describe('navigation wiring', () => {
  it('lets SERVICIO_CLIENTE open the account page', () => {
    expect(isServicioClientePath('/motored/mi-cuenta')).toBe(true);
  });

  it('renders the page inside the layout for an authenticated user', async () => {
    sessionStorage.setItem(MOTORED_TOKEN_KEY, 't');
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'SERVICIO_CLIENTE', nombre: 'S' }));
    render(<MiCuentaPage />);
    expect(await screen.findByLabelText('Contraseña actual')).toBeInTheDocument();
  });
});
