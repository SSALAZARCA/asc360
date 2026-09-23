/**
 * Tests for `CargasHistoryTable`'s `tipoFijo` mode (sdd/motored-cargas-
 * tipo-declarado, Phase 3, task 3.4/3.12; design D3). Mirrors the existing
 * Motored mocking convention (mock `lib/motored/api`, import the component
 * after the mock is registered).
 *
 * What's under test:
 * 1. `tipoFijo` hides the Tipo `<select>` entirely, keeps estado/fecha.
 * 2. `tipoFijo` is sent as the `tipo` filter on every `listarCargas` call,
 *    and survives a change to another filter (never dropped, never
 *    user-overridable).
 * 3. Without `tipoFijo`, the Tipo `<select>` is still there (unchanged
 *    behavior for any future non-fixed usage).
 * 4. Historical rows with a legacy `MAESTRO_BODEGAS`/`NULL` tipo still
 *    render a resolved label instead of breaking the grid (spec
 *    "Historical rows with legacy or missing tipo remain servable").
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockListarCargas = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listarCargas: (...args) => mockListarCargas(...args),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

import CargasHistoryTable from '../components/motored/cargas/CargasHistoryTable';

const CARGA_BASE = {
  id: 'c1', nombre_archivo: 'archivo.xlsx', estado: 'VALIDADO',
  periodo_desde: null, periodo_hasta: null,
  filas_leidas: 10, filas_validas: 10, filas_rechazadas: 0,
  created_at: '2026-08-01T00:00:00Z',
};

beforeEach(() => {
  mockListarCargas.mockReset().mockResolvedValue([]);
  pushMock.mockClear();
});

describe('CargasHistoryTable — tipoFijo', () => {
  it('hides the Tipo filter select when tipoFijo is set', async () => {
    render(<CargasHistoryTable tipoFijo="VENTAS" />);

    await waitFor(() => expect(mockListarCargas).toHaveBeenCalled());
    expect(screen.queryByText('Tipo')).not.toBeInTheDocument();
    expect(screen.getByText('Estado')).toBeInTheDocument();
    expect(screen.getByText('Desde')).toBeInTheDocument();
    expect(screen.getByText('Hasta')).toBeInTheDocument();
  });

  it('shows the Tipo filter select when tipoFijo is not set', async () => {
    render(<CargasHistoryTable />);

    await waitFor(() => expect(mockListarCargas).toHaveBeenCalled());
    expect(screen.getByText('Tipo')).toBeInTheDocument();
  });

  it('always sends tipoFijo as the tipo filter, even after changing another filter', async () => {
    render(<CargasHistoryTable tipoFijo="INVENTARIO" />);

    await waitFor(() => expect(mockListarCargas).toHaveBeenCalledWith(
      expect.objectContaining({ tipo: 'INVENTARIO' })
    ));

    const estadoSelects = screen.getAllByRole('combobox');
    fireEvent.change(estadoSelects[0], { target: { value: 'APLICADO' } });

    await waitFor(() => expect(mockListarCargas).toHaveBeenLastCalledWith(
      expect.objectContaining({ tipo: 'INVENTARIO', estado: 'APLICADO' })
    ));
  });

  it('shows an honest per-type empty state when tipoFijo has no rows', async () => {
    render(<CargasHistoryTable tipoFijo="VENTAS" />);

    await waitFor(() => expect(screen.getByText('Todavía no hay cargas de Ventas.')).toBeInTheDocument());
  });

  it('still renders a resolved label for a historical MAESTRO_BODEGAS row', async () => {
    mockListarCargas.mockResolvedValue([{ ...CARGA_BASE, tipo: 'MAESTRO_BODEGAS' }]);

    render(<CargasHistoryTable />);

    await waitFor(() => expect(screen.getByText('MAESTRO_BODEGAS')).toBeInTheDocument());
  });

  it('still renders and opens a historical row with tipo NULL', async () => {
    mockListarCargas.mockResolvedValue([{ ...CARGA_BASE, tipo: null }]);

    render(<CargasHistoryTable />);

    await waitFor(() => expect(screen.getByText('Sin tipo')).toBeInTheDocument());
    fireEvent.click(screen.getByText('archivo.xlsx'));
    expect(pushMock).toHaveBeenCalledWith('/motored/cargas/c1');
  });
});
