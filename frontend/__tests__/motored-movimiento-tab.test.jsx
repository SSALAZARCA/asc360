/**
 * Tests for `MovimientoTab` (sdd/motored-cargas-tipo-declarado, Phase 3,
 * task 3.5/3.12; design D3) -- the generic per-movement-type tab that
 * replaced the standalone Cargas screen. Mirrors the existing Motored
 * mocking convention (mock `lib/motored/api`, import the component after
 * the mock is registered).
 *
 * What's under test:
 * 1. Renders its own label and a filtered (tipoFijo) history underneath.
 * 2. "Subir archivo" is visible for ADMIN/COMPRAS and opens
 *    `UploadMovimientoModal` scoped to this tab's own `tipo`.
 * 3. "Subir archivo" is hidden for SUCURSAL/CONSULTA (UI-level RBAC; the
 *    real guarantee is server-side).
 * 4. A successful upload refreshes the history table underneath.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListarCargas = jest.fn();
const mockSubir = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listarCargas: (...args) => mockListarCargas(...args),
  subirCargaMovimiento: (...args) => mockSubir(...args),
  getCarga: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

import MovimientoTab from '../components/motored/cargas/MovimientoTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

function setRole(role) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role }));
}

function xlsxFile(name = 'ventas.xlsx') {
  return new File(['dummy'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

beforeEach(() => {
  mockListarCargas.mockReset().mockResolvedValue([]);
  mockSubir.mockReset();
  sessionStorage.clear();
});

describe('MovimientoTab', () => {
  it('renders its own label and a history filtered to its own tipo', async () => {
    setRole('CONSULTA');
    render(<MovimientoTab tipo="VENTAS" label="Ventas" />);

    expect(screen.getByText('Ventas')).toBeInTheDocument();
    await waitFor(() => expect(mockListarCargas).toHaveBeenCalledWith(
      expect.objectContaining({ tipo: 'VENTAS' })
    ));
  });

  it('shows "Subir archivo" for ADMIN and opens the upload modal scoped to its own tipo', async () => {
    setRole('ADMIN');
    render(<MovimientoTab tipo="INVENTARIO" label="Inventario" />);

    await waitFor(() => expect(screen.getByText('Subir archivo')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Subir archivo'));

    expect(screen.getByRole('dialog', { name: /Subir Inventario/i })).toBeInTheDocument();
  });

  it('shows "Subir archivo" for COMPRAS as well', async () => {
    setRole('COMPRAS');
    render(<MovimientoTab tipo="BACKORDER" label="Backorder" />);

    await waitFor(() => expect(screen.getByText('Subir archivo')).toBeInTheDocument());
  });

  it('hides "Subir archivo" for read-only roles (SUCURSAL/CONSULTA)', async () => {
    setRole('SUCURSAL');
    render(<MovimientoTab tipo="VENTAS" label="Ventas" />);

    await waitFor(() => expect(mockListarCargas).toHaveBeenCalled());
    expect(screen.queryByText('Subir archivo')).not.toBeInTheDocument();
  });

  it('refreshes the history table after a successful upload', async () => {
    setRole('ADMIN');
    mockSubir.mockResolvedValue({ carga_id: 'c1', duplicado_de: null });
    render(<MovimientoTab tipo="FACTURAS_PEDIDOS" label="Facturas de pedidos" />);

    await waitFor(() => expect(mockListarCargas).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByText('Subir archivo'));
    const dialog = screen.getByRole('dialog');
    const input = dialog.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [xlsxFile()] } });
    fireEvent.click(within(dialog).getByText('Subir archivo'));

    await waitFor(() => expect(mockListarCargas).toHaveBeenCalledTimes(2));
  });
});
