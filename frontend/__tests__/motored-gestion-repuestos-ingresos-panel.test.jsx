/**
 * Panel "Ingresos facturas" (Gestión repuestos): KPIs, por-tienda table
 * ordered by invoices that arrived but were not ingresadas, detalle with
 * filters and a lazy per-invoice history, the empty state when no ingreso is
 * loaded, and the confirm buttons that only COORDINADOR_REPUESTOS gets.
 */
import React from 'react';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockResumen = jest.fn();
const mockPorTienda = jest.fn();
const mockDetalle = jest.fn();
const mockHistorial = jest.fn();
const mockConfirmar = jest.fn();

jest.mock('../lib/motored/gestionRepuestosApi', () => ({
  getIngresosResumen: (...a) => mockResumen(...a),
  getIngresosPorTienda: (...a) => mockPorTienda(...a),
  getIngresosDetalle: (...a) => mockDetalle(...a),
  getIngresosHistorial: (...a) => mockHistorial(...a),
  confirmarIngreso: (...a) => mockConfirmar(...a),
}));

import IngresosFacturasPanel from '../components/motored/gestion-repuestos/IngresosFacturasPanel';

const CALI = 'id-cali';
const PASTO = 'id-pasto';

const RESUMEN = {
  verificable_desde: '2026-09-07',
  resumen: {
    pendientes: 147, llegaron_sin_ingresar: 23, sin_confirmar: 98,
    aun_no_llegan: 26, mas_antigua: 31, valor_pendiente: 1000000,
  },
};
const TIENDAS = {
  verificable_desde: '2026-09-07',
  tiendas: [
    { sucursal_id: PASTO, tienda: 'Pasto', pendientes: 12, llegaron_sin_ingresar: 1,
      sin_confirmar: 8, aun_no_llegan: 3, mas_antigua: 31, valor_pendiente: 500000 },
    { sucursal_id: CALI, tienda: 'Cali Norte', pendientes: 9, llegaron_sin_ingresar: 6,
      sin_confirmar: 2, aun_no_llegan: 1, mas_antigua: 12, valor_pendiente: 300000 },
  ],
};
const item = (numero, tienda, id, estado, dias, extra = {}) => ({
  prefijo_rh: 'RH', numero_rh: numero, factura: `RH ${numero}`, sucursal_id: id,
  tienda, fecha: '2026-09-07', dias, unidades: 14, valor: 1912400, estado,
  confirmado_por: null, confirmado_en: null, ...extra,
});
const DETALLE = {
  verificable_desde: '2026-09-07',
  items: [
    item(471208, 'Pasto', PASTO, 'LLEGO', 31, {
      confirmado_por: 'Carlos Ruiz', confirmado_en: '2026-10-06T16:20:00+00:00' }),
    item(482915, 'Cali Norte', CALI, 'SIN_CONFIRMAR', 1),
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  mockResumen.mockResolvedValue(RESUMEN);
  mockPorTienda.mockResolvedValue(TIENDAS);
  mockDetalle.mockResolvedValue(DETALLE);
  mockHistorial.mockResolvedValue({ historial: [] });
});

const abrir = async (props = {}) => {
  render(<IngresosFacturasPanel {...props} />);
  await screen.findByText('RH 471208');
};

test('shows the header date and the five KPIs, "Llegaron sin ingresar" included', async () => {
  await abrir();
  expect(screen.getByText(/Verificable desde el 07\/09\/2026/)).toBeInTheDocument();
  const kpi = (nombre) => screen.getByText(nombre, { selector: 'p' }).closest('div');
  expect(within(kpi('Pendientes')).getByText('147')).toBeInTheDocument();
  expect(within(kpi('Llegaron sin ingresar')).getByText('23')).toBeInTheDocument();
  expect(within(kpi('Sin confirmar')).getByText('98')).toBeInTheDocument();
  expect(within(kpi('Aún no llegan')).getByText('26')).toBeInTheDocument();
  expect(within(kpi('Más antigua')).getByText('31 días')).toBeInTheDocument();
});

test('orders the stores by invoices that arrived without ingreso', async () => {
  await abrir();
  const tabla = screen.getByRole('table', { name: /por tienda/i });
  const filas = within(tabla).getAllByRole('row').slice(1);
  expect(within(filas[0]).getByText('Cali Norte')).toBeInTheDocument();
  expect(within(filas[1]).getByText('Pasto')).toBeInTheDocument();
});

test('picking a store row filters the detalle by that store', async () => {
  await abrir();
  const tabla = screen.getByRole('table', { name: /por tienda/i });
  await userEvent.click(within(tabla).getByText('Pasto'));
  await waitFor(() => expect(mockDetalle).toHaveBeenLastCalledWith(
    expect.objectContaining({ sucursal: PASTO })));
  expect(screen.getByLabelText('Tienda')).toHaveValue(PASTO);
});

