/**
 * Bodegas are now managed from the Sucursales upload ("Bodegas secundarias"):
 * the Bodegas tab is gone from Maestros, the Sucursales upload modal documents
 * the new column (and the link/unlink rules), the upload result reports what
 * was linked/unlinked, and the "bodega without sucursal" health warning shows
 * under the Sucursales tab.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockGetSalud = jest.fn();
const mockValidarCarga = jest.fn();
const mockSubirCarga = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getSalud: (...a) => mockGetSalud(...a),
  validarCarga: (...a) => mockValidarCarga(...a),
  subirCarga: (...a) => mockSubirCarga(...a),
  validarCargaArchivo: jest.fn(),
  subirCargaArchivo: jest.fn(),
  descargarPlantilla: jest.fn(),
}));
jest.mock('../app/motored/motored-layout', () => ({ __esModule: true, default: ({ children }) => <div>{children}</div> }));
jest.mock('../components/motored/maestros/SucursalesTab', () => ({ __esModule: true, default: () => <p>contenido sucursales</p> }));
jest.mock('../components/motored/maestros/BodegasTab', () => ({ __esModule: true, default: () => <p>contenido bodegas</p> }));
jest.mock('../components/motored/maestros/ProveedoresTab', () => ({ __esModule: true, default: () => <p>p</p> }));
jest.mock('../components/motored/maestros/ReferenciasTab', () => ({ __esModule: true, default: () => <p>r</p> }));
jest.mock('../components/motored/maestros/ClientesTecniredTab', () => ({ __esModule: true, default: () => <p>c</p> }));
jest.mock('../components/motored/maestros/VendedoresTab', () => ({ __esModule: true, default: () => <p>v</p> }));
jest.mock('../components/motored/cargas/MovimientoTab', () => ({ __esModule: true, default: () => <p>m</p> }));

import MaestrosPage from '../app/motored/maestros/page';
import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

beforeEach(() => {
  mockGetSalud.mockReset().mockResolvedValue({ estado: 'advertencia', hallazgos: [
    {
      tipo: 'bodega_sin_sucursal', entidad: 'sucursal', bloqueante: false,
      mensaje: "La bodega 'BA066' no está asociada a ninguna sucursal; agréguela en 'Bodegas secundarias' de su sucursal.",
    },
  ] });
  mockValidarCarga.mockReset();
  mockSubirCarga.mockReset();
});

describe('Maestros page', () => {
  it('no longer has a Bodegas tab', async () => {
    render(<MaestrosPage />);
    await screen.findByText('contenido sucursales');
    expect(screen.queryByRole('button', { name: /^Bodegas/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^Sucursales/ })).toBeInTheDocument();
  });

  it('shows the bodega-without-sucursal warning under the Sucursales tab', async () => {
    render(<MaestrosPage />);
    fireEvent.click(await screen.findByRole('button', { name: /1 advertencia/ }));
    expect(screen.getByText('BA066')).toBeInTheDocument();
  });
});

describe('Sucursales bulk upload modal', () => {
  it('lists the Bodegas secundarias column with its help text', () => {
    render(<BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />);
    expect(screen.getByText('Bodegas secundarias')).toBeInTheDocument();
    const ayuda = screen.getByRole('note', { name: /separad.s por coma/i });
    expect(ayuda).toBeInTheDocument();
  });

  it('explains how links and unlinks work', () => {
    render(<BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />);
    const nota = screen.getByTestId('nota-bodegas-secundarias');
    expect(nota).toHaveTextContent(/sin la columna no se toca ninguna bodega/i);
    expect(nota).toHaveTextContent(/celda en blanco desvincula/i);
    expect(nota).toHaveTextContent(/nunca se borran/i);
  });

  it('does not show the sucursal note on other masters', () => {
    render(<BulkUploadModal entidad="proveedor" onClose={jest.fn()} onSuccess={jest.fn()} />);
    expect(screen.queryByTestId('nota-bodegas-secundarias')).toBeNull();
  });

  it('reports the linked and unlinked bodegas after an upload', async () => {
    mockSubirCarga.mockResolvedValue({
      ok: true, total_filas: 2, insertados: 0, actualizados: 2,
      bodegas_secundarias: {
        vinculadas: [{ sucursal: 'CALI', bodega: 'BA066' }],
        desvinculadas: [{ sucursal: 'PASTO', bodega: 'BA075' }],
      },
    });
    const csv = 'Nombre,Bodega principal,Bodegas secundarias\nCALI,BA061,BA066\n';
    const { container } = render(<BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />);
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [new File([csv], 's.csv', { type: 'text/csv' })] },
    });
    const cargar = await screen.findByRole('button', { name: 'Cargar' });
    await waitFor(() => expect(cargar).not.toBeDisabled());
    fireEvent.click(cargar);

    const panel = await screen.findByTestId('resultado-bodegas-secundarias');
    expect(within(panel).getByText(/Vinculadas \(1\)/)).toBeInTheDocument();
    expect(within(panel).getByText(/CALI: BA066/)).toBeInTheDocument();
    expect(within(panel).getByText(/Desvinculadas \(1\)/)).toBeInTheDocument();
    expect(within(panel).getByText(/PASTO: BA075/)).toBeInTheDocument();
  });

  it('every <option> rendered by the modal carries an explicit text color', () => {
    const { container } = render(<BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />);
    container.querySelectorAll('option').forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });
});
