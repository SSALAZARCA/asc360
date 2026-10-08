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
  getLineasComercialesCarga: jest.fn().mockResolvedValue([{ valor: 'Repuestos', etiqueta: 'Repuestos' }]),
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

async function fila(estado = 'VALIDADO') {
  render(<ErroresTab carga={{ id: 'c1', estado }} />);
  return screen.findByTestId('error-row');
}

async function crearReferencia(row) {
  fireEvent.click(within(row).getByRole('button', { name: 'Crear referencia' }));
  const dialogo = await screen.findByRole('dialog');
  await within(dialogo).findByRole('option', { name: 'Repuestos' });
  fireEvent.change(within(dialogo).getByLabelText(/Línea comercial/), { target: { value: 'Repuestos' } });
  fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear referencia' }));
}

it('says the referencia was created and to revalidate to include the rows', async () => {
  mockResolver.mockResolvedValue({ acciones_aplicadas: 1, acciones_ignoradas: 0 });
  const row = await fila();

  await crearReferencia(row);

  expect(await screen.findByRole('status')).toHaveTextContent(
    /Referencia 90605-200000S creada \(línea Repuestos\)\. Use 'Volver a validar'/
  );
  expect(within(screen.getByTestId('error-row')).getByText('Resuelta')).toBeInTheDocument();
});

it('says when the referencia already existed', async () => {
  mockResolver.mockResolvedValue({ acciones_aplicadas: 0, acciones_ignoradas: 1 });
  const row = await fila();

  await crearReferencia(row);

  expect(await screen.findByRole('status')).toHaveTextContent(/ya existía/);
});

it('still says the next carga when the carga can no longer be revalidated', async () => {
  mockResolver.mockResolvedValue({ acciones_aplicadas: 1, acciones_ignoradas: 0 });
  const row = await fila('APLICADO');

  await crearReferencia(row);

  expect(await screen.findByRole('status')).toHaveTextContent(/próxima carga/);
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
