/**
 * Forced password change (T8): login routing, layout guard, banner, success
 * redirect, sidebar reduction and the PASSWORD_CHANGE_REQUIRED 403 handling.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
const mockLogin = jest.fn();
const mockChange = jest.fn();
let mockPathname = '/motored/maestros';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));
jest.mock('next/image', () => {
  const MockImage = (props) => <span data-testid="img" data-alt={props.alt} />;
  MockImage.displayName = 'MockImage';
  return MockImage;
});
jest.mock('../lib/motored/api', () => ({
  login: (...a) => mockLogin(...a),
  changeOwnPassword: (...a) => mockChange(...a),
  estadoTelegram: () => new Promise(() => {}),
}));

import MotoredLoginPage from '../app/motored/login/page';
import MotoredLayout from '../app/motored/motored-layout';
import MotoredSidebar from '../components/motored/MotoredSidebar';
import MiCuentaContainer from '../components/motored/mi-cuenta/MiCuentaContainer';
import { motoredFetch, MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const BANNER = 'Por seguridad, debes cambiar tu contraseña antes de continuar.';

function setSession(user) {
  sessionStorage.setItem(MOTORED_TOKEN_KEY, 'tok');
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify(user));
}

beforeEach(() => {
  pushMock.mockClear();
  mockLogin.mockReset();
  mockChange.mockReset();
  sessionStorage.clear();
  mockPathname = '/motored/maestros';
});

describe('login routing', () => {
  async function loginAs(user) {
    mockLogin.mockResolvedValue({ access_token: 't', user });
    const { container } = render(<MotoredLoginPage />);
    fireEvent.change(container.querySelector('input[type="email"]'), { target: { value: 'a@b.co' } });
    fireEvent.change(container.querySelector('input[type="password"]'), { target: { value: 'pw' } });
    fireEvent.submit(container.querySelector('form'));
    await waitFor(() => expect(pushMock).toHaveBeenCalled());
  }

  it.each(['ADMIN', 'SERVICIO_CLIENTE'])('sends %s to mi-cuenta while the flag is set', async (role) => {
    await loginAs({ role, must_change_password: true });
    expect(pushMock).toHaveBeenCalledWith('/motored/mi-cuenta');
  });

  it('keeps the normal landing when the flag is false', async () => {
    await loginAs({ role: 'COMPRAS', must_change_password: false });
    expect(pushMock).toHaveBeenCalledWith('/motored/inicio');
  });
});

describe('layout guard', () => {
  it('redirects any other page to mi-cuenta while the flag is set', async () => {
    setSession({ nombre: 'U', role: 'COMPRAS', must_change_password: true });
    render(<MotoredLayout><div>Contenido protegido</div></MotoredLayout>);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/mi-cuenta'));
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });

  it('lets mi-cuenta render while the flag is set', async () => {
    mockPathname = '/motored/mi-cuenta';
    setSession({ nombre: 'U', role: 'SERVICIO_CLIENTE', must_change_password: true });
    render(<MotoredLayout><div>Pantalla cuenta</div></MotoredLayout>);
    expect(await screen.findByText('Pantalla cuenta')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('does not interfere when the flag is false', async () => {
    setSession({ nombre: 'U', role: 'COMPRAS', must_change_password: false });
    render(<MotoredLayout><div>Contenido normal</div></MotoredLayout>);
    expect(await screen.findByText('Contenido normal')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});

describe('sidebar while the flag is set', () => {
  it('shows only the change-password entry and Salir', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'ADMIN', must_change_password: true }} />);
    expect(screen.getByText('Cambiar mi contraseña')).toBeInTheDocument();
    expect(screen.getByText('Salir')).toBeInTheDocument();
    expect(screen.queryByText('Maestros')).not.toBeInTheDocument();
    expect(screen.queryByText('Usuarios')).not.toBeInTheDocument();
  });
});

describe('mi-cuenta', () => {
  const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const change = (nueva = 'nueva-clave-22') => {
    fill('Contraseña actual', 'vieja-clave-1');
    fill('Nueva contraseña', nueva);
    fill('Confirmar nueva contraseña', nueva);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar contraseña' }));
  };

  it('shows the banner only while the flag is set', () => {
    setSession({ role: 'COMPRAS', must_change_password: true });
    const { unmount } = render(<MiCuentaContainer />);
    expect(screen.getByText(BANNER)).toBeInTheDocument();
    unmount();
    setSession({ role: 'COMPRAS', must_change_password: false });
    render(<MiCuentaContainer />);
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
  });

  it.each([['COMPRAS', '/motored/inicio'], ['SERVICIO_CLIENTE', '/motored/inicio']])(
    'after a forced change, stores the fresh session and goes home (%s)', async (role, home) => {
      setSession({ role, must_change_password: true });
      mockChange.mockResolvedValue({ access_token: 'fresh', user: { role, must_change_password: false } });
      render(<MiCuentaContainer />);
      change();
      await waitFor(() => expect(pushMock).toHaveBeenCalledWith(home));
      expect(sessionStorage.getItem(MOTORED_TOKEN_KEY)).toBe('fresh');
      expect(JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY)).must_change_password).toBe(false);
    },
  );

  it('does not redirect after a voluntary change', async () => {
    setSession({ role: 'COMPRAS', must_change_password: false });
    mockChange.mockResolvedValue({ access_token: 'fresh', user: { role: 'COMPRAS', must_change_password: false } });
    render(<MiCuentaContainer />);
    change();
    await screen.findByRole('status');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('checks letters and digits on the client without calling the API', () => {
    setSession({ role: 'COMPRAS', must_change_password: false });
    render(<MiCuentaContainer />);
    change('soloLetrasAqui');
    expect(screen.getByRole('alert')).toHaveTextContent('al menos un número');
    expect(mockChange).not.toHaveBeenCalled();
  });
});

const forbidden = (body) => ({
  ok: false, status: 403, json: () => Promise.resolve(body), clone: () => ({ json: () => Promise.resolve(body) }),
});

describe('PASSWORD_CHANGE_REQUIRED 403', () => {
  it('flags the stored user and notifies the layout', async () => {
    setSession({ role: 'COMPRAS', nombre: 'U', must_change_password: false });
    const events = jest.fn();
    window.addEventListener('storage', events);
    global.fetch = jest.fn().mockResolvedValue(forbidden({ detail: { code: 'PASSWORD_CHANGE_REQUIRED' } }));

    const res = await motoredFetch('/maestros/sucursales');

    expect(res.status).toBe(403);
    expect(JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY)).must_change_password).toBe(true);
    expect(sessionStorage.getItem(MOTORED_TOKEN_KEY)).toBe('tok');
    expect(events).toHaveBeenCalled();
    window.removeEventListener('storage', events);
  });

  it('leaves other 403s alone', async () => {
    setSession({ role: 'COMPRAS', must_change_password: false });
    global.fetch = jest.fn().mockResolvedValue(forbidden({ detail: 'No tiene permisos' }));
    await motoredFetch('/usuarios');
    expect(JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY)).must_change_password).toBe(false);
  });
});
