/**
 * Panel "Ingresos facturas" (Gestión repuestos): KPIs, por-tienda table
 * ordered by invoices that arrived but were not ingresadas, detalle with
 * filters and a lazy per-invoice history, the empty state when no ingreso is
 * loaded, and the confirm buttons that only COORDINADOR_REPUESTOS gets.
 */
import React from 'react';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockDetalle = jest.fn();
const mockHistorial = jest.fn();
const mockConfirmar = jest.fn();

jest.mock('../lib/motored/gestionRepuestosApi', () => ({
  getIngresosDetalle: (...a) => mockDetalle(...a),
  getIngresosHistorial: (...a) => mockHistorial(...a),
  confirmarIngreso: (...a) => mockConfirmar(...a),
}));

import IngresosFacturasPanel from '../components/motored/gestion-repuestos/IngresosFacturasPanel';

const CALI = 'id-cali';
const PASTO = 'id-pasto';

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
    item(490001, 'Cali Norte', CALI, 'NO_HA_LLEGADO', 10, { unidades: 6, valor: 1000000 }),
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  mockDetalle.mockResolvedValue(DETALLE);
  mockHistorial.mockResolvedValue({ historial: [] });
});

const abrir = async (props = {}) => {
  render(<IngresosFacturasPanel {...props} />);
  await screen.findByText('RH 471208');
};

const kpi = (nombre) => screen.getByText(nombre, { selector: 'p' }).closest('div');
const filasTienda = () => within(screen.getByRole('table', { name: /por tienda/i })).getAllByRole('row').slice(1);
const valorKpi = (nombre, valor) => expect(within(kpi(nombre)).getByText(valor)).toBeInTheDocument();

test('shows the header date and the five KPIs derived from the detalle', async () => {
  await abrir();
  expect(screen.getByText(/Verificable desde el 07\/09\/2026/)).toBeInTheDocument();
  valorKpi('Pendientes', '3');
  valorKpi('Llegaron sin ingresar', '1');
  valorKpi('Sin confirmar', '1');
  valorKpi('Aún no llegan', '1');
  valorKpi('Más antigua', '31 días');
});

test('fetches the detalle once, without filters', async () => {
  await abrir();
  expect(mockDetalle).toHaveBeenCalledTimes(1);
  expect(mockDetalle).toHaveBeenCalledWith();
});

test('orders the stores by invoices that arrived without ingreso', async () => {
  await abrir();
  const filas = filasTienda();
  expect(within(filas[0]).getByText('Pasto')).toBeInTheDocument();
  expect(within(filas[1]).getByText('Cali Norte')).toBeInTheDocument();
});

test('the Estado filter updates the KPIs and the Por tienda rows without refetching', async () => {
  await abrir();
  await userEvent.click(screen.getByRole('button', { name: 'Sin confirmar' }));
  valorKpi('Pendientes', '1');
  valorKpi('Llegaron sin ingresar', '0');
  valorKpi('Más antigua', '1 días');
  expect(filasTienda()).toHaveLength(1);
  expect(within(filasTienda()[0]).getByText('Cali Norte')).toBeInTheDocument();
  expect(screen.getByText('Con los filtros aplicados')).toBeInTheDocument();
  expect(screen.queryByText('RH 471208')).not.toBeInTheDocument();
  expect(mockDetalle).toHaveBeenCalledTimes(1);
});

test('the Antigüedad filter updates the KPIs and the Por tienda rows', async () => {
  await abrir();
  await userEvent.click(screen.getByRole('button', { name: 'Más de 15 días' }));
  valorKpi('Pendientes', '1');
  valorKpi('Más antigua', '31 días');
  expect(filasTienda()).toHaveLength(1);
  expect(within(filasTienda()[0]).getByText('Pasto')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '8 a 15 días' }));
  valorKpi('Pendientes', '1');
  valorKpi('Más antigua', '10 días');
  expect(within(filasTienda()[0]).getByText('Cali Norte')).toBeInTheDocument();
});

test('the Tienda select updates the KPIs and keeps only that store in Por tienda', async () => {
  await abrir();
  await userEvent.selectOptions(screen.getByLabelText('Tienda'), CALI);
  valorKpi('Pendientes', '2');
  valorKpi('Llegaron sin ingresar', '0');
  expect(filasTienda()).toHaveLength(1);
  expect(screen.getByLabelText('Tienda')).toHaveValue(CALI);
  expect(screen.getByLabelText('Tienda').querySelectorAll('option')).toHaveLength(3);
});

test('the Por tienda row shows the sums of its invoices', async () => {
  await abrir();
  const cali = filasTienda().find((f) => within(f).queryByText('Cali Norte'));
  const celdas = within(cali).getAllByRole('cell').map((c) => c.textContent);
  expect(celdas.slice(1, 6)).toEqual(['2', '0', '1', '1', '10']);
});

test('clicking a store row selects it, clicking again clears it', async () => {
  await abrir();
  const tabla = screen.getByRole('table', { name: /por tienda/i });
  await userEvent.click(within(tabla).getByText('Pasto'));
  expect(screen.getByLabelText('Tienda')).toHaveValue(PASTO);
  valorKpi('Pendientes', '1');
  expect(screen.queryByText('RH 482915')).not.toBeInTheDocument();
  expect(within(filasTienda()[0]).getByText('Pasto').closest('tr')).toHaveAttribute('aria-selected', 'true');
  await userEvent.click(within(tabla).getByText('Pasto'));
  expect(screen.getByLabelText('Tienda')).toHaveValue('');
  valorKpi('Pendientes', '3');
});

