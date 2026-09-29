/**
 * "Reactivar" row action for inactive rows (odd/motored-acciones-con-iconos, T5):
 * the five screens that have "Desactivar".
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListMaestros = jest.fn();
const mockReactivateMaestro = jest.fn();
const mockBuscarReferencias = jest.fn();
const mockListUsuarios = jest.fn();
const mockReactivateUsuario = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  reactivateMaestro: (...args) => mockReactivateMaestro(...args),
  buscarReferencias: (...args) => mockBuscarReferencias(...args),
  listLineasComerciales: () => Promise.resolve([]),
  buscarSustitutas: () => Promise.resolve([]),
  listUsuarios: (...args) => mockListUsuarios(...args),
  listSolicitudesPendientes: () => Promise.resolve([]),
  reactivateUsuario: (...args) => mockReactivateUsuario(...args),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/usuarios',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const MockMotoredSidebar = () => <div />;
  MockMotoredSidebar.displayName = 'MockMotoredSidebar';
  return MockMotoredSidebar;
});

import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';
import SucursalesTab from '../components/motored/maestros/SucursalesTab';
import BodegasTab from '../components/motored/maestros/BodegasTab';
import ProveedoresTab from '../components/motored/maestros/ProveedoresTab';
import ReferenciasTab from '../components/motored/maestros/ReferenciasTab';
import UsuariosPage from '../app/motored/usuarios/page';

const SUC = { id: 's1', nombre: 'NORTE', dias_seguridad: '2.5', activa: false };
const BOD = { id: 'b1', codigo: 'BA1', descripcion: 'x', sucursal_id: 's1', activa: false };
const PRO = { id: 'p1', codigo: 'HMCL', nombre: 'HMCL Colombia', es_principal: true, activa: false };
const REF = {
  id: 'r1', codigo: 'REF-1', proveedor_id: 'p1', nombre: 'Viejo', unidad_empaque: 1,
  homologados: [], sustituida_por: 'r2', activa: false,
};
const USR = { id: 'u1', nombre: 'Rita Rechazada', email: 'r@x.com', role: 'COMPRAS', activo: false, status: 'rejected' };

beforeEach(() => {
  mockListMaestros.mockReset();
  mockReactivateMaestro.mockReset().mockResolvedValue({});
  mockReactivateUsuario.mockReset().mockResolvedValue({});
  mockBuscarReferencias.mockReset().mockResolvedValue({ items: [REF], total: 1, page: 1, page_size: 50 });
  mockListUsuarios.mockReset().mockResolvedValue([USR]);
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'admin-1', nombre: 'Ana', role: 'ADMIN' }));
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => jest.restoreAllMocks());

const MAESTRO_CASES = [
  ['Sucursales', SucursalesTab, 'sucursales', SUC, 'NORTE'],
  ['Bodegas', BodegasTab, 'bodegas', BOD, 'BA1'],
  ['Proveedores', ProveedoresTab, 'proveedores', PRO, 'HMCL Colombia'],
];

describe.each(MAESTRO_CASES)('%s: Reactivar', (_nombre, Tab, entidad, fila, texto) => {
  beforeEach(() => {
    mockListMaestros.mockImplementation((e) => Promise.resolve(e === entidad ? [fila] : [SUC]));
  });

  it('shows Reactivar (not Desactivar) on an inactive row and reactivates after confirming', async () => {
    render(<Tab />);
    const tr = (await screen.findAllByText(texto))[0].closest('tr');
    expect(within(tr).queryByRole('button', { name: 'Desactivar' })).toBeNull();

    fireEvent.click(within(tr).getByRole('button', { name: 'Reactivar' }));

    await waitFor(() => expect(mockReactivateMaestro).toHaveBeenCalledWith(entidad, fila.id));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(mockListMaestros.mock.calls.filter(([e]) => e === entidad).length).toBeGreaterThan(1));
  });

  it('does nothing when the confirmation is declined', async () => {
    window.confirm.mockReturnValue(false);
    render(<Tab />);
    const tr = (await screen.findAllByText(texto))[0].closest('tr');

    fireEvent.click(within(tr).getByRole('button', { name: 'Reactivar' }));

    expect(mockReactivateMaestro).not.toHaveBeenCalled();
  });
});

describe('Referencias: Reactivar', () => {
  beforeEach(() => {
    mockListMaestros.mockResolvedValue([{ id: 'p1', codigo: 'HMCL', nombre: 'HMCL' }]);
  });

  it('reactivates and refetches the current page', async () => {
    render(<ReferenciasTab />);
    const tr = (await screen.findByText('REF-1')).closest('tr');
    const llamadasAntes = mockBuscarReferencias.mock.calls.length;

    fireEvent.click(within(tr).getByRole('button', { name: 'Reactivar' }));

    await waitFor(() => expect(mockReactivateMaestro).toHaveBeenCalledWith('referencias', 'r1'));
    await waitFor(() => expect(mockBuscarReferencias.mock.calls.length).toBeGreaterThan(llamadasAntes));
    expect(within(tr).queryByRole('button', { name: 'Desactivar' })).toBeNull();
  });
});

describe('Usuarios: Reactivar', () => {
  it('reactivates an inactive usuario after confirming and reloads the list', async () => {
    render(<UsuariosPage />);
    const tr = (await screen.findByText('Rita Rechazada')).closest('tr');
    expect(within(tr).queryByRole('button', { name: 'Desactivar' })).toBeNull();

    fireEvent.click(within(tr).getByRole('button', { name: 'Reactivar' }));

    await waitFor(() => expect(mockReactivateUsuario).toHaveBeenCalledWith('u1'));
    await waitFor(() => expect(mockListUsuarios.mock.calls.length).toBeGreaterThan(1));
  });

  it('shows the error when the backend refuses', async () => {
    mockReactivateUsuario.mockRejectedValue(new Error('boom'));
    render(<UsuariosPage />);
    const tr = (await screen.findByText('Rita Rechazada')).closest('tr');

    fireEvent.click(within(tr).getByRole('button', { name: 'Reactivar' }));

    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});
