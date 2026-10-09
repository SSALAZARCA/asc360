/**
 * COORDINADOR_REPUESTOS role and the "Gestión repuestos" section: valid
 * session role, lands on KPI's, sees KPI's plus Gestión repuestos only, is
 * offered when creating users, and is kept inside its pages. The
 * "Ingresos facturas" placeholder renders for ADMIN, COMPRAS, GERENCIA and
 * COORDINADOR_REPUESTOS only. UX only: the backend is the real enforcement.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/tablero-asesores';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

import MotoredLayout, { VALID_ROLES } from '../app/motored/motored-layout';
import MotoredSidebar from '../components/motored/MotoredSidebar';
import UsuarioCreateForm from '../components/motored/UsuarioCreateForm';
import IngresosFacturasPage from '../app/motored/gestion-repuestos/ingresos-facturas/page';
import { TABLERO_ROLES } from '../components/motored/tablero-asesores/useTableroGate';
import {
  COORDINADOR_REPUESTOS, GESTION_REPUESTOS_ROLES, KPIS_PATH, homePathFor, landingPathFor,
} from '../lib/motored/session';
import { tienePermiso } from '../lib/motored/permisosPorRol';
import { ROL_NOMBRE } from '../components/motored/inicio/textos';

const INGRESOS_FACTURAS_PATH = '/motored/gestion-repuestos/ingresos-facturas';
const CUATRO_ROLES = ['ADMIN', 'COMPRAS', 'GERENCIA', 'COORDINADOR_REPUESTOS'];
const OTROS_ROLES = ['SERVICIO_CLIENTE', 'SUCURSAL', 'CONSULTA'];

function login(role, extra = {}) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'C', role, ...extra }));
  sessionStorage.setItem('motored_token', 'tok');
}

function sidebarLabels() {
  return screen.getAllByRole('button').map((b) => b.textContent.trim());
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = KPIS_PATH;
});

describe('COORDINADOR_REPUESTOS session', () => {
  it('exposes the role constant and accepts it in the layout', async () => {
    expect(COORDINADOR_REPUESTOS).toBe('COORDINADOR_REPUESTOS');
    expect(VALID_ROLES).toContain(COORDINADOR_REPUESTOS);
    login(COORDINADOR_REPUESTOS);

    render(<MotoredLayout><div>Contenido KPIs</div></MotoredLayout>);

    expect(await screen.findByText('Contenido KPIs')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("lands on KPI's after login", () => {
    expect(KPIS_PATH).toBe('/motored/tablero-asesores');
    expect(homePathFor(COORDINADOR_REPUESTOS)).toBe(KPIS_PATH);
    expect(landingPathFor({ role: COORDINADOR_REPUESTOS })).toBe(KPIS_PATH);
  });

  it('still lands on the account page while a password change is pending', () => {
    expect(landingPathFor({ role: COORDINADOR_REPUESTOS, must_change_password: true }))
      .toBe('/motored/mi-cuenta');
  });

  it.each(['/motored/maestros', '/motored/pedidos', '/motored/inicio', '/motored/usuarios', '/motored/configuracion'])(
    'is sent back to KPI\'s from %s',
    async (path) => {
      mockPathname = path;
      login(COORDINADOR_REPUESTOS);

      render(<MotoredLayout><div>Prohibido</div></MotoredLayout>);

      await waitFor(() => expect(pushMock).toHaveBeenCalledWith(KPIS_PATH));
      expect(screen.queryByText('Prohibido')).not.toBeInTheDocument();
    },
  );

  it.each([INGRESOS_FACTURAS_PATH, '/motored/mi-cuenta'])('may open %s', async (path) => {
    mockPathname = path;
    login(COORDINADOR_REPUESTOS);

    render(<MotoredLayout><div>Permitido</div></MotoredLayout>);

    expect(await screen.findByText('Permitido')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('passes the KPI page gate', () => {
    expect(TABLERO_ROLES).toContain(COORDINADOR_REPUESTOS);
  });

  it('has a readable role name', () => {
    expect(ROL_NOMBRE.COORDINADOR_REPUESTOS).toBe('Coordinador de repuestos');
  });
});

describe('sidebar', () => {
  it("shows COORDINADOR_REPUESTOS KPI's and Gestión repuestos only", () => {
    render(<MotoredSidebar user={{ nombre: 'C', role: COORDINADOR_REPUESTOS }} />);

    expect(sidebarLabels()).toEqual(["KPI's", 'Gestión repuestos', 'Cambiar mi contraseña', 'Salir']);
    fireEvent.click(screen.getByRole('button', { name: 'Gestión repuestos' }));
    expect(sidebarLabels()).toEqual([
      "KPI's", 'Gestión repuestos', 'Ingresos facturas', 'Cambiar mi contraseña', 'Salir',
    ]);
  });

  it.each(CUATRO_ROLES)('shows Gestión repuestos > Ingresos facturas to %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Gestión repuestos' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ingresos facturas' }));
    expect(pushMock).toHaveBeenCalledWith(INGRESOS_FACTURAS_PATH);
  });

  it.each(OTROS_ROLES)('hides Gestión repuestos from %s', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);

    expect(screen.queryByRole('button', { name: 'Gestión repuestos' })).not.toBeInTheDocument();
  });
});

describe('create-user form', () => {
  it('offers Coordinador de repuestos with an explicit option style', () => {
    render(<UsuarioCreateForm onCreate={jest.fn()} />);
    const option = screen.getByRole('option', { name: 'Coordinador de repuestos' });

    expect(option).toHaveValue('COORDINADOR_REPUESTOS');
    expect(option.style.color).toBe('rgb(26, 26, 24)');
  });
});

describe('Ingresos facturas page', () => {
  it.each(CUATRO_ROLES)('renders the placeholder for %s', async (role) => {
    mockPathname = INGRESOS_FACTURAS_PATH;
    login(role);

    render(<IngresosFacturasPage />);

    expect(await screen.findByRole('heading', { name: 'Ingresos facturas' })).toBeInTheDocument();
    expect(screen.getByText('Aquí verá las facturas de pedidos pendientes por ingresar.')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it.each(OTROS_ROLES)('sends %s to its home and never renders the page', async (role) => {
    mockPathname = INGRESOS_FACTURAS_PATH;
    login(role);

    render(<IngresosFacturasPage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(pushMock).not.toHaveBeenCalledWith(INGRESOS_FACTURAS_PATH);
    expect(screen.queryByRole('heading', { name: 'Ingresos facturas' })).not.toBeInTheDocument();
  });

  it('matches the permission matrix', () => {
    expect(GESTION_REPUESTOS_ROLES).toEqual(CUATRO_ROLES);
    [...CUATRO_ROLES, ...OTROS_ROLES].forEach((rol) => {
      expect(tienePermiso('ingresos-facturas', rol)).toBe(CUATRO_ROLES.includes(rol));
    });
  });
});
