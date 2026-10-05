/**
 * Editing a store from a row far down the table: the form lives at the top,
 * so "Editar" brings it into view and says which store is being edited, and
 * a failed save brings the error into view too.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListMaestros = jest.fn();
const mockUpdateMaestro = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  createMaestro: jest.fn(),
  updateMaestro: (...args) => mockUpdateMaestro(...args),
  deactivateMaestro: jest.fn(),
  reactivateMaestro: jest.fn(),
}));

import SucursalesTab from '../components/motored/maestros/SucursalesTab';

const SUC = {
  id: 's1', nombre: 'NORTE', codigo_co: 'E05', sic: '1', dias_seguridad: '2.5',
  bodega_principal: 'BE051', activa: true, bodegas_secundarias: [],
};

let scroll;

beforeEach(() => {
  scroll = jest.fn();
  Element.prototype.scrollIntoView = scroll;
  mockListMaestros.mockReset().mockResolvedValue([SUC]);
  mockUpdateMaestro.mockReset();
});

afterEach(() => {
  delete Element.prototype.scrollIntoView;
});

async function editar() {
  render(<SucursalesTab />);
  const table = await screen.findByRole('table');
  fireEvent.click(within(table).getByRole('button', { name: 'Editar' }));
}

it('brings the form into view and names the store being edited', async () => {
  await editar();

  expect(scroll).toHaveBeenCalled();
  expect(screen.getByText(/Editando: NORTE/)).toBeInTheDocument();
});

it('brings a failed save into view', async () => {
  mockUpdateMaestro.mockRejectedValue(new Error('La bodega BX ya es de OTRA'));
  await editar();
  scroll.mockClear();

  fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

  await waitFor(() => expect(screen.getByText('La bodega BX ya es de OTRA')).toBeInTheDocument());
  expect(scroll).toHaveBeenCalled();
});
