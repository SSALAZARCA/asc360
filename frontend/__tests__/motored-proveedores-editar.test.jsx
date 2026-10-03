/**
 * Proveedores "Editar": the form sits above a long list, so editing must
 * bring the form into view, focus it, say which proveedor is being edited
 * and save through updateMaestro.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockListMaestros = jest.fn();
const mockUpdateMaestro = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  createMaestro: jest.fn(),
  updateMaestro: (...args) => mockUpdateMaestro(...args),
  deactivateMaestro: jest.fn(),
  reactivateMaestro: jest.fn(),
}));

import ProveedoresTab from '../components/motored/maestros/ProveedoresTab';

const HMCL = { id: 'p1', codigo: '900723988', nombre: 'HMCL', es_principal: true, activo: true };
const OTRO = { id: 'p2', codigo: 'OTRO', nombre: 'Otros', es_principal: false, activo: true };

beforeEach(() => {
  mockListMaestros.mockReset().mockResolvedValue([HMCL, OTRO]);
  mockUpdateMaestro.mockReset().mockResolvedValue({});
  Element.prototype.scrollIntoView = jest.fn();
});

async function editarOtro() {
  render(<ProveedoresTab />);
  await screen.findByText('Otros');
  const botones = screen.getAllByRole('button', { name: 'Editar' });
  fireEvent.click(botones[1]);
}

describe('ProveedoresTab edit', () => {
  it('loads the proveedor into the form', async () => {
    await editarOtro();
    expect(screen.getByDisplayValue('OTRO')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeInTheDocument();
  });

  it('brings the form into view and focuses its first field', async () => {
    await editarOtro();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByDisplayValue('OTRO')).toHaveFocus());
  });

  it('says which proveedor is being edited', async () => {
    await editarOtro();
    expect(screen.getByText(/Editando proveedor/)).toHaveTextContent('Otros');
  });

  it('saves the change through updateMaestro', async () => {
    await editarOtro();
    fireEvent.change(screen.getByDisplayValue('Otros'), { target: { value: 'Otros proveedores' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalledWith(
      'proveedores', 'p2', { codigo: 'OTRO', nombre: 'Otros proveedores', es_principal: false },
    ));
  });
});
