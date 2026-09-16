/**
 * Tests for the `.xlsx` path of the Motored bulk-upload modal, introduced
 * in the batch adding server-side Excel parsing
 * (sdd/motored-pedidos-cimientos, post-Fase-6, owner brief "Excel upload
 * capability").
 *
 * Unlike `motored-bulk-upload-error-report.test.jsx` (which mocks
 * `lib/motored/api` entirely), this file mocks `global.fetch` directly and
 * leaves the real `lib/motored/api.js` / `lib/motored/motoredFetch.js` in
 * place -- the whole point is to PROVE the `.xlsx` path builds a real
 * `FormData` request instead of parsing the file client-side with
 * `papaparse`, which only `fetch`-level mocking can observe (mocking the
 * api module would hide exactly the thing under test).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

function xlsxFile(name = 'sucursales.xlsx') {
  return new File(['dummy-xlsx-bytes'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function csvFile(content, name = 'sucursales.csv') {
  return new File([content], name, { type: 'text/csv' });
}

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ ok: true, total_filas: 1 }),
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('BulkUploadModal — .xlsx path', () => {
  it('sends a FormData request instead of parsing the file client-side', async () => {
    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [xlsxFile()] } });

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());

    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toMatch(/\/carga\/excel\/validar$/);
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get('file')).toBeTruthy();
    expect(options.body.get('file').name).toBe('sucursales.xlsx');

    // No client-side CSV parsing/preview for the Excel path.
    expect(screen.queryByText(/Vista previa/i)).not.toBeInTheDocument();
  });

  it('shows the server validation result via the shared result panel', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ok: false,
        total_filas: 2,
        errores: [{ fila: 1, motivo: 'nombre: campo requerido' }],
      }),
    });

    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [xlsxFile()] } });

    await waitFor(() => {
      expect(screen.getByTestId('carga-error-row')).toBeInTheDocument();
    });
    expect(screen.getByText(/Fila 1: nombre: campo requerido/)).toBeInTheDocument();
  });

  it('posts the file to the real (non dry-run) endpoint when Cargar is clicked', async () => {
    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [xlsxFile()] } });
    await waitFor(() => expect(screen.getByText('Cargar')).not.toBeDisabled());

    fireEvent.click(screen.getByText('Cargar'));

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    const [url, options] = global.fetch.mock.calls[1];
    expect(url).toMatch(/\/carga\/excel$/);
    expect(options.body).toBeInstanceOf(FormData);
  });

  it('still parses .csv files client-side (unchanged behavior)', async () => {
    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, {
      target: { files: [csvFile('Nombre\nCALI NORTE\n')] },
    });

    await waitFor(() => expect(screen.getByText(/Vista previa/i)).toBeInTheDocument());
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
