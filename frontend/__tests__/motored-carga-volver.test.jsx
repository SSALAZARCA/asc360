/**
 * Back button on the carga detail screen + `?tab=` deep link in MaestrosTabs.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockGetCarga = jest.fn();
const mockPush = jest.fn();
let mockSearch = '';
jest.mock('../lib/motored/api', () => ({
  getCarga: (...args) => mockGetCarga(...args),
  getSalud: () => Promise.resolve({ hallazgos: [] }),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(mockSearch),
}));
jest.mock('../components/motored/cargas/ResumenTab', () => () => <div />);
jest.mock('../components/motored/cargas/ErroresTab', () => () => <div />);
jest.mock('../components/motored/cargas/VistaPreviaTab', () => () => <div />);

import CargaDetalle from '../components/motored/cargas/CargaDetalle';
import MaestrosTabs from '../components/motored/maestros/MaestrosTabs';

beforeEach(() => {
  mockPush.mockReset();
  mockGetCarga.mockReset();
  mockSearch = '';
});

describe('CargaDetalle back button', () => {
  it('goes back to the Maestros tab of the carga tipo', async () => {
    mockGetCarga.mockResolvedValue({ id: 'c1', tipo: 'VENTAS', nombre_archivo: 'a.xlsx', estado: 'APLICADO' });
    render(<CargaDetalle cargaId="c1" />);
    const btn = await screen.findByRole('button', { name: /Volver a Ventas/ });
    fireEvent.click(btn);
    expect(mockPush).toHaveBeenCalledWith('/motored/maestros?tab=ventas');
  });

  it('maps a multi-word tipo to its tab id', async () => {
    mockGetCarga.mockResolvedValue({ id: 'c1', tipo: 'DEMANDA_PERDIDA', nombre_archivo: 'a.xlsx', estado: 'APLICADO' });
    render(<CargaDetalle cargaId="c1" />);
    fireEvent.click(await screen.findByRole('button', { name: /Volver a Demanda perdida/ }));
    expect(mockPush).toHaveBeenCalledWith('/motored/maestros?tab=demanda_perdida');
  });

  it('renders while loading and goes to Maestros', () => {
    mockGetCarga.mockReturnValue(new Promise(() => {}));
    render(<CargaDetalle cargaId="c1" />);
    fireEvent.click(screen.getByRole('button', { name: /Volver a Maestros/ }));
    expect(mockPush).toHaveBeenCalledWith('/motored/maestros');
  });

  it('renders on error', async () => {
    mockGetCarga.mockRejectedValue(new Error('boom'));
    render(<CargaDetalle cargaId="c1" />);
    await screen.findByText('boom');
    expect(screen.getByRole('button', { name: /Volver a Maestros/ })).toBeInTheDocument();
  });
});

describe('MaestrosTabs ?tab= deep link', () => {
  const tabs = [
    { id: 'uno', label: 'Uno', render: () => <div>contenido-uno</div> },
    { id: 'inventario', label: 'Inventario', render: () => <div>contenido-inventario</div> },
  ];

  it('opens the tab named in the query string', async () => {
    mockSearch = 'tab=inventario';
    render(<MaestrosTabs tabs={tabs} />);
    expect(screen.getByText('contenido-inventario')).toBeInTheDocument();
    await waitFor(() => expect(mockGetCarga).not.toHaveBeenCalled());
  });

  it('falls back to the first tab for an unknown value', () => {
    mockSearch = 'tab=nope';
    render(<MaestrosTabs tabs={tabs} />);
    expect(screen.getByText('contenido-uno')).toBeInTheDocument();
  });

  it('still defaults to the first tab without a query', () => {
    render(<MaestrosTabs tabs={tabs} />);
    expect(screen.getByText('contenido-uno')).toBeInTheDocument();
  });
});
