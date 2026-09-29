/**
 * Referencia 9-column layout (owner request 2026-09-28) -- `ReferenciasTab`
 * table and single-record form. Columns (exact labels, in order): Código,
 * Código del proveedor, Nombre, Línea comercial, Unidad de empaque, Precio
 * Normal antes de IVA, Precio Público antes de IVA, Código de referencia
 * sustituta, Homologados otras marcas. `precio_venta` is no longer shown.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListMaestros = jest.fn();
const mockCreateMaestro = jest.fn();
const mockUpdateMaestro = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  createMaestro: (...args) => mockCreateMaestro(...args),
  updateMaestro: (...args) => mockUpdateMaestro(...args),
  deactivateMaestro: jest.fn(),
}));

import ReferenciasTab from '../components/motored/maestros/ReferenciasTab';

const PROVEEDORES = [
  { id: 'p1', codigo: 'HMCL', nombre: 'HMCL Colombia' },
  { id: 'p2', codigo: 'OTROS', nombre: 'Otros proveedores' },
];
const REFERENCIAS = [
  {
    id: 'r-old', codigo: 'REF-OLD', proveedor_id: 'p1', nombre: 'Viejo', linea_comercial: 'REPUESTOS',
    unidad_empaque: 1, unidad_empaque_advertencia: false, precio_normal: '100.00', precio_venta: '999.00',
    precio_publico: '150.00', sustituida_por: null, homologados: [], activa: false,
  },
  {
    id: 'r-new', codigo: 'REF-NEW', proveedor_id: 'p1', nombre: 'Nuevo', linea_comercial: 'REPUESTOS',
    unidad_empaque: 2, unidad_empaque_advertencia: false, precio_normal: '200.00', precio_venta: '888.00',
    precio_publico: '250.00', sustituida_por: 'r-old', homologados: ['YAM-1', 'HON-2'], activa: true,
  },
  {
    id: 'r-p2', codigo: 'REF-P2', proveedor_id: 'p2', nombre: 'De otro proveedor', linea_comercial: null,
    unidad_empaque: 1, unidad_empaque_advertencia: false, precio_normal: null, precio_venta: null,
    precio_publico: null, sustituida_por: null, homologados: [], activa: true,
  },
];

beforeEach(() => {
  mockListMaestros.mockReset().mockImplementation((entidad) => (
    Promise.resolve(entidad === 'proveedores' ? PROVEEDORES : REFERENCIAS)
  ));
  mockCreateMaestro.mockReset().mockResolvedValue({});
  mockUpdateMaestro.mockReset().mockResolvedValue({});
});

async function renderTab() {
  render(<ReferenciasTab />);
  await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  await waitFor(() => expect(within(screen.getByRole('table')).getByText('REF-NEW')).toBeInTheDocument());
  return screen.getByRole('table');
}

// Header text without the tooltip's own text (the tooltip is role="note").
function headerLabel(header) {
  const note = within(header).queryByRole('note');
  return header.textContent.replace(note ? note.textContent : '', '').trim();
}

function headerLabels(table) {
  return within(table).getAllByRole('columnheader').map(headerLabel);
}

function rowFor(table, codigo) {
  return within(table).getAllByRole('row').find((row) => within(row).queryByRole('cell', { name: codigo }));
}

describe('ReferenciasTab — table', () => {
  it('shows the 9 business columns in order (then Estado and actions)', async () => {
    const table = await renderTab();

    expect(headerLabels(table).slice(0, 9)).toEqual([
      'Código',
      'Código del proveedor',
      'Nombre',
      'Línea comercial',
      'Unidad de empaque',
      'Precio Normal antes de IVA',
      'Precio Público antes de IVA',
      'Código de referencia sustituta',
      'Homologados otras marcas',
    ]);
  });

  it('shows the proveedor codigo, the substitute codigo and homologados joined with ", "', async () => {
    const table = await renderTab();
    const cells = within(rowFor(table, 'REF-NEW')).getAllByRole('cell').map((td) => td.textContent);

    expect(cells[1]).toBe('HMCL');
    expect(cells[5]).toBe('200.00');
    expect(cells[6]).toBe('250.00');
    expect(cells[7]).toBe('REF-OLD');
    expect(cells[8]).toBe('YAM-1, HON-2');
  });

  it('keeps a long homologados list on one line with a +N button instead of wrapping', async () => {
    const largo = { ...REFERENCIAS[2], id: 'r-long', codigo: 'REF-LONG', homologados: ['A1', 'B2', 'C3', 'D4', 'E5'] };
    mockListMaestros.mockImplementation((entidad) => (
      Promise.resolve(entidad === 'proveedores' ? PROVEEDORES : [...REFERENCIAS, largo])
    ));
    const table = await renderTab();
    const row = rowFor(table, 'REF-LONG');

    expect(within(row).getByText('A1, B2, C3')).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: 'Ver los 5 modelos' })).toHaveTextContent('+2');
  });

  it('no longer shows precio_venta anywhere', async () => {
    const table = await renderTab();

    expect(within(table).queryByText('888.00')).not.toBeInTheDocument();
    expect(screen.queryByText(/Precio venta/i)).not.toBeInTheDocument();
  });

  it('has hover tooltips for the non-obvious column headers', async () => {
    const table = await renderTab();
    const tooltipHeaders = within(table).getAllByRole('columnheader')
      .filter((th) => within(th).queryByRole('note'))
      .map(headerLabel);

    expect(tooltipHeaders).toEqual(expect.arrayContaining([
      'Código del proveedor',
      'Precio Normal antes de IVA',
      'Precio Público antes de IVA',
      'Código de referencia sustituta',
      'Homologados otras marcas',
    ]));
  });
  it('describes homologados as compatible motorcycle models of other brands, not part codes', async () => {
    const table = await renderTab();
    const header = within(table).getAllByRole('columnheader')
      .find((th) => headerLabel(th) === 'Homologados otras marcas');
    const tooltip = within(header).getByRole('note').textContent;

    expect(tooltip).toMatch(/modelos de moto/i);
    expect(tooltip).not.toMatch(/c[oó]digos/i);
  });

  it('the sustituta tooltip states the same-proveedor rule without pointing to homologados', async () => {
    const table = await renderTab();
    const header = within(table).getAllByRole('columnheader')
      .find((th) => headerLabel(th) === 'Código de referencia sustituta');
    const tooltip = within(header).getByRole('note').textContent;

    expect(tooltip).toMatch(/mismo proveedor/i);
    expect(tooltip).not.toMatch(/homologados/i);
  });
});

describe('ReferenciasTab — form', () => {
  it('edits homologados as a comma/semicolon separated text and sends a clean array', async () => {
    await renderTab();
    fireEvent.click(within(rowFor(screen.getByRole('table'), 'REF-NEW')).getByRole('button', { name: 'Editar' }));

    const input = screen.getByLabelText(/Homologados otras marcas/i, { selector: 'input' });
    expect(input.value).toBe('YAM-1, HON-2');

    fireEvent.change(input, { target: { value: ' YAM-1; SUZ-3 ,, YAM-1' } });
    fireEvent.click(screen.getByText('Guardar cambios'));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    const payload = mockUpdateMaestro.mock.calls[0][2];
    expect(payload.homologados).toEqual(['YAM-1', 'SUZ-3']);
    expect(payload).not.toHaveProperty('precio_venta');
  });

  it('labels the proveedor dropdown options with the proveedor codigo and styles every option', async () => {
    await renderTab();

    const option = screen.getByRole('option', { name: /HMCL/ });
    expect(option.textContent).toContain('HMCL');
    screen.getAllByRole('option').forEach((opt) => {
      expect(opt.getAttribute('style')).toMatch(/color/);
    });
  });

  it('only offers substitutes from the selected proveedor (never the row itself)', async () => {
    await renderTab();
    fireEvent.click(within(rowFor(screen.getByRole('table'), 'REF-NEW')).getByRole('button', { name: 'Editar' }));

    const sustituta = screen.getByLabelText(/Código de referencia sustituta/i, { selector: 'select' });
    const offered = within(sustituta).getAllByRole('option').map((o) => o.textContent);
    expect(offered).toContain('REF-OLD');
    expect(offered).not.toContain('REF-P2');
    expect(offered).not.toContain('REF-NEW');
    within(sustituta).getAllByRole('option').forEach((opt) => {
      expect(opt.getAttribute('style')).toMatch(/color/);
    });
  });

  it('clears the chosen substitute when the proveedor changes to one it does not belong to', async () => {
    await renderTab();
    fireEvent.click(within(rowFor(screen.getByRole('table'), 'REF-NEW')).getByRole('button', { name: 'Editar' }));

    const proveedor = screen.getByLabelText(/Código del proveedor/i, { selector: 'select' });
    fireEvent.change(proveedor, { target: { value: 'p2' } });

    const sustituta = screen.getByLabelText(/Código de referencia sustituta/i, { selector: 'select' });
    expect(sustituta.value).toBe('');
    const offered = within(sustituta).getAllByRole('option').map((o) => o.textContent);
    expect(offered).toContain('REF-P2');
    expect(offered).not.toContain('REF-OLD');
  });
});
