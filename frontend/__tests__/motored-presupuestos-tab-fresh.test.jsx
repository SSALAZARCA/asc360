/**
 * Presupuestos tab freshness (T3 review advisories): the month view refreshes
 * after Aplicar, ignores out-of-order detail responses, clears sticky errors,
 * and the editor shows the Spanish cap message.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MES, LISTA, TIENDAS } from './helpers/presupuestosFixtures';

const mockApi = {
  listarMesesPresupuesto: jest.fn(),
  listarTiendasPresupuesto: jest.fn(),
  getMesPresupuesto: jest.fn(),
  getVersionesPresupuesto: jest.fn(),
  guardarAsesorPresupuesto: jest.fn(),
  quitarAsesorPresupuesto: jest.fn(),
};
jest.mock('../lib/motored/presupuestosApi', () => new Proxy({}, { get: (_t, n) => (...a) => mockApi[n](...a) }));
jest.mock('../components/motored/maestros/presupuestos/CargaPresupuestosModal', () => ({
  __esModule: true,
  default: ({ onAplicado }) => (
    <button type="button" onClick={() => onAplicado({ meses: [{ mes: '2026-10', version: 3 }] })}>simular aplicar</button>
  ),
}));

import PresupuestosTab from '../components/motored/maestros/PresupuestosTab';

const deferred = () => {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const mesCon = (mes, nombre) => ({
  ...MES, mes, lineas: [{ ...MES.lineas[0], asesor: nombre }], por_tienda: [{ sucursal_id: 's1', tienda: 'Cali', asesores: 1, total: 1500000 }],
});

beforeEach(() => {
  Object.values(mockApi).forEach((f) => f.mockReset());
  mockApi.listarMesesPresupuesto.mockResolvedValue(LISTA);
  mockApi.listarTiendasPresupuesto.mockResolvedValue(TIENDAS);
  mockApi.getMesPresupuesto.mockResolvedValue(MES);
});

it('refetches the selected month detail after Aplicar so the newest version shows', async () => {
  render(<PresupuestosTab />);
  await screen.findByText('Ana Gómez');
  expect(mockApi.getMesPresupuesto).toHaveBeenCalledTimes(1);

  mockApi.listarMesesPresupuesto.mockResolvedValue([{ ...LISTA[0], version: 3 }, LISTA[1]]);
  mockApi.getMesPresupuesto.mockResolvedValue(mesCon('2026-10', 'Ana Nueva'));
  fireEvent.click(screen.getByRole('button', { name: 'Cargar presupuestos' }));
  fireEvent.click(await screen.findByRole('button', { name: 'simular aplicar' }));

  expect(await screen.findByText('Ana Nueva')).toBeInTheDocument();
});

it('ignores a slow detail response for a month that is no longer selected', async () => {
  const lento = deferred();
  render(<PresupuestosTab />);
  await screen.findByText('Ana Gómez');

  mockApi.getMesPresupuesto.mockImplementation((mes) => (mes === '2026-09'
    ? lento.promise : Promise.resolve(mesCon('2026-10', 'Octubre Fresco'))));
  fireEvent.change(screen.getByLabelText('Mes'), { target: { value: '2026-09' } });
  fireEvent.change(screen.getByLabelText('Mes'), { target: { value: '2026-10' } });
  await screen.findByText('Octubre Fresco');

  await act(async () => { lento.resolve(mesCon('2026-09', 'Septiembre Tardio')); });
  expect(screen.queryByText('Septiembre Tardio')).toBeNull();
  expect(screen.getByText('Octubre Fresco')).toBeInTheDocument();
});

it('clears a previous error after a successful month change', async () => {
  render(<PresupuestosTab />);
  await screen.findByText('Ana Gómez');
  mockApi.getMesPresupuesto.mockRejectedValueOnce(new Error('Falló el mes.'));
  fireEvent.change(screen.getByLabelText('Mes'), { target: { value: '2026-09' } });
  expect(await screen.findByRole('alert')).toHaveTextContent('Falló el mes.');

  mockApi.getMesPresupuesto.mockResolvedValue(mesCon('2026-10', 'Ana Gómez'));
  fireEvent.change(screen.getByLabelText('Mes'), { target: { value: '2026-10' } });

  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});

it('shows the Spanish cap message when the monto exceeds the maximum', async () => {
  render(<PresupuestosTab />);
  fireEvent.click(await screen.findByRole('button', { name: 'Agregar asesor' }));
  fireEvent.change(screen.getByLabelText('Cédula'), { target: { value: '444' } });
  fireEvent.change(screen.getByLabelText('Tienda'), { target: { value: 's1' } });
  fireEvent.change(screen.getByLabelText('Monto'), { target: { value: '100000000001' } });
  fireEvent.click(screen.getByRole('button', { name: 'Guardar cambio' }));

  expect(await screen.findByRole('alert')).toHaveTextContent('El presupuesto no puede superar 100.000.000.000 pesos');
  expect(mockApi.guardarAsesorPresupuesto).not.toHaveBeenCalled();
});
