/**
 * INVENTARIO and BACKORDER are a snapshot at one moment: the upload asks for
 * a single "Fecha de corte" (sent as desde == hasta), never a date range.
 * VENTAS keeps its period range.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockSubir = jest.fn();
jest.mock('../lib/motored/api', () => ({
  subirCargaMovimiento: (...args) => mockSubir(...args),
  getCarga: jest.fn(),
  descargarPlantillaMovimiento: jest.fn(),
}));

import UploadMovimientoModal from '../components/motored/cargas/UploadMovimientoModal';

function elegirArchivo(container) {
  const input = container.querySelector('input[type="file"]');
  fireEvent.change(input, {
    target: { files: [new File(['x'], 'inv.xlsx')] },
  });
}

beforeEach(() => {
  mockSubir.mockReset().mockResolvedValue({ duplicado_de: null });
});

it.each(['INVENTARIO', 'BACKORDER'])(
  '%s asks for one cutoff date and sends it as the whole period',
  async (tipo) => {
    const { container } = render(
      <UploadMovimientoModal tipo={tipo} label={tipo} onClose={() => {}} onUploaded={() => {}} />
    );
    expect(screen.queryByText(/hasta/i)).toBeNull();
    elegirArchivo(container);
    fireEvent.change(screen.getByLabelText(/Fecha de corte/), {
      target: { value: '2026-10-05' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Subir archivo' }));

    await waitFor(() => expect(mockSubir).toHaveBeenCalled());
    expect(mockSubir.mock.calls[0][2]).toEqual({
      periodoDesde: '2026-10-05', periodoHasta: '2026-10-05',
    });
  }
);

it('INVENTARIO without a cutoff date is blocked with a clear message', () => {
  const { container } = render(
    <UploadMovimientoModal tipo="INVENTARIO" label="Inventario" onClose={() => {}} onUploaded={() => {}} />
  );
  elegirArchivo(container);

  fireEvent.click(screen.getByRole('button', { name: 'Subir archivo' }));

  expect(screen.getByText(/Declará la fecha de corte/)).toBeInTheDocument();
  expect(mockSubir).not.toHaveBeenCalled();
});

it('VENTAS keeps the period range', () => {
  render(
    <UploadMovimientoModal tipo="VENTAS" label="Ventas" onClose={() => {}} onUploaded={() => {}} />
  );
  expect(screen.getByText(/Período declarado — desde/)).toBeInTheDocument();
  expect(screen.getByText(/Período declarado — hasta/)).toBeInTheDocument();
});
