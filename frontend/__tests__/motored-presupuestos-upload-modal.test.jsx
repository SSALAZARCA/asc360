/**
 * Upload modal of the budgets: template, dry-run summary per month, errors
 * that block Aplicar, and the 422/409 messages of the apply.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockApi = {
  validarPresupuestos: jest.fn(),
  aplicarPresupuestos: jest.fn(),
  descargarPlantillaPresupuestos: jest.fn(),
};
jest.mock('../lib/motored/presupuestosApi', () => new Proxy({}, { get: (_t, n) => (...a) => mockApi[n](...a) }));

import CargaPresupuestosModal from '../components/motored/maestros/presupuestos/CargaPresupuestosModal';

const VALIDO = {
  valido: true, filas: 3, errores: [],
  warnings: [{ fila: 2, columna: 'Cédula', mensaje: 'El vendedor está inactivo' }],
  meses: [
    { mes: '2026-10', asesores: 2, total: 2500000, reemplaza_version: 1,
      por_tienda: [{ sucursal_id: 's1', tienda: 'Cali', asesores: 2, total: 2500000 }] },
    { mes: '2026-11', asesores: 1, total: 900000, reemplaza_version: null,
      por_tienda: [{ sucursal_id: 's2', tienda: 'Bogotá', asesores: 1, total: 900000 }] },
  ],
};
const INVALIDO = {
  valido: false, filas: 1, meses: [], warnings: [],
  errores: [{ fila: 1, columna: 'Tienda', mensaje: 'Tienda no encontrada' }],
};

const ARCHIVO = new File(['x'], 'oct.xlsx');

function setup(props = {}) {
  const onAplicado = jest.fn();
  const onClose = jest.fn();
  render(<CargaPresupuestosModal onAplicado={onAplicado} onClose={onClose} {...props} />);
  return { onAplicado, onClose };
}

function elegirArchivo() {
  fireEvent.change(screen.getByLabelText('Archivo de presupuestos'), { target: { files: [ARCHIVO] } });
}

beforeEach(() => {
  Object.values(mockApi).forEach((f) => f.mockReset());
  mockApi.validarPresupuestos.mockResolvedValue(VALIDO);
  mockApi.aplicarPresupuestos.mockResolvedValue({ meses: [{ mes: '2026-10', version: 2, asesores: 2, total: 2500000 }] });
});

it('downloads the template', () => {
  setup();
  fireEvent.click(screen.getByRole('button', { name: 'Descargar plantilla Excel' }));
  expect(mockApi.descargarPlantillaPresupuestos).toHaveBeenCalled();
});

it('keeps Validar disabled until a file is chosen', () => {
  setup();
  expect(screen.getByRole('button', { name: 'Validar' })).toBeDisabled();
  elegirArchivo();
  expect(screen.getByRole('button', { name: 'Validar' })).toBeEnabled();
});

it('shows the dry-run per month, with replaced version, new month and tienda totals', async () => {
  setup();
  elegirArchivo();
  fireEvent.click(screen.getByRole('button', { name: 'Validar' }));

  const oct = await screen.findByRole('region', { name: /2026-10/ });
  expect(within(oct).getByText(/reemplaza la versión 1/)).toBeInTheDocument();
  expect(within(oct).getByText('Cali')).toBeInTheDocument();
  expect(within(oct).getAllByText(/2\.500\.000/).length).toBeGreaterThan(0);
  const nov = screen.getByRole('region', { name: /2026-11/ });
  expect(within(nov).getByText(/mes nuevo/)).toBeInTheDocument();
  expect(screen.getByText('El vendedor está inactivo')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Aplicar' })).toBeEnabled();
});

it('lists the errors in a table and disables Aplicar', async () => {
  mockApi.validarPresupuestos.mockResolvedValue(INVALIDO);
  setup();
  elegirArchivo();
  fireEvent.click(screen.getByRole('button', { name: 'Validar' }));

  expect(await screen.findByText('Tienda no encontrada')).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Fila' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Columna' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Aplicar' })).toBeDisabled();
});

it('applies and reports the versions created', async () => {
  const { onAplicado } = setup();
  elegirArchivo();
  fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Aplicar' }));

  await waitFor(() => expect(mockApi.aplicarPresupuestos).toHaveBeenCalledWith(ARCHIVO));
  expect(await screen.findByText(/2026-10: versión 2/)).toBeInTheDocument();
  expect(onAplicado).toHaveBeenCalledWith({ meses: [{ mes: '2026-10', version: 2, asesores: 2, total: 2500000 }] });
});

it.each([
  ['422', Object.assign(new Error('El presupuesto tiene errores'), { status: 422, errores: [{ fila: 4, columna: 'Cédula', mensaje: 'No existe' }] }), /El presupuesto tiene errores/],
  ['409', Object.assign(new Error('Otra persona está modificando este presupuesto. Intente de nuevo.'), { status: 409 }), /Otra persona está modificando/],
])('shows the %s message of the apply', async (_n, error, texto) => {
  mockApi.aplicarPresupuestos.mockRejectedValue(error);
  setup();
  elegirArchivo();
  fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Aplicar' }));

  expect(await screen.findByRole('alert')).toHaveTextContent(texto);
  if (error.errores) expect(screen.getByText('No existe')).toBeInTheDocument();
});

it('shows a validation request failure and a new file clears the previous summary', async () => {
  mockApi.validarPresupuestos.mockRejectedValueOnce(new Error('El archivo no es .xlsx'));
  setup();
  elegirArchivo();
  fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('El archivo no es .xlsx');

  fireEvent.click(screen.getByRole('button', { name: 'Validar' }));
  await screen.findByRole('region', { name: /2026-10/ });
  elegirArchivo();
  expect(screen.queryByRole('region', { name: /2026-10/ })).toBeNull();
});
