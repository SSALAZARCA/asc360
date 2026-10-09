/**
 * Panel "Ingresos facturas": who enters each invoice ("Refs." and "Ingresa"
 * columns) and the "Descargar plantilla" button of the ERP template.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockDetalle = jest.fn();
const mockHistorial = jest.fn();
const mockConfirmar = jest.fn();
const mockDescargar = jest.fn();

jest.mock('../lib/motored/gestionRepuestosApi', () => ({
  getIngresosDetalle: (...a) => mockDetalle(...a),
  getIngresosHistorial: (...a) => mockHistorial(...a),
  confirmarIngreso: (...a) => mockConfirmar(...a),
  descargarPlantillaIngreso: (...a) => mockDescargar(...a),
}));

import IngresosFacturasPanel from '../components/motored/gestion-repuestos/IngresosFacturasPanel';

const item = (numero, id, estado, responsable, refs, puede) => ({
  prefijo_rh: 'RH', numero_rh: numero, factura: `RH ${numero}`, sucursal_id: id,
  tienda: 'Cali Norte', fecha: '2026-09-07', dias: 5, unidades: 14, valor: 1912400, estado,
  confirmado_por: null, confirmado_en: null,
  num_referencias: refs, responsable, puede_descargar_plantilla: puede,
});
const DETALLE = {
  verificable_desde: '2026-09-07',
  items: [
    item(100, 'id-1', 'LLEGO', 'ANALISTA', 25, true),
    item(101, 'id-2', 'SIN_CONFIRMAR', 'ANALISTA', 18, false),
    item(102, 'id-3', 'LLEGO', 'ASESOR', 4, false),
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  mockDetalle.mockResolvedValue(DETALLE);
  mockHistorial.mockResolvedValue({ historial: [] });
  mockDescargar.mockResolvedValue({ nombre: 'x.xlsx', omitidas: [] });
});

const abrir = async (props = {}) => {
  render(<IngresosFacturasPanel {...props} />);
  await screen.findByText('RH 100');
};
const fila = (factura) => screen.getByText(factura).closest('tr');

test('shows the references column and who enters each invoice', async () => {
  await abrir();
  const tabla = screen.getByRole('table', { name: 'Detalle' });
  expect(within(tabla).getByRole('columnheader', { name: 'Refs.' })).toBeInTheDocument();
  expect(within(tabla).getByRole('columnheader', { name: 'Ingresa' })).toBeInTheDocument();
  expect(within(fila('RH 100')).getByText('25')).toBeInTheDocument();
  expect(within(fila('RH 100')).getByText('Analista')).toBeInTheDocument();
  expect(within(fila('RH 102')).getByText('4')).toBeInTheDocument();
  expect(within(fila('RH 102')).getByText('Asesor')).toBeInTheDocument();
});

test('offers the template only on rows that can download it, to a role that may', async () => {
  await abrir({ puedeDescargar: true });
  expect(within(fila('RH 100')).getByRole('button', { name: 'Descargar plantilla' })).toBeInTheDocument();
  expect(within(fila('RH 102')).queryByRole('button', { name: 'Descargar plantilla' })).not.toBeInTheDocument();
});

test('an analista row not yet confirmed shows a muted hint, nothing clickable', async () => {
  await abrir({ puedeDescargar: true });
  expect(within(fila('RH 101')).queryByRole('button', { name: 'Descargar plantilla' })).not.toBeInTheDocument();
  expect(within(fila('RH 101')).getByText('Disponible al confirmar llegada')).toBeInTheDocument();
  expect(within(fila('RH 102')).queryByText('Disponible al confirmar llegada')).not.toBeInTheDocument();
});

test('a read-only role never sees the download button', async () => {
  await abrir({ puedeDescargar: false });
  expect(screen.queryByRole('button', { name: 'Descargar plantilla' })).not.toBeInTheDocument();
});

test('downloads the template of that invoice and store', async () => {
  await abrir({ puedeDescargar: true });
  await userEvent.click(within(fila('RH 100')).getByRole('button', { name: 'Descargar plantilla' }));
  expect(mockDescargar).toHaveBeenCalledWith('RH 100', 'id-1');
});

test('shows the backend detail when the download fails', async () => {
  mockDescargar.mockRejectedValue(new Error('La tienda Cali Norte no tiene bodega principal configurada.'));
  await abrir({ puedeDescargar: true });
  await userEvent.click(within(fila('RH 100')).getByRole('button', { name: 'Descargar plantilla' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('no tiene bodega principal');
});
