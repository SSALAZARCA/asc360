/**
 * Tests for the Motored bulk-upload modal, introduced in:
 *   sdd/motored-pedidos-cimientos, Phase 6 (frontend, PR6), task 6.4
 *
 * Mirrors `catalog-upload.test.jsx`'s mocking convention (mock the fetch
 * helper module, import after the mock is registered). The one hard
 * requirement under test: given a `carga` response with `ok: false` and a
 * populated `errores` array, the modal renders EVERY row's error message,
 * not just a generic failure banner -- matching the backend's own
 * all-or-nothing guarantee that ALL row errors are reported in one pass
 * (`backend/app/motored/services/carga.py::procesar_carga`, owner decision
 * #1).
 *
 * Drives the REAL file-upload flow (a CSV `File` fed to the hidden
 * `<input type="file">`, parsed by the real `papaparse`), not a shortcut
 * around it -- this modal was rewritten from a raw-JSON textarea to a real
 * file picker specifically because the textarea version was unusable for
 * an actual business user, so the test must exercise the same path a real
 * user does.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockValidarCarga = jest.fn();
const mockSubirCarga = jest.fn();
jest.mock('../lib/motored/api', () => ({
  validarCarga: (...args) => mockValidarCarga(...args),
  subirCarga: (...args) => mockSubirCarga(...args),
}));

import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

function csvFile(content, name = 'sucursales.csv') {
  return new File([content], name, { type: 'text/csv' });
}

async function uploadCsv(container, content) {
  const input = container.querySelector('input[type="file"]');
  fireEvent.change(input, { target: { files: [csvFile(content)] } });
  await waitFor(() => expect(screen.getByText(/Vista previa/i)).toBeInTheDocument());
}

beforeEach(() => {
  mockValidarCarga.mockReset();
  mockSubirCarga.mockReset();
});

describe('BulkUploadModal — full error report', () => {
  it('renders every row error from a rejected (ok:false) carga response', async () => {
    mockSubirCarga.mockResolvedValue({
      ok: false,
      total_filas: 3,
      errores: [
        { fila: 1, motivo: 'nombre: campo requerido' },
        { fila: 2, motivo: 'sic: campo requerido' },
        { fila: 3, motivo: 'dias_seguridad: debe ser numérico' },
      ],
    });

    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    await uploadCsv(container, 'Nombre,SIC,Días de seguridad\nUno,,\nDos,,\nTres,,\n');
    fireEvent.click(screen.getByText('Cargar'));

    await waitFor(() => {
      expect(screen.getAllByTestId('carga-error-row')).toHaveLength(3);
    });

    expect(screen.getByText(/Fila 1: nombre: campo requerido/)).toBeInTheDocument();
    expect(screen.getByText(/Fila 2: sic: campo requerido/)).toBeInTheDocument();
    expect(screen.getByText(/Fila 3: dias_seguridad: debe ser numérico/)).toBeInTheDocument();

    // Not just a generic banner -- the per-row list must exist alongside it.
    expect(screen.getByTestId('carga-error-list')).toBeInTheDocument();
  });

  it('does not call onSuccess when the carga response is ok:false', async () => {
    mockSubirCarga.mockResolvedValue({
      ok: false,
      total_filas: 1,
      errores: [{ fila: 1, motivo: 'nombre: campo requerido' }],
    });
    const onSuccess = jest.fn();

    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={onSuccess} />
    );

    await uploadCsv(container, 'Nombre,SIC,Días de seguridad\nUno,,\n');
    fireEvent.click(screen.getByText('Cargar'));

    await waitFor(() => {
      expect(screen.getByTestId('carga-error-row')).toBeInTheDocument();
    });
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('rejects a file missing the required Nombre column before calling the API', async () => {
    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [csvFile('SIC,Días de seguridad\n1,2\n')] } });

    await waitFor(() => {
      expect(screen.getByText(/falta la columna obligatoria/i)).toBeInTheDocument();
    });
    expect(mockValidarCarga).not.toHaveBeenCalled();
    expect(mockSubirCarga).not.toHaveBeenCalled();
  });
});
