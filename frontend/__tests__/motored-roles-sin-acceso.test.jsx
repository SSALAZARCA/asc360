/**
 * Owner decision 2026-10-05: SUCURSAL and CONSULTA have no screens yet.
 * They see only "Cambiar mi contraseña", land on the account page after
 * login (or after the forced first-login change) and read a short notice
 * there. The backend answers 403 everywhere else; this is the UX side.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
const mockLogin = jest.fn();
let mockPathname = '/motored/mi-cuenta';

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
  estadoTelegram: () => Promise.resolve({ telegram_vinculado: false }),
}));
jest.mock('../app/motored/motored-layout', () => {
  const Layout = ({ children }) => <div>{children}</div>;
  Layout.displayName = 'MockMotoredLayout';
  return Layout;
});

import MotoredSidebar, { menuItemsFor } from '../components/motored/MotoredSidebar';
import MotoredLoginPage from '../app/motored/login/page';
import MiCuentaPage from '../app/motored/mi-cuenta/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';
import {
  ACCESO_NO_HABILITADO_NOTICE, MI_CUENTA_PATH, ROLES_SIN_ACCESO, homePathFor, landingPathFor, rolSinAcceso,
} from '../lib/motored/session';

const BLOCKED = ['SUCURSAL', 'CONSULTA'];
const WITH_SCREENS = ['ADMIN', 'COMPRAS', 'GERENCIA', 'SERVICIO_CLIENTE'];
const pagesOf = (role) => menuItemsFor({ role }).flatMap((i) => i.children || [i]).map((i) => i.id);

const RealMotoredLayout = jest.requireActual('../app/motored/motored-layout').default;

beforeEach(() => {
  mockPathname = '/motored/mi-cuenta';
  pushMock.mockClear();
  mockLogin.mockReset();
  sessionStorage.clear();
});

describe('roles without screens - constants', () => {
  it('blocks exactly SUCURSAL and CONSULTA', () => {
    expect([...ROLES_SIN_ACCESO].sort()).toEqual([...BLOCKED].sort());
    BLOCKED.forEach((role) => expect(rolSinAcceso(role)).toBe(true));
    WITH_SCREENS.forEach((role) => expect(rolSinAcceso(role)).toBe(false));
  });

  it('uses the owner notice text', () => {
    expect(ACCESO_NO_HABILITADO_NOTICE).toBe('Tu acceso todavía no está habilitado');
  });
});

describe('roles without screens - sidebar', () => {
  it.each(BLOCKED)('%s sees only "Cambiar mi contraseña"', (role) => {
    expect(pagesOf(role)).toEqual(['mi-cuenta']);
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    const labels = screen.getAllByRole('button').map((b) => b.textContent).filter((t) => !t.includes('Salir'));
    expect(labels).toEqual(['Cambiar mi contraseña']);
  });

  it.each(BLOCKED)('%s still sees only the account page during a forced change', (role) => {
    expect(pagesOf(role)).toEqual(menuItemsFor({ role, must_change_password: true }).map((i) => i.id));
  });

  it.each(['ADMIN', 'COMPRAS', 'GERENCIA'])('%s keeps Maestros', (role) => {
    expect(pagesOf(role)).toContain('maestros');
  });

  it.each(['SERVICIO_CLIENTE', 'ASESOR_MOSTRADOR', ...BLOCKED])('%s does not see Maestros', (role) => {
    expect(pagesOf(role)).not.toContain('maestros');
  });
});

describe('roles without screens - landing', () => {
  it.each(BLOCKED)('%s lands on the account page', (role) => {
    expect(homePathFor(role)).toBe(MI_CUENTA_PATH);
    expect(landingPathFor({ role })).toBe(MI_CUENTA_PATH);
  });

  it.each(BLOCKED)('login sends %s to the account page', async (role) => {
    mockLogin.mockResolvedValue({ access_token: 't', user: { role } });
    const { container } = render(<MotoredLoginPage />);
    fireEvent.change(container.querySelector('input[type="email"]'), { target: { value: 'a@b.co' } });
    fireEvent.change(container.querySelector('input[type="password"]'), { target: { value: 'pw' } });
    fireEvent.submit(container.querySelector('form'));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith(MI_CUENTA_PATH));
  });
});

describe('roles without screens - account page notice', () => {
  const renderAs = (role) => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre: 'U', role }));
    render(<MiCuentaPage />);
  };

  it.each(BLOCKED)('shows the notice to %s', (role) => {
    renderAs(role);
    expect(screen.getByText(ACCESO_NO_HABILITADO_NOTICE)).toBeInTheDocument();
    expect(screen.getByText('Cambiar mi contraseña', { selector: 'h1' })).toBeInTheDocument();
  });

  it.each(WITH_SCREENS)('hides the notice from %s', (role) => {
    renderAs(role);
    expect(screen.queryByText(ACCESO_NO_HABILITADO_NOTICE)).not.toBeInTheDocument();
  });
});

describe('roles without screens - layout gate', () => {
  const renderLayoutAs = (role, path) => {
    mockPathname = path;
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ nombre: 'U', role }));
    render(<RealMotoredLayout><div>Contenido protegido</div></RealMotoredLayout>);
  };

  it.each(BLOCKED)('redirects %s from /motored/maestros to the account page', async (role) => {
    renderLayoutAs(role, '/motored/maestros');
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith(MI_CUENTA_PATH));
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
  });

  it.each(BLOCKED)('lets %s stay on the account page', async (role) => {
    renderLayoutAs(role, MI_CUENTA_PATH);
    expect(await screen.findByText('Contenido protegido')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('keeps COMPRAS on /motored/maestros', async () => {
    renderLayoutAs('COMPRAS', '/motored/maestros');
    expect(await screen.findByText('Contenido protegido')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
