/**
 * COORDINADOR_REPUESTOS as a count leader (owner decision 2026-10-09): it
 * opens the Conteos pages and gets exactly the leader actions on the conteo
 * it leads; the schedule dialog lists both leader roles. Its sidebar does
 * not change yet (Inventarios stays ADMIN-only while stage 1 is tested).
 * UX only: the backend is the real enforcement.
 */
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import * as api from '../lib/motored/conteosApi';
import MotoredLayout from '../app/motored/motored-layout';
import MotoredSidebar from '../components/motored/MotoredSidebar';
import ConteosPage from '../app/motored/inventarios/conteos/page';
import ConteosContainer from '../components/motored/inventarios/ConteosContainer';
import ConteoDetalleContainer from '../components/motored/inventarios/ConteoDetalleContainer';
import { esLiderDeConteo, permisosConteo } from '../components/motored/inventarios/conteosFormato';
import {
  CONTEOS_PATH, CONTEOS_ROLES, CONTEOS_ROLES_VISIBLES, COORDINADOR_REPUESTOS, isCoordinadorRepuestosPath,
} from '../lib/motored/session';
import { ROLES, tienePermiso } from '../lib/motored/permisosPorRol';

const pushMock = jest.fn();
let mockPathname = CONTEOS_PATH;
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));
jest.mock('../lib/motored/conteosApi');

const PROGRAMADO = {
  id: 'c1', tipo: 'TOTAL', origen: 'MANUAL', estado: 'PROGRAMADO', fecha_programada: '2026-10-09',
  sucursal: { id: 's1', nombre: 'Quilichao' }, lider: { id: 'k1', nombre: 'Carla Coordinadora' },
  umbrales: { reconteo: '100000', critico: '500000' }, snapshot: null, acceso: null,
};
const SUCURSALES = [{ id: 's1', nombre: 'Quilichao', vigencia_horas: 6, inventario: null }];

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'C', role }));
  sessionStorage.setItem('motored_token', 'tok');
}

beforeEach(() => {
  sessionStorage.clear();
  jest.resetAllMocks();
  mockPathname = CONTEOS_PATH;
  api.listarConteos.mockResolvedValue([PROGRAMADO]);
  api.obtenerConteo.mockResolvedValue(PROGRAMADO);
  api.listarSucursalesConteo.mockResolvedValue(SUCURSALES);
  api.listarUbicaciones.mockResolvedValue([]);
  api.listarLideres.mockResolvedValue([
    { id: 'l1', nombre: 'Laura Líder', email: null, rol: 'LIDER_INVENTARIOS' },
    { id: 'k1', nombre: 'Carla Coordinadora', email: null, rol: 'COORDINADOR_REPUESTOS' },
    { id: 'a1', nombre: 'Adriana Admin', email: null, rol: 'ADMIN' },
  ]);
});

describe('the leader role helper', () => {
  it('accepts both leader roles and nothing else', () => {
    expect(esLiderDeConteo('LIDER_INVENTARIOS')).toBe(true);
    expect(esLiderDeConteo(COORDINADOR_REPUESTOS)).toBe(true);
    ['ADMIN', 'GERENCIA', 'COMPRAS', undefined].forEach((rol) => expect(esLiderDeConteo(rol)).toBe(false));
  });

  it('gives the coordinator the leader permissions', () => {
    expect(permisosConteo(COORDINADOR_REPUESTOS)).toEqual({ role: COORDINADOR_REPUESTOS, administra: false, opera: true });
  });
});

describe('the coordinator reaches Conteos', () => {
  it('is in the page gate and may open the inventory pages', () => {
    expect(CONTEOS_ROLES).toContain(COORDINADOR_REPUESTOS);
    expect(isCoordinadorRepuestosPath('/motored/inventarios/conteos')).toBe(true);
    expect(isCoordinadorRepuestosPath('/motored/inventarios/conteos/c1')).toBe(true);
    expect(isCoordinadorRepuestosPath('/motored/inventarios-otra')).toBe(false);
  });

  it('is not sent away from the conteos page by the layout', async () => {
    mockPathname = '/motored/inventarios/conteos/c1';
    login(COORDINADOR_REPUESTOS);

    render(<MotoredLayout><div>Permitido</div></MotoredLayout>);

    expect(await screen.findByText('Permitido')).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('renders the list page and opens its own conteo, without scheduling', async () => {
    login(COORDINADOR_REPUESTOS);
    render(<ConteosPage />);

    expect(await screen.findByRole('heading', { name: 'Conteos de inventario' })).toBeInTheDocument();
    expect(await screen.findByText('Quilichao')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Programar conteo' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir Quilichao' }));
    expect(pushMock).toHaveBeenCalledWith('/motored/inventarios/conteos/c1');
  });

  it('gets the leader action to start its own conteo', async () => {
    login(COORDINADOR_REPUESTOS);
    render(<ConteoDetalleContainer conteoId="c1" />);

    expect(await screen.findByRole('button', { name: 'Iniciar conteo de Quilichao' })).toBeInTheDocument();
  });
});

describe('the schedule dialog', () => {
  it('lists every assignable leader role, ADMIN included, with a styled option each', async () => {
    login('ADMIN');
    render(<ConteosContainer />);
    fireEvent.click(await screen.findByRole('button', { name: 'Programar conteo' }));
    const dialogo = await screen.findByRole('dialog');

    const select = within(dialogo).getByLabelText('Líder del conteo');
    expect(await within(select).findByRole('option', { name: 'Laura Líder · Líder de inventarios' }))
      .toHaveValue('l1');
    expect(within(select).getByRole('option', { name: 'Carla Coordinadora · Coordinador de repuestos' }))
      .toHaveValue('k1');
    expect(within(select).getByRole('option', { name: 'Adriana Admin · Administrador' }))
      .toHaveValue('a1');
    within(select).getAllByRole('option').forEach((opcion) => expect(opcion.style.color).not.toBe(''));
  });
});

describe('the coordinator sidebar and matrix', () => {
  it('keeps Inventarios hidden while the menu stays ADMIN-only', () => {
    expect(CONTEOS_ROLES_VISIBLES).toEqual(['ADMIN']);
    render(<MotoredSidebar user={{ nombre: 'C', role: COORDINADOR_REPUESTOS }} />);

    expect(screen.queryByRole('button', { name: 'Inventarios' })).not.toBeInTheDocument();
    expect(tienePermiso('conteos', COORDINADOR_REPUESTOS)).toBe(false);
  });

  it('says in the matrix that the coordinator leads the counts it is assigned', () => {
    const coordinador = ROLES.find((r) => r.id === COORDINADOR_REPUESTOS);

    expect(coordinador.ayuda).toMatch(/conteos de inventario/);
  });
});
