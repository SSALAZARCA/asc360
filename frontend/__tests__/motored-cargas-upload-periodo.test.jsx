/**
 * Tests for `UploadMovimientoModal` (sdd/motored-cargas-tipo-declarado,
 * Phase 3, task 3.11 -- rewritten from the retired 2-step `UploadCargaModal`
 * flow). Mirrors `motored-bulk-upload-error-report.test.jsx`'s mocking
 * convention (mock `lib/motored/api`, import the component after the mock
 * is registered).
 *
 * What's under test now that `tipo` is DECLARED (never detected/completed):
 * 1. A type that does NOT declare a period (FACTURAS_PEDIDOS) shows no
 *    period inputs at all and goes straight to the confirmation step after
 *    `subirCargaMovimiento(file, tipo, {...})` resolves.
 * 2. A type that DOES declare a period (VENTAS) shows the period inputs
 *    UP FRONT (before any file is even chosen) -- design D3: the tab
 *    already knows its own type, so there is nothing to wait for.
 * 3. Submitting a period-declaring type without a "desde" date is blocked
 *    client-side with an explicit message, never silently sent.
 * 4. Declaring a period spanning more than one calendar month shows the
 *    "Cargas recurrentes: un mes por archivo" notice (unchanged wording).
 * 5. A duplicate-hash response still surfaces the informational (never
 *    blocking) duplicate notice.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockSubir = jest.fn();
const mockGetCarga = jest.fn();

jest.mock('../lib/motored/api', () => ({
  subirCargaMovimiento: (...args) => mockSubir(...args),
  getCarga: (...args) => mockGetCarga(...args),
}));

import UploadMovimientoModal from '../components/motored/cargas/UploadMovimientoModal';

function xlsxFile(name = 'archivo.xlsx') {
  return new File(['dummy'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function selectFile(container, file) {
  const input = container.querySelector('input[type="file"]');
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  mockSubir.mockReset();
  mockGetCarga.mockReset();
});

describe('UploadMovimientoModal — declared tipo, one-step upload', () => {
  it('does not show period inputs for a type that does not declare a period, and uploads with just the file', async () => {
    mockSubir.mockResolvedValue({ carga_id: 'c1', duplicado_de: null });
    const onUploaded = jest.fn();

    const { container } = render(
      <UploadMovimientoModal tipo="FACTURAS_PEDIDOS" label="Facturas de pedidos" onClose={jest.fn()} onUploaded={onUploaded} />
    );

    expect(screen.queryByText(/Período declarado/i)).not.toBeInTheDocument();

    selectFile(container, xlsxFile('facturas.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(screen.getByText(/Carga recibida/i)).toBeInTheDocument());
    expect(mockSubir).toHaveBeenCalledWith(
      expect.any(File), 'FACTURAS_PEDIDOS', { periodoDesde: '', periodoHasta: '' }
    );
    expect(onUploaded).toHaveBeenCalled();
  });

  it('shows period inputs up front for a type that declares a period, before any file is chosen', () => {
    render(<UploadMovimientoModal tipo="VENTAS" label="Ventas" onClose={jest.fn()} onUploaded={jest.fn()} />);

    expect(screen.getByText(/Período declarado — desde/i)).toBeInTheDocument();
  });

  it('blocks submission of a period-declaring type without a "desde" date', async () => {
    const { container } = render(
      <UploadMovimientoModal tipo="VENTAS" label="Ventas" onClose={jest.fn()} onUploaded={jest.fn()} />
    );

    selectFile(container, xlsxFile('ventas.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(screen.getByText(/Declará el período de este archivo/i)).toBeInTheDocument());
    expect(mockSubir).not.toHaveBeenCalled();
  });

  it('sends the declared period alongside tipo and file once "desde" is filled', async () => {
    mockSubir.mockResolvedValue({ carga_id: 'c2', duplicado_de: null });

    const { container } = render(
      <UploadMovimientoModal tipo="VENTAS" label="Ventas" onClose={jest.fn()} onUploaded={jest.fn()} />
    );

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-09-01' } });
    selectFile(container, xlsxFile('ventas.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(mockSubir).toHaveBeenCalledWith(
      expect.any(File), 'VENTAS', { periodoDesde: '2026-09-01', periodoHasta: '2026-09-01' }
    ));
  });

  it('shows the "un mes por archivo" notice when the declared range spans more than one month', () => {
    const { container } = render(
      <UploadMovimientoModal tipo="VENTAS" label="Ventas" onClose={jest.fn()} onUploaded={jest.fn()} />
    );

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-01-01' } });
    fireEvent.change(dateInputs[1], { target: { value: '2026-06-30' } });

    expect(screen.getByText('Cargas recurrentes: un mes por archivo.')).toBeInTheDocument();
  });

  it('surfaces the duplicate-hash notice without blocking the upload', async () => {
    mockSubir.mockResolvedValue({ carga_id: 'c3', duplicado_de: 'c-previa' });
    mockGetCarga.mockResolvedValue({ created_at: '2026-08-01T00:00:00Z' });

    const { container } = render(
      <UploadMovimientoModal tipo="FACTURAS_PEDIDOS" label="Facturas de pedidos" onClose={jest.fn()} onUploaded={jest.fn()} />
    );

    selectFile(container, xlsxFile('facturas.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(screen.getByText(/Ya existe una carga idéntica/i)).toBeInTheDocument());
    expect(screen.getByText(/Carga recibida/i)).toBeInTheDocument();
  });
});
