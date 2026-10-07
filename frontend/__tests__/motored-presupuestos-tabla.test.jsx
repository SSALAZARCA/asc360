/**
 * Maestros > Presupuestos month view as ONE flat table: one row per asesor
 * sorted by tienda then asesor, one column per active bonus line with the
 * asesor's minimum sale, a totals row, and the same Editar/Quitar callbacks.
 */
import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import MesPresupuesto from '../components/motored/maestros/presupuestos/MesPresupuesto';
import { formatCOP } from '../lib/motored/formatCOP';
import { MES } from './helpers/presupuestosFixtures';

const DETALLE = {
  ...MES,
  lineas: [
    { ...MES.lineas[0], minimos: { LUBRICANTES: 120000, CASCOS: 60000 } },
    { ...MES.lineas[1], minimos: { LUBRICANTES: 80000 } },
    { ...MES.lineas[2], minimos: { LUBRICANTES: 160000, CASCOS: 80000 } },
  ],
  lineas_bono: [
    { linea: 'LUBRICANTES', etiqueta: 'Lubricantes', pct_meta: 10, bono: 50000 },
    { linea: 'CASCOS', etiqueta: 'Cascos', pct_meta: 5, bono: 30000 },
  ],
  umbral_bono_pct: 80,
  totales_minimos: { LUBRICANTES: 360000, CASCOS: 140000 },
};

const renderTabla = (detalle = DETALLE) => {
  const onEditar = jest.fn();
  const onQuitar = jest.fn();
  render(<MesPresupuesto detalle={detalle} onEditar={onEditar} onQuitar={onQuitar} />);
  return { onEditar, onQuitar, tabla: screen.getByRole('table', { name: 'Presupuestos del mes' }) };
};

// The header's own label is its first text node; a line column also holds its tooltip text.
const encabezados = (tabla) => within(tabla).getAllByRole('columnheader').map((th) => th.firstChild?.textContent ?? '');
const filasCuerpo = (tabla) => within(tabla.querySelector('tbody')).getAllByRole('row');

it('renders one row per asesor sorted by tienda, then asesor', () => {
  const { tabla } = renderTabla();

  const filas = filasCuerpo(tabla).map((f) => within(f).getAllByRole('cell').slice(0, 3).map((c) => c.textContent));
  expect(filas).toEqual([
    ['Bogotá', 'Carla Díaz', '333'],
    ['Cali', 'Ana Gómez', '111'],
    ['Cali', 'Beto Ruiz', '222'],
  ]);
  expect(screen.queryByRole('region', { name: /Tienda/ })).toBeNull();
});

it('adds one column per bonus line, in lineas_bono order, titled with etiqueta', () => {
  const { tabla } = renderTabla();

  expect(encabezados(tabla)).toEqual(['Tienda', 'Asesor', 'Cédula', 'Presupuesto', 'Lubricantes', 'Cascos', 'Acciones']);
});

it('shows each minimum as COP and a dash when the line has no minimum', () => {
  const { tabla } = renderTabla();

  const beto = within(tabla).getByText('Beto Ruiz').closest('tr');
  const celdas = within(beto).getAllByRole('cell').map((c) => c.textContent);
  expect(celdas.slice(3, 6)).toEqual([formatCOP(1000000), formatCOP(80000), '—']);
});

it('ends with a totals row: total budget and the total minimum per line', () => {
  const { tabla } = renderTabla();

  const total = within(tabla.querySelector('tfoot')).getByRole('row');
  const celdas = within(total).getAllByRole('cell').map((c) => c.textContent);
  expect(celdas.slice(0, 1)).toEqual(['Total']);
  expect(celdas.slice(3, 6)).toEqual([formatCOP(4500000), formatCOP(360000), formatCOP(140000)]);
});

it('explains each line column with its threshold, target percent and bonus', () => {
  renderTabla();

  const nota = screen.getByRole('note', { name: /× 10 %\./ });
  const texto = nota.getAttribute('aria-label');
  expect(texto).toContain('cumple justo el 80 % de su presupuesto: presupuesto × 80 % × 10 %.');
  expect(texto).toContain('Si vende más, la meta real es el 10 % de su venta total.');
  expect(texto).toContain(`Solo se activa con cumplimiento ≥ 80 %. Bono: ${formatCOP(50000)}.`);
  expect(screen.getAllByRole('note', { name: /Venta mínima de la línea/ })).toHaveLength(2);
});

it('keeps Editar and Quitar calling back with the asesor line', () => {
  const { tabla, onEditar, onQuitar } = renderTabla();

  fireEvent.click(within(tabla).getByRole('button', { name: 'Editar Ana Gómez' }));
  fireEvent.click(within(tabla).getByRole('button', { name: 'Quitar Beto Ruiz' }));

  expect(onEditar).toHaveBeenCalledWith(DETALLE.lineas[0]);
  expect(onQuitar).toHaveBeenCalledWith(DETALLE.lineas[1]);
});

it('renders without line columns when there are no active bonus lines', () => {
  const { tabla } = renderTabla({ ...DETALLE, lineas_bono: [], totales_minimos: {} });

  expect(encabezados(tabla)).toEqual(['Tienda', 'Asesor', 'Cédula', 'Presupuesto', 'Acciones']);
  expect(filasCuerpo(tabla)).toHaveLength(3);
});

it('keeps the table inside the horizontal scroll box', () => {
  const { tabla } = renderTabla();

  expect(tabla.closest('.motored-table-scroll')).not.toBeNull();
});
