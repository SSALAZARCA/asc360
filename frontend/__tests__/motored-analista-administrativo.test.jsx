/**
 * ANALISTA_ADMINISTRATIVO role: valid session role, lands on Ingresos
 * facturas, sees only the Gestión repuestos section (no KPI's), is offered
 * when creating users and is kept inside its pages. UX only: the backend is
 * the real enforcement.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/gestion-repuestos/ingresos-facturas';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

import MotoredLayout, { VALID_ROLES } from '../app/motored/motored-layout';
import UsuarioCreateForm from '../components/motored/UsuarioCreateForm';
import { menuItemsFor } from '../components/motored/MotoredSidebar';
import { TABLERO_ROLES } from '../components/motored/tablero-asesores/useTableroGate';
import { puedeConfirmarRol, puedeDescargarPlantillaRol } from '../components/motored/kpis/asesores/pendientes';
import { ROL_NOMBRE } from '../components/motored/inicio/textos';
import {
  ANALISTA_ADMINISTRATIVO, GESTION_REPUESTOS_ROLES, homePathFor, landingPathFor,
} from '../lib/motored/session';

const INGRESOS_FACTURAS_PATH = '/motored/gestion-repuestos/ingresos-facturas';

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'A', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

beforeEach(() => {
  sessionStorage.clear();
  pushMock.mockClear();
  mockPathname = INGRESOS_FACTURAS_PATH;
});

describe('ANALISTA_ADMINISTRATIVO', () => {
  it('is a valid role that opens Gestión repuestos', () => {
    expect(ANALISTA_ADMINISTRATIVO).toBe('ANALISTA_ADMINISTRATIVO');
    expect(VALID_ROLES).toContain(ANALISTA_ADMINISTRATIVO);
    expect(GESTION_REPUESTOS_ROLES).toContain(ANALISTA_ADMINISTRATIVO);
    expect(ROL_NOMBRE.ANALISTA_ADMINISTRATIVO).toBe('Analista administrativo');
  });

  it('has no KPI access and lands on Ingresos facturas', () => {
    expect(TABLERO_ROLES).not.toContain(ANALISTA_ADMINISTRATIVO);
    expect(homePathFor(ANALISTA_ADMINISTRATIVO)).toBe(INGRESOS_FACTURAS_PATH);
    expect(landingPathFor({ role: ANALISTA_ADMINISTRATIVO })).toBe(INGRESOS_FACTURAS_PATH);
    expect(landingPathFor({ role: ANALISTA_ADMINISTRATIVO, must_change_password: true })).toBe('/motored/mi-cuenta');
  });

  it('sees only Gestión repuestos and the account page in the menu', () => {
    const items = menuItemsFor({ role: ANALISTA_ADMINISTRATIVO });
    expect(items.map((i) => i.name)).toEqual(['Gestión repuestos', 'Cambiar mi contraseña']);
    expect(items[0].children.map((c) => c.id)).toEqual(['ingresos-facturas']);
  });

  it('may confirm Llegó / No ha llegado', () => {
    expect(puedeConfirmarRol(ANALISTA_ADMINISTRATIVO)).toBe(true);
    expect(puedeConfirmarRol('COMPRAS')).toBe(false);
  });

  it.each([INGRESOS_FACTURAS_PATH, '/motored/mi-cuenta'])('may open %s', async (path) => {
    mockPathname = path;
    login(ANALISTA_ADMINISTRATIVO);
    render(<MotoredLayout><div>Permitido</div></MotoredLayout>);
    expect(await screen.findByText('Permitido')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it.each(['/motored/tablero-asesores', '/motored/maestros', '/motored/inicio', '/motored/configuracion'])(
    'is sent back to Ingresos facturas from %s',
    async (path) => {
      mockPathname = path;
      login(ANALISTA_ADMINISTRATIVO);
      render(<MotoredLayout><div>Prohibido</div></MotoredLayout>);
      await waitFor(() => expect(pushMock).toHaveBeenCalledWith(INGRESOS_FACTURAS_PATH));
      expect(screen.queryByText('Prohibido')).not.toBeInTheDocument();
    },
  );

  it('is offered, with its Spanish label, when creating a user', () => {
    render(<UsuarioCreateForm onCreate={jest.fn()} />);
    const opcion = screen.getByRole('option', { name: 'Analista administrativo' });
    expect(opcion).toHaveValue('ANALISTA_ADMINISTRATIVO');
    expect(opcion.style.color).not.toBe('');
  });
});

describe('puedeDescargarPlantillaRol', () => {
  it.each([
    ['ADMIN', true],
    [ANALISTA_ADMINISTRATIVO, true],
    ['COORDINADOR_REPUESTOS', false],
    ['COMPRAS', false],
    ['GERENCIA', false],
    ['ASESOR_MOSTRADOR', false],
    [undefined, false],
  ])('role %s may download the ERP template: %s', (role, esperado) => {
    expect(puedeDescargarPlantillaRol(role)).toBe(esperado);
  });
});
