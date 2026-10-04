/**
 * Maestros tabs by role (budgets, T3): GERENCIA sees ONLY Presupuestos (and
 * must not fire the health call the backend would 403), ADMIN sees every tab
 * plus Presupuestos, every other role keeps the old tabs and never sees it.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const mockGetSalud = jest.fn();
jest.mock('../lib/motored/api', () => new Proxy({}, { get: (_t, name) => (
  name === 'getSalud' ? (...a) => mockGetSalud(...a) : jest.fn(() => Promise.resolve([]))
) }));
jest.mock('../lib/motored/presupuestosApi', () => ({
  listarMesesPresupuesto: jest.fn(() => Promise.resolve([])),
  listarTiendasPresupuesto: jest.fn(() => Promise.resolve([])),
}));
jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(''),
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/maestros',
}));
jest.mock('../app/motored/motored-layout', () => ({ __esModule: true, default: ({ children }) => <div>{children}</div> }));
['SucursalesTab', 'ProveedoresTab', 'ReferenciasTab', 'ClientesTecniredTab', 'VendedoresTab'].forEach((n) => {
  jest.doMock(`../components/motored/maestros/${n}`, () => ({ __esModule: true, default: () => <p>{n}</p> }));
});
jest.mock('../components/motored/cargas/MovimientoTab', () => ({ __esModule: true, default: () => <p>mov</p> }));

import MaestrosPage from '../app/motored/maestros/page';
import { filtrarTabsPorRol } from '../lib/motored/maestrosTabsPorRol';

const TABS = [
  { id: 'a', label: 'A' },
  { id: 'p', label: 'Presupuestos', roles: ['ADMIN', 'GERENCIA'] },
];

beforeEach(() => {
  sessionStorage.clear();
  mockGetSalud.mockReset().mockResolvedValue({ hallazgos: [] });
});

function login(role) {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
}

describe('filtrarTabsPorRol', () => {
  it('GERENCIA keeps only the tabs that list it', () => {
    expect(filtrarTabsPorRol(TABS, 'GERENCIA').map((t) => t.id)).toEqual(['p']);
  });
  it('ADMIN keeps everything', () => {
    expect(filtrarTabsPorRol(TABS, 'ADMIN').map((t) => t.id)).toEqual(['a', 'p']);
  });
  it.each(['COMPRAS', 'CONSULTA', 'SUCURSAL', null])('%s loses the restricted tab', (rol) => {
    expect(filtrarTabsPorRol(TABS, rol).map((t) => t.id)).toEqual(['a']);
  });
});

describe('Maestros page', () => {
  it('GERENCIA sees only the Presupuestos tab and never asks for the health', async () => {
    login('GERENCIA');
    render(<MaestrosPage />);

    expect(await screen.findByRole('button', { name: 'Presupuestos' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Sucursales/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Ventas' })).toBeNull();
    await new Promise((r) => setTimeout(r, 0));
    expect(mockGetSalud).not.toHaveBeenCalled();
  });

  it('ADMIN sees the old tabs plus Presupuestos', async () => {
    login('ADMIN');
    render(<MaestrosPage />);

    expect(await screen.findByRole('button', { name: /Sucursales/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Presupuestos' })).toBeInTheDocument();
    await waitFor(() => expect(mockGetSalud).toHaveBeenCalled());
  });

  it('COMPRAS keeps the old tabs and does not see Presupuestos', async () => {
    login('COMPRAS');
    render(<MaestrosPage />);

    expect(await screen.findByRole('button', { name: /Sucursales/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Presupuestos' })).toBeNull();
  });
});
