/**
 * LIDER_INVENTARIOS role and the "Conteos de inventario" page: valid
 * session role, lands on Conteos, is kept inside its pages, is offered when
 * creating users and has a readable name. While stage 1 is being built the
 * sidebar group "Inventarios" shows to ADMIN only. The list page
 * renders for ADMIN, LIDER_INVENTARIOS and GERENCIA; any other role goes
 * home. UX only: the backend is the real enforcement.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/inventarios/conteos';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));
// The list page asks for the conteos; an empty list is enough here.
jest.mock('../lib/motored/conteosApi', () => ({
  listarConteos: jest.fn(() => Promise.resolve([])),
  listarSucursalesConteo: jest.fn(() => Promise.resolve([])),
  listarLideres: jest.fn(() => Promise.resolve([])),
}));

import MotoredLayout, { VALID_ROLES } from '../app/motored/motored-layout';
import MotoredSidebar from '../components/motored/MotoredSidebar';
import UsuarioCreateForm from '../components/motored/UsuarioCreateForm';
import ConteosPage from '../app/motored/inventarios/conteos/page';
import {
  CONTEOS_PATH, CONTEOS_ROLES, CONTEOS_ROLES_VISIBLES, LIDER_INVENTARIOS, homePathFor,
  isLiderInventariosPath, landingPathFor,
} from '../lib/motored/session';
import { tienePermiso } from '../lib/motored/permisosPorRol';
import { ROL_NOMBRE } from '../components/motored/inicio/textos';

const ROLES_CONTEOS = ['ADMIN', 'LIDER_INVENTARIOS', 'GERENCIA'];
const OTROS_ROLES = ['COMPRAS', 'SERVICIO_CLIENTE', 'COORDINADOR_REPUESTOS', 'SUCURSAL', 'CONSULTA'];

function login(role, extra = {}) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'L', role, ...extra }));
  sessionStorage.setItem('motored_token', 'tok');
}

function sidebarLabels() {
  return screen.getAllByRole('button').map((b) => b.textContent.trim());
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = CONTEOS_PATH;
});

describe('LIDER_INVENTARIOS session', () => {
  it('exposes the role constant and accepts it in the layout', async () => {
    expect(LIDER_INVENTARIOS).toBe('LIDER_INVENTARIOS');
    expect(VALID_ROLES).toContain(LIDER_INVENTARIOS);
    login(LIDER_INVENTARIOS);

    render(<MotoredLayout><div>Contenido conteos</div></MotoredLayout>);

    expect(await screen.findByText('Contenido conteos')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('lands on Conteos after login', () => {
    expect(CONTEOS_PATH).toBe('/motored/inventarios/conteos');
    expect(homePathFor(LIDER_INVENTARIOS)).toBe(CONTEOS_PATH);
    expect(landingPathFor({ role: LIDER_INVENTARIOS })).toBe(CONTEOS_PATH);
  });

  it('still lands on the account page while a password change is pending', () => {
    expect(landingPathFor({ role: LIDER_INVENTARIOS, must_change_password: true }))
      .toBe('/motored/mi-cuenta');
  });

  it('allows the inventory pages and the account page only', () => {
    expect(isLiderInventariosPath('/motored/inventarios')).toBe(true);
    expect(isLiderInventariosPath('/motored/inventarios/conteos/123')).toBe(true);
    expect(isLiderInventariosPath('/motored/mi-cuenta')).toBe(true);
    expect(isLiderInventariosPath('/motored/inventarios-otra')).toBe(false);
    expect(isLiderInventariosPath('/motored/inicio')).toBe(false);
  });

  it.each([
    '/motored/inicio', '/motored/tablero-asesores', '/motored/maestros', '/motored/pedidos',
    '/motored/gestion-repuestos/ingresos-facturas', '/motored/usuarios', '/motored/configuracion',
  ])('is sent back to Conteos from %s', async (path) => {
    mockPathname = path;
    login(LIDER_INVENTARIOS);

    render(<MotoredLayout><div>Prohibido</div></MotoredLayout>);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith(CONTEOS_PATH));
    expect(screen.queryByText('Prohibido')).not.toBeInTheDocument();
  });

  it.each([CONTEOS_PATH, '/motored/mi-cuenta'])('may open %s', async (path) => {
    mockPathname = path;
    login(LIDER_INVENTARIOS);

    render(<MotoredLayout><div>Permitido</div></MotoredLayout>);

    expect(await screen.findByText('Permitido')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('has a readable role name', () => {
    expect(ROL_NOMBRE.LIDER_INVENTARIOS).toBe('Líder de inventarios');
  });
});

describe('sidebar while stage 1 is being built', () => {
  it('shows the Inventarios group to ADMIN only', () => {
    expect(CONTEOS_ROLES_VISIBLES).toEqual(['ADMIN']);
  });

  it('opens Inventarios > Conteos for ADMIN', () => {
    render(<MotoredSidebar user={{ nombre: 'A', role: 'ADMIN' }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Inventarios' }));
    fireEvent.click(screen.getByRole('button', { name: 'Conteos' }));
    expect(pushMock).toHaveBeenCalledWith(CONTEOS_PATH);
  });

  it.each(['LIDER_INVENTARIOS', 'GERENCIA', ...OTROS_ROLES])('hides Inventarios from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);

    expect(screen.queryByRole('button', { name: 'Inventarios' })).not.toBeInTheDocument();
  });

  it("shows LIDER_INVENTARIOS only its account page, never KPI's, Pedidos or Configuración", () => {
    render(<MotoredSidebar user={{ nombre: 'L', role: LIDER_INVENTARIOS }} />);

    expect(sidebarLabels()).toEqual(['Cambiar mi contraseña', 'Salir']);
  });

  it('matches the permission matrix', () => {
    ['ADMIN', 'LIDER_INVENTARIOS', 'GERENCIA', ...OTROS_ROLES].forEach((rol) => {
      expect(tienePermiso('conteos', rol)).toBe(rol === 'ADMIN');
    });
  });
});

describe('create-user form', () => {
  it('offers Líder de inventarios with an explicit option style', () => {
    render(<UsuarioCreateForm onCreate={jest.fn()} />);
    const option = screen.getByRole('option', { name: 'Líder de inventarios' });

    expect(option).toHaveValue('LIDER_INVENTARIOS');
    expect(option.style.color).toBe('rgb(26, 26, 24)');
  });
});

describe('Conteos list page', () => {
  it('is gated to ADMIN, LIDER_INVENTARIOS and GERENCIA', () => {
    expect(CONTEOS_ROLES).toEqual(ROLES_CONTEOS);
  });

  it.each(ROLES_CONTEOS)('renders the list for %s', async (role) => {
    login(role);

    render(<ConteosPage />);

    expect(await screen.findByRole('heading', { name: 'Conteos de inventario' })).toBeInTheDocument();
    expect(await screen.findByText('No hay conteos para mostrar.')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it.each(['COMPRAS', 'SERVICIO_CLIENTE', 'COORDINADOR_REPUESTOS'])(
    'sends %s to its home and never renders the page',
    async (role) => {
      login(role);

      render(<ConteosPage />);

      await waitFor(() => expect(pushMock).toHaveBeenCalledWith(homePathFor(role)));
      expect(screen.queryByRole('heading', { name: 'Conteos de inventario' })).not.toBeInTheDocument();
    },
  );
});
