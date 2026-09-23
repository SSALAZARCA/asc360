/**
 * Tests for `UploadCargaModal` (sdd/motored-pedidos-ingesta, Phase 10, task
 * 10.3): the ADR-9 period-gating flow. Mirrors
 * `motored-bulk-upload-error-report.test.jsx`'s mocking convention (mock
 * `lib/motored/api`, import the component after the mock is registered).
 *
 * What's under test:
 * 1. A file whose type+period are both already resolved after `POST`
 *    (`requiere_tipo: false, requiere_periodo: false`) skips straight to
 *    the "listo" confirmation -- no gating step is shown.
 * 2. A file the server could NOT type-detect (`requiere_tipo: true`, e.g.
 *    an unrecognized-header file or a `MAESTRO_*` upload, which never
 *    auto-detects by design) MUST show the manual type selector and MUST
 *    NOT call `completarCarga` until a type is chosen.
 * 3. Choosing a type that declares a period (VENTAS) when none was given
 *    at upload time reveals the period inputs, and `completarCarga` is
 *    called with both `tipo` and `periodo_desde`/`periodo_hasta`.
 * 4. Declaring a period spanning more than one calendar month shows the
 *    "Cargas recurrentes: un mes por archivo" notice (design's own wording).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockSubir = jest.fn();
const mockCompletar = jest.fn();
const mockGetCarga = jest.fn();

jest.mock('../lib/motored/api', () => ({
  subirCargaMovimiento: (...args) => mockSubir(...args),
  completarCarga: (...args) => mockCompletar(...args),
  getCarga: (...args) => mockGetCarga(...args),
}));

import UploadCargaModal from '../components/motored/cargas/UploadCargaModal';

function xlsxFile(name = 'ventas.xlsx') {
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
  mockCompletar.mockReset();
  mockGetCarga.mockReset();
});

describe('UploadCargaModal — ADR-9 period gating', () => {
  it('goes straight to the confirmation step when tipo and período are already resolved', async () => {
    mockSubir.mockResolvedValue({
      carga_id: 'c1', tipo_detectado: 'FACTURAS_PEDIDOS', requiere_tipo: false, requiere_periodo: false, duplicado_de: null,
    });

    const onUploaded = jest.fn();
    const { container } = render(<UploadCargaModal onClose={jest.fn()} onUploaded={onUploaded} />);

    selectFile(container, xlsxFile('facturas.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(screen.getByText(/Carga recibida/i)).toBeInTheDocument());
    expect(mockCompletar).not.toHaveBeenCalled();
    expect(onUploaded).toHaveBeenCalled();
  });

  it('requires a manual type before continuing when the server could not detect one', async () => {
    mockSubir.mockResolvedValue({
      carga_id: 'c2', tipo_detectado: null, requiere_tipo: true, requiere_periodo: false, duplicado_de: null,
    });

    const { container } = render(<UploadCargaModal onClose={jest.fn()} onUploaded={jest.fn()} />);

    selectFile(container, xlsxFile('sin_tipo.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(screen.getByText(/no se pudo detectar automáticamente/i)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Guardar y continuar'));
    await waitFor(() => expect(screen.getByText(/Elegí un tipo de archivo/i)).toBeInTheDocument());
    expect(mockCompletar).not.toHaveBeenCalled();
  });

  it('shows period inputs and sends them once a period-declaring type is chosen', async () => {
    mockSubir.mockResolvedValue({
      carga_id: 'c3', tipo_detectado: null, requiere_tipo: true, requiere_periodo: false, duplicado_de: null,
    });
    mockCompletar.mockResolvedValue({ id: 'c3', estado: 'PENDIENTE' });

    const { container } = render(<UploadCargaModal onClose={jest.fn()} onUploaded={jest.fn()} />);

    selectFile(container, xlsxFile('ventas.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));
    await waitFor(() => expect(screen.getByText(/no se pudo detectar automáticamente/i)).toBeInTheDocument());

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'VENTAS' } });

    await waitFor(() => expect(screen.getByText(/Período declarado — desde/i)).toBeInTheDocument());

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-09-01' } });

    fireEvent.click(screen.getByText('Guardar y continuar'));

    await waitFor(() => expect(mockCompletar).toHaveBeenCalledWith('c3', {
      tipo: 'VENTAS',
      periodo_desde: '2026-09-01',
      periodo_hasta: '2026-09-01',
    }));
  });

  it('shows period inputs when a detected type is overridden, via "Cambiar tipo", to one that declares período', async () => {
    mockSubir.mockResolvedValue({
      carga_id: 'c6', tipo_detectado: 'FACTURAS_PEDIDOS', requiere_tipo: false, requiere_periodo: true, duplicado_de: null,
    });
    mockCompletar.mockResolvedValue({ id: 'c6', estado: 'PENDIENTE' });

    const { container } = render(<UploadCargaModal onClose={jest.fn()} onUploaded={jest.fn()} />);

    selectFile(container, xlsxFile('confundido.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));
    await waitFor(() => expect(screen.getByText(/Tipo detectado/i)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Cambiar tipo'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'VENTAS' } });

    await waitFor(() => expect(screen.getByText(/Período declarado — desde/i)).toBeInTheDocument());

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-09-01' } });
    fireEvent.click(screen.getByText('Guardar y continuar'));

    await waitFor(() => expect(mockCompletar).toHaveBeenCalledWith('c6', {
      tipo: 'VENTAS',
      periodo_desde: '2026-09-01',
      periodo_hasta: '2026-09-01',
    }));
  });

  it('shows the "un mes por archivo" notice when the declared range spans more than one month', async () => {
    mockSubir.mockResolvedValue({
      carga_id: 'c4', tipo_detectado: 'VENTAS', requiere_tipo: false, requiere_periodo: true, duplicado_de: null,
    });

    const { container } = render(<UploadCargaModal onClose={jest.fn()} onUploaded={jest.fn()} />);

    selectFile(container, xlsxFile('ventas_seed.xlsx'));
    fireEvent.click(screen.getByText('Subir archivo'));

    await waitFor(() => expect(screen.getByText(/Tipo detectado/i)).toBeInTheDocument());

    const dateInputs = container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-01-01' } });
    fireEvent.change(dateInputs[1], { target: { value: '2026-06-30' } });

    await waitFor(() => expect(screen.getByText('Cargas recurrentes: un mes por archivo.')).toBeInTheDocument());
  });
});
