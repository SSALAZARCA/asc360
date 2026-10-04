/**
 * Usuarios > Roles y permisos (T4): read-only role x screen matrix, plus the
 * drift guard that keeps it in step with the sidebar, the gates and the layout.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/usuarios',
}));

import RolesPermisosMatriz from '../components/motored/usuarios/RolesPermisosMatriz';
import { ROLES, PANTALLAS, tienePermiso } from '../lib/motored/permisosPorRol';
import { menuItemsFor } from '../components/motored/MotoredSidebar';
import { VALID_ROLES } from '../app/motored/motored-layout';
import { PEDIDOS_ROLES } from '../lib/motored/usePedidosGate';
import { TABLERO_ROLES } from '../components/motored/tablero-asesores/useTableroGate';
import { CONFIGURACION_ROLES } from '../components/motored/configuracion/useConfiguracionGate';
import { DETRACTORES_ROLES } from '../lib/motored/useDetractoresGate';

const idsDeRoles = ROLES.map((r) => r.id);

function celda(pantalla, rol) {
  const fila = screen.getByRole('rowheader', { name: pantalla }).closest('tr');
  const cabeceras = screen.getAllByRole('columnheader');
  const indice = cabeceras.findIndex((th) => th.textContent.startsWith(rol));
  return within(fila).getAllByRole('cell')[indice - 1]; // first header is the screen column
}
const marca = (pantalla, rol) => within(celda(pantalla, rol)).getByRole('img').getAttribute('aria-label');

describe('RolesPermisosMatriz', () => {
  it('renders one column per role and one row per screen', () => {
    render(<RolesPermisosMatriz />);

    idsDeRoles.forEach((rol) => {
      expect(screen.getAllByRole('columnheader').some((th) => th.textContent.startsWith(rol))).toBe(true);
    });
    expect(screen.getAllByRole('rowheader')).toHaveLength(PANTALLAS.length);
  });

  it('shows GERENCIA with Presupuestos and KPIs only', () => {
    render(<RolesPermisosMatriz />);

    expect(marca('Maestros: Presupuestos', 'GERENCIA')).toBe('Sí');
    expect(marca("KPI's", 'GERENCIA')).toBe('Sí');
    ['Pedidos y corridas', 'Configuración', 'Cargas de archivos', 'Gestión de usuarios', 'Vincular Telegram']
      .forEach((p) => expect(marca(p, 'GERENCIA')).toBe('No'));
  });

  it('shows ADMIN with access everywhere', () => {
    render(<RolesPermisosMatriz />);

    PANTALLAS.forEach((p) => expect(marca(p.nombre, 'ADMIN')).toBe('Sí'));
  });

  it('labels every cell Sí or No for assistive technology', () => {
    render(<RolesPermisosMatriz />);

    const marcas = screen.getAllByRole('img');
    expect(marcas).toHaveLength(PANTALLAS.length * ROLES.length);
    marcas.forEach((m) => expect(['Sí', 'No']).toContain(m.getAttribute('aria-label')));
  });

  it('is read-only and says how to change permissions', () => {
    render(<RolesPermisosMatriz />);

    expect(screen.getByText(/Vista de solo lectura\. Los permisos se definen en la aplicación; para cambiarlos, contacte al administrador del sistema\./)).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('explains non-obvious roles with tooltips', () => {
    render(<RolesPermisosMatriz />);

    expect(screen.getByRole('note', { name: "Ve Presupuestos y KPI's" })).toBeInTheDocument();
    expect(screen.getAllByRole('note').length).toBeGreaterThanOrEqual(2);
  });

  it('keeps the table in the scroll wrapper with a sticky first column', () => {
    const { container } = render(<RolesPermisosMatriz />);

    expect(container.querySelector('table').closest('.motored-table-scroll')).not.toBeNull();
    screen.getAllByRole('rowheader').forEach((th) => expect(th.style.position).toBe('sticky'));
  });
});

describe('permission matrix drift guard', () => {
  it('lists exactly the roles the layout accepts (web roles)', () => {
    expect([...idsDeRoles].sort()).toEqual([...VALID_ROLES].sort());
  });

  it.each(idsDeRoles)('marks for %s the same sidebar entries the sidebar shows', (rol) => {
    const visibles = menuItemsFor({ role: rol }).flatMap((i) => (i.children ? i.children : [i])).map((i) => i.id);
    const marcadas = PANTALLAS.filter((p) => p.sidebarId && tienePermiso(p.id, rol)).map((p) => p.sidebarId);

    expect([...marcadas].sort()).toEqual([...visibles].sort());
  });

  it('has a matrix row for every sidebar entry', () => {
    const todas = menuItemsFor({ role: 'ADMIN' }).flatMap((i) => (i.children ? i.children : [i])).map((i) => i.id);
    const cubiertas = PANTALLAS.map((p) => p.sidebarId).filter(Boolean);

    todas.forEach((id) => expect(cubiertas).toContain(id));
  });

  it('follows the gate constants of Pedidos, KPIs, Configuración and Detractores', () => {
    idsDeRoles.forEach((rol) => {
      expect(tienePermiso('pedidos', rol)).toBe(PEDIDOS_ROLES.includes(rol));
      expect(tienePermiso('topes', rol)).toBe(PEDIDOS_ROLES.includes(rol));
      expect(tienePermiso('tablero-asesores', rol)).toBe(TABLERO_ROLES.includes(rol));
      expect(tienePermiso('configuracion', rol)).toBe(CONFIGURACION_ROLES.includes(rol));
      expect(tienePermiso('detractores', rol)).toBe(DETRACTORES_ROLES.includes(rol));
    });
  });
});