test('the state and age filters query the detalle', async () => {
  await abrir();
  await userEvent.click(screen.getByRole('button', { name: 'Ya llegó sin ingresar' }));
  await waitFor(() => expect(mockDetalle).toHaveBeenLastCalledWith(
    expect.objectContaining({ estado: 'LLEGO' })));
  await userEvent.click(screen.getByRole('button', { name: '> 15 días' }));
  await waitFor(() => expect(mockDetalle).toHaveBeenLastCalledWith(
    expect.objectContaining({ estado: 'LLEGO', min_dias: 15 })));
});

test('the detalle shows the state chip, last change and the count', async () => {
  await abrir();
  const fila = screen.getByText('RH 471208').closest('tr');
  expect(within(fila).getByText('Ya llegó sin ingresar')).toBeInTheDocument();
  expect(within(fila).getByText(/Carlos Ruiz/)).toBeInTheDocument();
  expect(within(fila).getByText('07/09/2026')).toBeInTheDocument();
  const otra = screen.getByText('RH 482915').closest('tr');
  expect(within(otra).getByText('Sin confirmar')).toBeInTheDocument();
  expect(screen.getByText(/Mostrando 2 de 147/)).toBeInTheDocument();
});

test('the historial opens on demand and lists who changed it', async () => {
  mockHistorial.mockResolvedValue({ historial: [
    { estado: 'LLEGO', por: 'Juan Pérez', canal: 'link', en: '2026-10-08T14:15:00+00:00' },
    { estado: 'NO_HA_LLEGADO', por: 'Ana Gómez', canal: 'link', en: '2026-10-07T21:02:00+00:00' },
  ] });
  await abrir();
  const fila = screen.getByText('RH 471208').closest('tr');
  await userEvent.click(within(fila).getByRole('button', { name: 'Historial' }));
  expect(mockHistorial).toHaveBeenCalledWith('RH 471208', PASTO);
  expect(await screen.findByText('Juan Pérez:')).toBeInTheDocument();
  expect(screen.getByText('Ana Gómez:')).toBeInTheDocument();
  await userEvent.click(within(fila).getByRole('button', { name: 'Ocultar' }));
  expect(screen.queryByText('Juan Pérez:')).not.toBeInTheDocument();
});

test('an invoice nobody answered shows the empty history text', async () => {
  await abrir();
  const fila = screen.getByText('RH 482915').closest('tr');
  await userEvent.click(within(fila).getByRole('button', { name: 'Historial' }));
  expect(await screen.findByText('Nadie ha respondido todavía.')).toBeInTheDocument();
});

test('with no ingreso loaded it explains how to start and shows no tables', async () => {
  mockResumen.mockResolvedValue({ verificable_desde: null, resumen: { ...RESUMEN.resumen, pendientes: 0 } });
  mockPorTienda.mockResolvedValue({ verificable_desde: null, tiendas: [] });
  mockDetalle.mockResolvedValue({ verificable_desde: null, items: [] });
  render(<IngresosFacturasPanel />);
  expect(await screen.findByText('Carga ingresos de facturas para empezar el seguimiento')).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('an empty filter result says so', async () => {
  await abrir();
  mockDetalle.mockResolvedValue({ verificable_desde: '2026-09-07', items: [] });
  await userEvent.click(screen.getByRole('button', { name: 'Sin confirmar' }));
  expect(await screen.findByText('No hay facturas con estos filtros.')).toBeInTheDocument();
});

test('a failed load shows an error', async () => {
  mockResumen.mockRejectedValue(new Error('x'));
  render(<IngresosFacturasPanel />);
  expect(await screen.findByRole('alert')).toBeInTheDocument();
});

test('read-only roles see no confirm buttons', async () => {
  await abrir();
  expect(screen.queryByRole('button', { name: 'Llegó' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'No ha llegado' })).not.toBeInTheDocument();
});

test('the coordinador confirms an invoice and the row updates', async () => {
  mockConfirmar.mockResolvedValue(item(482915, 'Cali Norte', CALI, 'LLEGO', 1, {
    confirmado_por: 'Coord', confirmado_en: '2026-10-08T15:00:00+00:00' }));
  await abrir({ puedeConfirmar: true });
  const fila = screen.getByText('RH 482915').closest('tr');
  await userEvent.click(within(fila).getByRole('button', { name: 'Llegó' }));
  expect(mockConfirmar).toHaveBeenCalledWith({
    factura: 'RH 482915', sucursal_id: CALI, estado: 'LLEGO' });
  await waitFor(() => expect(within(
    screen.getByText('RH 482915').closest('tr')).getByText('Ya llegó sin ingresar')).toBeInTheDocument());
});

test('a 409 on confirm tells the invoice is no longer pending', async () => {
  const error = Object.assign(new Error('Esta factura ya no está pendiente de ingreso.'), { status: 409 });
  mockConfirmar.mockRejectedValue(error);
  await abrir({ puedeConfirmar: true });
  const fila = screen.getByText('RH 482915').closest('tr');
  await userEvent.click(within(fila).getByRole('button', { name: 'No ha llegado' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('ya no está pendiente');
});
