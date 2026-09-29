/**
 * `ReferenciasTab` table and single-record form. The table shows 7 business
 * columns (exact labels, in order): Código, Código del proveedor, Nombre,
 * Línea comercial, Unidad de empaque, Precio Normal antes de IVA, Precio
 * Público antes de IVA. "Código de referencia sustituta" and "Homologados
 * otras marcas" are hidden from the table (business decision) but stay as
 * form fields. `precio_venta` is no longer shown.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListMaestros = jest.fn();
const mockCreateMaestro = jest.fn();
const mockUpdateMaestro = jest.fn();
const mockBuscarReferencias = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  createMaestro: (...args) => mockCreateMaestro(...args),
  updateMaestro: (...args) => mockUpdateMaestro(...args),
  deactivateMaestro: jest.fn(),
  buscarReferencias: (...args) => mockBuscarReferencias(...args),
  listLineasComerciales: () => Promise.resolve(['REPUESTOS']),
  buscarSustitutas: () => Promise.resolve([]),
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
    precio_publico: '250.00', sustituida_por: 'r-old', sustituta_codigo: 'REF-OLD', homologados: ['YAM-1', 'HON-2'], activa: true,
  },
  {
    id: 'r-p2', codigo: 'REF-P2', proveedor_id: 'p2', nombre: 'De otro proveedor', linea_comercial: null,
    unidad_empaque: 1, unidad_empaque_advertencia: false, precio_normal: null, precio_venta: null,
    precio_publico: null, sustituida_por: null, homologados: [], activa: true,
  },
];

function pagina(items) {
  return Promise.resolve({ items, total: items.length, page: 1, page_size: 50 });
}

beforeEach(() => {
  mockListMaestros.mockReset().mockResolvedValue(PROVEEDORES);
  mockBuscarReferencias.mockReset().mockImplementation(() => pagina(REFERENCIAS));
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

// Intl may emit a non-breaking space between "$" and the amount.
function normalizeSpaces(text) {
  return text.replace(/\s+/g, ' ');
}

function headerLabels(table) {
  return within(table).getAllByRole('columnheader').map(headerLabel);
}

function rowFor(table, codigo) {
  return within(table).getAllByRole('row').find((row) => within(row).queryByRole('cell', { name: codigo }));
}

describe('ReferenciasTab — table', () => {
  it('shows the 7 business columns in order (then Estado and actions)', async () => {
    const table = await renderTab();

    expect(headerLabels(table).slice(0, 7)).toEqual([
      'Código',
      'Código del proveedor',
      'Nombre',
      'Línea comercial',
      'Unidad de empaque',
      'Precio Normal antes de IVA',
      'Precio Público antes de IVA',
    ]);
    expect(headerLabels(table)[7]).toBe('Estado');
  });

  it('hides the sustituta and homologados columns from the table', async () => {
    const table = await renderTab();
    const labels = headerLabels(table);

    expect(labels).not.toContain('Código de referencia sustituta');
    expect(labels).not.toContain('Homologados otras marcas');
    const cells = within(rowFor(table, 'REF-NEW')).getAllByRole('cell').map((td) => td.textContent);
    expect(cells[1]).toBe('HMCL');
    expect(cells).not.toContain('REF-OLD');
    expect(cells).not.toContain('YAM-1, HON-2');
  });

  it('shows both prices as rounded Colombian pesos, right-aligned with their headers', async () => {
    const conPrecios = { ...REFERENCIAS[2], id: 'r-cop', codigo: 'REF-COP', precio_normal: '12746.44', precio_publico: '361815.10' };
    mockBuscarReferencias.mockImplementation(() => pagina([...REFERENCIAS, conPrecios]));
    const table = await renderTab();
    const cells = within(rowFor(table, 'REF-COP')).getAllByRole('cell');

    expect(normalizeSpaces(cells[5].textContent)).toBe('$ 12.746');
    expect(normalizeSpaces(cells[6].textContent)).toBe('$ 361.815');
    expect(cells[5]).toHaveStyle({ textAlign: 'right' });
    expect(cells[6]).toHaveStyle({ textAlign: 'right' });
    ['Precio Normal antes de IVA', 'Precio Público antes de IVA'].forEach((label) => {
      const header = within(table).getAllByRole('columnheader').find((th) => headerLabel(th) === label);
      expect(header).toHaveStyle({ textAlign: 'right' });
    });
  });

  it('shows a dash for missing prices', async () => {
    const table = await renderTab();
    const cells = within(rowFor(table, 'REF-P2')).getAllByRole('cell').map((td) => td.textContent);

    expect(cells[5]).toBe('—');
    expect(cells[6]).toBe('—');
  });

  it('keeps the raw price in the edit form and sends it as a number', async () => {
    const table = await renderTab();
    fireEvent.click(within(rowFor(table, 'REF-NEW')).getByRole('button', { name: 'Editar' }));

    expect(screen.getByLabelText(/Precio Normal antes de IVA/i, { selector: 'input' })).toHaveValue('200.00');
    fireEvent.click(screen.getByText('Guardar cambios'));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2]).toMatchObject({ precio_normal: 200, precio_publico: 250 });
  });

  it('does not render homologados in the row, not even a long list', async () => {
    const largo = { ...REFERENCIAS[2], id: 'r-long', codigo: 'REF-LONG', homologados: ['A1', 'B2', 'C3', 'D4', 'E5'] };
    mockBuscarReferencias.mockImplementation(() => pagina([...REFERENCIAS, largo]));
    const table = await renderTab();
    const row = rowFor(table, 'REF-LONG');

    expect(within(row).queryByText(/A1/)).not.toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: /modelos/ })).not.toBeInTheDocument();
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
    ]));
  });
});

describe('ReferenciasTab — form', () => {
  it('keeps the sustituta and homologados fields in the form', async () => {
    await renderTab();
    fireEvent.click(within(rowFor(screen.getByRole('table'), 'REF-NEW')).getByRole('button', { name: 'Editar' }));

    expect(screen.getByRole('combobox', { name: /Código de referencia sustituta/ })).toHaveValue('REF-OLD');
    expect(screen.getByLabelText(/Homologados otras marcas/i, { selector: 'input' })).toBeInTheDocument();
  });

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

  it('labels the proveedor dropdown options with the proveedor codigo and styles every option on the page', async () => {
    await renderTab();

    const option = screen.getByRole('option', { name: /HMCL/ });
    expect(option.textContent).toContain('HMCL');
    screen.getAllByRole('option').forEach((opt) => {
      expect(opt.getAttribute('style')).toMatch(/color/);
    });
  });
});
