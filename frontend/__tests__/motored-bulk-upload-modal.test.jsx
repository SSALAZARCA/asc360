/**
 * Sucursales bulk upload: the "Activa" column.
 *
 * The backend validates the column strictly (only yes/no words; anything
 * else is a row error), so the CSV path must send the raw text untouched.
 * Coercing it here with the lenient boolean helper would turn a typo into
 * a silent "inactive".
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

function csvFile(content) {
  return new File([content], 'sucursales.csv', { type: 'text/csv' });
}

beforeEach(() => {
  mockValidarCarga.mockReset();
  mockSubirCarga.mockReset();
});

describe('BulkUploadModal — sucursal "Activa" column', () => {
  it('sends the raw Activa text so the backend can reject unknown values', async () => {
    mockSubirCarga.mockResolvedValue({ ok: true, total_filas: 3, errores: [] });
    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, {
      target: { files: [csvFile('Nombre,Activo\nCALI,No\nPASTO,tal vez\nNEIVA,\n')] },
    });
    await waitFor(() => expect(screen.getByText(/Vista previa/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText('Cargar'));

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalled());
    expect(mockSubirCarga).toHaveBeenCalledWith('sucursal', [
      { nombre: 'CALI', activa: 'No' },
      { nombre: 'PASTO', activa: 'tal vez' },
      { nombre: 'NEIVA', activa: '' },
    ]);
  });
});

describe('BulkUploadModal — sucursal "Sucursal principal" column', () => {
  it('lists the column with its tooltip', () => {
    render(<BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />);

    expect(screen.getByText('Sucursal principal')).toBeInTheDocument();
  });

  it('maps the "Tienda principal" header and sends the name untouched', async () => {
    mockSubirCarga.mockResolvedValue({ ok: true, total_filas: 2, errores: [] });
    const { container } = render(
      <BulkUploadModal entidad="sucursal" onClose={jest.fn()} onSuccess={jest.fn()} />
    );

    const input = container.querySelector('input[type="file"]');
    fireEvent.change(input, {
      target: { files: [csvFile('Nombre,Tienda principal\nEXPO 2,Medellín la 33\nLA 33,\n')] },
    });
    await waitFor(() => expect(screen.getByText(/Vista previa/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText('Cargar'));

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalled());
    expect(mockSubirCarga).toHaveBeenCalledWith('sucursal', [
      { nombre: 'EXPO 2', sucursal_principal: 'Medellín la 33' },
      { nombre: 'LA 33', sucursal_principal: '' },
    ]);
  });
});
