/**
 * Motored sidebar grouping: Inicio, KPI's, then the Pedidos, Gestión repuestos,
 * Encuestas satisfacción and Configuración groups, then "Cambiar mi contraseña". Grouping must not
 * change which pages each role reaches.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const pushMock = jest.fn();
let mockPathname = '/motored/maestros';
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

import MotoredSidebar, { menuItemsFor } from '../components/motored/MotoredSidebar';

const ADMIN = { nombre: 'U', role: 'ADMIN' };

// Pages each role reaches. SUCURSAL and CONSULTA have no screens yet and
// ASESOR_MOSTRADOR has no web access (owner decision 2026-10-05).
const PAGES_BEFORE = {
  ADMIN: ['inicio', 'pedidos', 'tablero-asesores', 'maestros', 'usuarios-gestion', 'ingresos', 'ventas-perdidas',
    'ingresos-facturas', 'encuesta-satisfaccion', 'detractores', 'mi-cuenta', 'configuracion'],
  COMPRAS: ['inicio', 'pedidos', 'tablero-asesores', 'maestros', 'ingresos-facturas', 'mi-cuenta'],
  GERENCIA: ['inicio', 'tablero-asesores', 'maestros', 'ingresos-facturas', 'mi-cuenta'],
  COORDINADOR_REPUESTOS: ['tablero-asesores', 'ingresos-facturas', 'mi-cuenta'],
  SUCURSAL: ['mi-cuenta'],
  CONSULTA: ['mi-cuenta'],
  SERVICIO_CLIENTE: ['inicio', 'encuesta-satisfaccion', 'detractores', 'mi-cuenta'],
  ASESOR_MOSTRADOR: [],
};

const TOP_LEVEL = {
  ADMIN: ['Inicio', "KPI's", 'Pedidos', 'Gestión repuestos', 'Encuestas satisfacción', 'Configuración', 'Cambiar mi contraseña'],
  COMPRAS: ['Inicio', "KPI's", 'Pedidos', 'Gestión repuestos', 'Cambiar mi contraseña'],
  GERENCIA: ['Inicio', "KPI's", 'Pedidos', 'Gestión repuestos', 'Cambiar mi contraseña'],
  COORDINADOR_REPUESTOS: ["KPI's", 'Gestión repuestos', 'Cambiar mi contraseña'],
  SUCURSAL: ['Cambiar mi contraseña'],
  CONSULTA: ['Cambiar mi contraseña'],
  SERVICIO_CLIENTE: ['Inicio', 'Encuestas satisfacción', 'Cambiar mi contraseña'],
  ASESOR_MOSTRADOR: [],
};

const GROUPS = [
  ['Pedidos', ['Registro de pedidos', 'Maestros', 'Ventas perdidas'], ['/motored/pedidos', '/motored/maestros', '/motored/ventas-perdidas']],
  ['Gestión repuestos', ['Ingresos facturas'], ['/motored/gestion-repuestos/ingresos-facturas']],
  ['Encuestas satisfacción', ['Cargue de encuestas', 'Gestión de detractores'], ['/motored/encuesta-satisfaccion', '/motored/detractores']],
  ['Configuración', ['Configuración parámetros', 'Gestión de usuarios', 'Registro de ingresos'], ['/motored/configuracion', '/motored/usuarios', '/motored/ingresos']],
];

const pagesOf = (user) => menuItemsFor(user).flatMap((i) => i.children || [i]).map((i) => i.id);
const navLabels = () => screen.getAllByRole('button').map((b) => b.textContent).filter((t) => !t.includes('Salir'));

beforeEach(() => {
  pushMock.mockClear();
  mockPathname = '/motored/maestros';
});

describe('MotoredSidebar groups - order and labels', () => {
  it('shows the top level in the owner order for ADMIN', () => {
    render(<MotoredSidebar user={ADMIN} />);
    expect(navLabels()).toEqual(TOP_LEVEL.ADMIN);
  });

  it('lists every entry in order once all groups are open', () => {
    render(<MotoredSidebar user={ADMIN} />);
    GROUPS.forEach(([group]) => fireEvent.click(screen.getByRole('button', { name: group })));
    expect(navLabels()).toEqual([
      'Inicio', "KPI's",
      'Pedidos', 'Registro de pedidos', 'Maestros', 'Ventas perdidas',
      'Gestión repuestos', 'Ingresos facturas',
      'Encuestas satisfacción', 'Cargue de encuestas', 'Gestión de detractores',
      'Configuración', 'Configuración parámetros', 'Gestión de usuarios', 'Registro de ingresos',
      'Cambiar mi contraseña',
    ]);
  });

  it.each(GROUPS)('groups %s children and navigates from each one', (group, children, paths) => {
    render(<MotoredSidebar user={ADMIN} />);
    fireEvent.click(screen.getByRole('button', { name: group }));
    expect(pushMock).not.toHaveBeenCalled();
    children.forEach((child, i) => {
      fireEvent.click(screen.getByRole('button', { name: child }));
      expect(pushMock).toHaveBeenLastCalledWith(paths[i]);
    });
  });
});

describe('MotoredSidebar groups - per-role visibility', () => {
  it.each(Object.keys(PAGES_BEFORE))('keeps the same pages for %s', (role) => {
    expect([...pagesOf({ role })].sort()).toEqual([...PAGES_BEFORE[role]].sort());
  });

  it.each(Object.keys(TOP_LEVEL))('shows %s only the groups holding one of its pages', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    const labels = screen.queryAllByRole('button').map((b) => b.textContent).filter((t) => !t.includes('Salir'));
    expect(labels).toEqual(TOP_LEVEL[role]);
  });

  it('shows GERENCIA only Maestros inside Pedidos', () => {
    render(<MotoredSidebar user={{ nombre: 'U', role: 'GERENCIA' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Pedidos' }));
    expect(navLabels()).toEqual(['Inicio', "KPI's", 'Pedidos', 'Maestros', 'Gestión repuestos', 'Cambiar mi contraseña']);
  });

  it.each(['ADMIN', 'COMPRAS', 'GERENCIA', 'SERVICIO_CLIENTE'])('puts Inicio first for %s and navigates home', (role) => {
    render(<MotoredSidebar user={{ nombre: 'U', role }} />);
    const inicio = screen.getAllByRole('button')[0];
    expect(inicio).toHaveTextContent('Inicio');
    fireEvent.click(inicio);
    expect(pushMock).toHaveBeenLastCalledWith('/motored/inicio');
  });

  it('marks Inicio as the current page on /motored/inicio', () => {
    mockPathname = '/motored/inicio';
    render(<MotoredSidebar user={ADMIN} />);
    expect(screen.getByRole('button', { name: 'Inicio' })).toHaveAttribute('aria-current', 'page');
  });

  it('shows no user nothing and a pending password change only the account page', () => {
    expect(pagesOf(null)).toEqual([]);
    expect(pagesOf({ role: 'ADMIN', must_change_password: true })).toEqual(['mi-cuenta']);
  });
});

describe('MotoredSidebar groups - collapse and current section', () => {
  it.each(GROUPS)('%s starts folded and toggles on click', (group, children) => {
    render(<MotoredSidebar user={ADMIN} />);
    const header = screen.getByRole('button', { name: group });
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: children[0] })).toBeNull();
    fireEvent.click(header);
    expect(header).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(header);
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it.each(GROUPS.flatMap(([group, , paths]) => paths.map((p) => [group, p])))(
    '%s is marked as current on %s', (group, path) => {
      mockPathname = path;
      render(<MotoredSidebar user={ADMIN} />);
      const header = screen.getByRole('button', { name: group });
      expect(header).toHaveAttribute('aria-current', 'true');
      expect(header).toHaveAttribute('aria-expanded', 'false');
      GROUPS.filter(([other]) => other !== group).forEach(([other]) => {
        expect(screen.getByRole('button', { name: other })).not.toHaveAttribute('aria-current');
      });
    },
  );
});
