/**
 * Cargas > Errores: every resolve action tells the user what happened and
 * marks the row as resolved, instead of leaving the screen unchanged.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockGetErrores = jest.fn();
const mockResolver = jest.fn();
jest.mock('../lib/motored/api', () => ({
  getErroresCarga: (...args) => mockGetErrores(...args),
  resolverErroresCarga: (...args) => mockResolver(...args),
  descargarErroresCargaCsv: jest.fn(),
  listMaestros: jest.fn().mockResolvedValue([]),
}));

import ErroresTab from '../components/motored/cargas/ErroresTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const REF = {
  id: 'e1', fila: 57232, columna: 'Referencia', valor: '90605-200000S',
  codigo_error: 'REFERENCIA_NO_ENCONTRADA', mensaje: 'No se encontró.',
};

beforeEach(() => {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'ADMIN' }));
  mockGetErrores.mockReset().mockResolvedValue([REF]);
  mockResolver.mockReset();
});

async function fila() {
  render(<ErroresTab carga={{ id: 'c1' }} />);
  return screen.findByTestId('error-row');
}

it('says the referencia was created and that the row loads next time', async () => {
  mockResolver.mockResolvedValue({ acciones_aplicadas: 1, acciones_ignoradas: 0 });
  const row = await fila();

  fireEvent.click(within(row).getByRole('button', { name: 'Crear como OTROS' }));

  expect(await screen.findByRole('status')).toHaveTextContent(
    /Referencia 90605-200000S creada.*próxima carga/
  );
  expect(within(screen.getByTestId('error-row')).getByText('Resuelta')).toBeInTheDocument();
});

it('says when the referencia already existed', async () => {
  mockResolver.mockResolvedValue({ acciones_aplicadas: 0, acciones_ignoradas: 1 });
  const row = await fila();

  fireEvent.click(within(row).getByRole('button', { name: 'Crear como OTROS' }));

  expect(await screen.findByRole('status')).toHaveTextContent(/ya existía/);
});

it('confirms an ignored row', async () => {
  mockResolver.mockResolvedValue({ acciones_aplicadas: 0, acciones_ignoradas: 1 });
  const row = await fila();

  fireEvent.click(within(row).getByRole('button', { name: 'Ignorar' }));

  expect(await screen.findByRole('status')).toHaveTextContent(/no se carga/);
  await waitFor(() => expect(
    within(screen.getByTestId('error-row')).getByText('Resuelta')
  ).toBeInTheDocument());
});