test('shows the active filters and Limpiar resets them all', async () => {
  await abrir();
  expect(screen.queryByText(/Filtros activos/)).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText('Tienda'), CALI);
  await userEvent.click(screen.getByRole('button', { name: 'Sin confirmar' }));
  const linea = screen.getByText(/Filtros activos/);
  expect(linea).toHaveTextContent('Cali Norte');
  expect(linea).toHaveTextContent('Sin confirmar');
  await userEvent.click(screen.getByRole('button', { name: 'Limpiar' }));
  expect(screen.queryByText(/Filtros activos/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Tienda')).toHaveValue('');
  valorKpi('Pendientes', '3');
  expect(screen.getByText('Facturas sin ingresar en la red')).toBeInTheDocument();
});

test.each([
  ['Hasta 7 días', 1],
  ['8 a 15 días', 1],
  ['Más de 15 días', 1],
  ['Todas', 3],
])('the "%s" age pill keeps %s invoices', async (nombre, n) => {
  await abrir();
  const grupo = screen.getByRole('group', { name: 'Antigüedad' });
  await userEvent.click(within(grupo).getByRole('button', { name: nombre }));
  valorKpi('Pendientes', String(n));
  expect(within(grupo).getByRole('button', { name: nombre })).toHaveAttribute('aria-pressed', 'true');
});

test('the age pills carry the semáforo dot of their band', async () => {
  await abrir();
  const grupo = screen.getByRole('group', { name: 'Antigüedad' });
  const nivel = (nombre) => within(grupo).getByRole('button', { name: nombre }).querySelector('[data-nivel]')?.dataset.nivel;
  expect(nivel('Todas')).toBeUndefined();
  expect(nivel('Hasta 7 días')).toBe('normal');
  expect(nivel('8 a 15 días')).toBe('atencion');
  expect(nivel('Más de 15 días')).toBe('critico');
});

test('the detalle shows the state chip, last change and the count', async () => {
  await abrir();
  const fila = screen.getByText('RH 471208').closest('tr');
  expect(within(fila).getByText('Ya llegó sin ingresar')).toBeInTheDocument();
  expect(within(fila).getByText(/Carlos Ruiz/)).toBeInTheDocument();
  expect(within(fila).getByText('07/09/2026')).toBeInTheDocument();
  const otra = screen.getByText('RH 482915').closest('tr');
  expect(within(otra).getByText('Sin confirmar')).toBeInTheDocument();
  expect(screen.getByText(/Mostrando 3 de 3/)).toBeInTheDocument();
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
  mockDetalle.mockResolvedValue({ verificable_desde: null, items: [] });
  render(<IngresosFacturasPanel />);
  expect(await screen.findByText('Carga ingresos de facturas para empezar el seguimiento')).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('an empty filter result says so', async () => {
  await abrir();
  await userEvent.click(screen.getByRole('button', { name: 'Sin confirmar' }));
  await userEvent.click(screen.getByRole('button', { name: 'Más de 15 días' }));
  expect(await screen.findByText('No hay facturas con estos filtros.')).toBeInTheDocument();
});

test('a failed load shows an error', async () => {
  mockDetalle.mockRejectedValue(new Error('x'));
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
  mockDetalle.mockResolvedValue({ verificable_desde: '2026-09-07', items: [
    DETALLE.items[0],
    item(482915, 'Cali Norte', CALI, 'LLEGO', 1, { confirmado_por: 'Coord' }), DETALLE.items[2]] });
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

test('a confirmation refetches the detalle and the KPIs follow', async () => {
  mockConfirmar.mockResolvedValue(item(482915, 'Cali Norte', CALI, 'LLEGO', 1, {
    confirmado_por: 'Coord', confirmado_en: '2026-10-08T15:00:00+00:00' }));
  await abrir({ puedeConfirmar: true });
  mockDetalle.mockResolvedValue({ verificable_desde: '2026-09-07', items: [
    DETALLE.items[0],
    item(482915, 'Cali Norte', CALI, 'LLEGO', 1, { confirmado_por: 'Coord' }),
    DETALLE.items[2],
  ] });
  const fila = screen.getByText('RH 482915').closest('tr');
  await userEvent.click(within(fila).getByRole('button', { name: 'Llegó' }));
  await waitFor(() => expect(mockDetalle).toHaveBeenCalledTimes(2));
  await waitFor(() => valorKpi('Llegaron sin ingresar', '2'));
  valorKpi('Sin confirmar', '0');
});

test('a failed historial says so instead of claiming nobody answered', async () => {
  mockHistorial.mockRejectedValue(new Error('x'));
  await abrir();
  const fila = screen.getByText('RH 482915').closest('tr');
  await userEvent.click(within(fila).getByRole('button', { name: 'Historial' }));
  expect(await screen.findByText('No se pudo cargar el historial.')).toBeInTheDocument();
  expect(screen.queryByText('Nadie ha respondido todavía.')).not.toBeInTheDocument();
});
