/**
 * Ad-hoc bugfix (asc360, NOT tracked under any sdd/* change): the "Descargar
 * plantilla" button in `BulkUploadModal.js` used to build a CSV client-side
 * (`downloadTemplate`, via `papaparse`'s `Papa.unparse` + a `Blob`) -- that
 * version never wrote a UTF-8 BOM, so Excel on Windows misread the charset
 * and showed broken accents (e.g. "CÃ³digo" instead of "Código"). It now
 * calls the new server-side `.xlsx` endpoint (`lib/motored/api.js::
 * descargarPlantilla`) instead.
 *
 * Mirrors `motored-bulk-upload-error-report.test.jsx`'s mocking convention
 * (mock `lib/motored/api` entirely, import the component after the mock is
 * registered) -- the same convention `ErroresTab`'s own CSV-download button
 * is tested with (`motored-cargas-errores-csv.test.jsx`), since there is no
 * standalone unit test for `descargarErroresCargaCsv`/`descargarPlantilla`
 * themselves, only through the component that calls them.
 */
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';

const mockValidarCarga = jest.fn();
const mockSubirCarga = jest.fn();
const mockValidarCargaArchivo = jest.fn();
const mockSubirCargaArchivo = jest.fn();
const mockDescargarPlantilla = jest.fn();

jest.mock('../lib/motored/api', () => ({
  validarCarga: (...args) => mockValidarCarga(...args),
  subirCarga: (...args) => mockSubirCarga(...args),
  validarCargaArchivo: (...args) => mockValidarCargaArchivo(...args),
  subirCargaArchivo: (...args) => mockSubirCargaArchivo(...args),
  descargarPlantilla: (...args) => mockDescargarPlantilla(...args),
}));

import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

beforeEach(() => {
  mockDescargarPlantilla.mockReset().mockResolvedValue(undefined);
});

describe('BulkUploadModal — Descargar plantilla', () => {
  it('renders a button whose label no longer mentions CSV', () => {
    render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);

    expect(screen.queryByText('Descargar plantilla CSV')).not.toBeInTheDocument();
    expect(screen.getByText(/Descargar plantilla/i)).toBeInTheDocument();
  });

  it('calls descargarPlantilla with the exact entidad when clicked, instead of building a CSV client-side', () => {
    render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);

    fireEvent.click(screen.getByText(/Descargar plantilla/i));

    expect(mockDescargarPlantilla).toHaveBeenCalledWith('referencia');
  });

  it('uses the entidad prop for a different master too (sucursal)', () => {
    render(<BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />);

    fireEvent.click(screen.getByText(/Descargar plantilla/i));

    expect(mockDescargarPlantilla).toHaveBeenCalledWith('sucursal');
  });

  it('shows a visible error instead of failing silently when the download rejects (gga finding)', async () => {
    mockDescargarPlantilla.mockRejectedValueOnce(new Error('HTTP 403'));
    render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);

    fireEvent.click(screen.getByText(/Descargar plantilla/i));

    expect(await screen.findByText(/No se pudo descargar la plantilla/i)).toBeInTheDocument();
  });

  it('lists exactly the 9 referencia columns, in order, and no longer mentions precio de venta', () => {
    render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);

    const list = screen.getByRole('list');
    // Each item reads "<label> (obligatoria|opcional)" plus an optional tooltip.
    const labels = within(list).getAllByRole('listitem').map((li) => li.textContent.split(' (')[0]);
    expect(labels).toEqual([
      'Código',
      'Código del proveedor',
      'Nombre',
      'Línea comercial',
      'Unidad de empaque',
      'Precio Normal antes de IVA',
      'Precio Público antes de IVA',
      'Código de referencia sustituta',
      'Homologados otras marcas',
    ]);
    expect(screen.queryByText(/Precio de venta/i)).not.toBeInTheDocument();
  });

  it('describes homologados as compatible motorcycle models and allows a sustituta from the same file', () => {
    render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);

    const items = within(screen.getByRole('list')).getAllByRole('listitem');
    const homologados = items.find((li) => li.textContent.startsWith('Homologados otras marcas')).textContent;
    const sustituta = items.find((li) => li.textContent.startsWith('Código de referencia sustituta')).textContent;

    expect(homologados).toMatch(/modelos de moto/i);
    expect(homologados).not.toMatch(/c[oó]digos equivalentes/i);
    expect(sustituta).toMatch(/mismo archivo/i);
    expect(sustituta).toMatch(/mismo proveedor/i);
    expect(sustituta).not.toMatch(/homologados/i);
  });
});
