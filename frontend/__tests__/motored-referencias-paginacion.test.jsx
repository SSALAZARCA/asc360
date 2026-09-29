/**
 * Referencias pagination (`odd/tasks/motored-referencias-paginacion.md`, T2):
 * `ReferenciasTab` fetches only the current page, with a paginator, a
 * debounced search, línea comercial / estado filters, a refetch of the
 * current page after every write, and a server-side sustituta type-ahead.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockBuscarReferencias = jest.fn();
const mockBuscarSustitutas = jest.fn();
const mockCreateMaestro = jest.fn();
const mockUpdateMaestro = jest.fn();
const mockDeactivateMaestro = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: () => Promise.resolve([
    { id: 'p1', codigo: 'HMCL', nombre: 'HMCL Colombia' },
    { id: 'p2', codigo: 'OTROS', nombre: 'Otros proveedores' },
  ]),
  listLineasComerciales: () => Promise.resolve(['ACCESORIOS', 'REPUESTOS']),
  buscarReferencias: (...args) => mockBuscarReferencias(...args),
  buscarSustitutas: (...args) => mockBuscarSustitutas(...args),
  createMaestro: (...args) => mockCreateMaestro(...args),
  updateMaestro: (...args) => mockUpdateMaestro(...args),
  deactivateMaestro: (...args) => mockDeactivateMaestro(...args),
}));

import ReferenciasTab from '../components/motored/maestros/ReferenciasTab';

const REF_NEW = {
  id: 'r-new', codigo: 'REF-NEW', proveedor_id: 'p1', nombre: 'Nuevo', linea_comercial: 'REPUESTOS',
  unidad_empaque: 1, unidad_empaque_advertencia: false, precio_normal: '1.00', precio_publico: null,
  sustituida_por: 'r-old', sustituta_codigo: 'REF-OLD', homologados: [], activa: true,
};

beforeEach(() => {
  mockBuscarReferencias.mockReset().mockImplementation(({ page, pageSize }) => (
    Promise.resolve({ items: [REF_NEW], total: 120, page, page_size: pageSize })
  ));
  mockBuscarSustitutas.mockReset().mockResolvedValue([{ id: 'r-alt', codigo: 'REF-ALT', nombre: 'Alternativa' }]);
  mockCreateMaestro.mockReset().mockResolvedValue({});
  mockUpdateMaestro.mockReset().mockResolvedValue({});
  mockDeactivateMaestro.mockReset().mockResolvedValue({});
});

function lastQuery() {
  const { calls } = mockBuscarReferencias.mock;
  return calls[calls.length - 1][0];
}

async function renderTab() {
  render(<ReferenciasTab />);
  await screen.findByText('Página 1 de 3');
  await within(screen.getByRole('table')).findByText('REF-NEW');
}

async function goToPage2() {
  fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
  await screen.findByText('Página 2 de 3');
}

describe('ReferenciasTab — paginator', () => {
  it('fetches only the first page of 50 and shows the page position and total', async () => {
    await renderTab();

    expect(lastQuery()).toMatchObject({ page: 1, pageSize: 50 });
    expect(screen.getByText('120 referencias')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled();
  });

  it('moves between pages with Siguiente / Anterior', async () => {
    await renderTab();
    await goToPage2();
    expect(lastQuery()).toMatchObject({ page: 2 });

    fireEvent.click(screen.getByRole('button', { name: 'Anterior' }));
    await screen.findByText('Página 1 de 3');
    expect(lastQuery()).toMatchObject({ page: 1 });
  });

  it('disables Siguiente on the last page', async () => {
    mockBuscarReferencias.mockImplementation(({ page, pageSize }) => (
      Promise.resolve({ items: [REF_NEW], total: 1, page, page_size: pageSize })
    ));
    render(<ReferenciasTab />);

    await screen.findByText('Página 1 de 1');
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled();
  });

  it('changing the page size goes back to page 1 with the new size, and styles its options', async () => {
    await renderTab();
    await goToPage2();

    const porPagina = screen.getByLabelText('Por página', { selector: 'select' });
    within(porPagina).getAllByRole('option').forEach((opt) => expect(opt.getAttribute('style')).toMatch(/color/));
    fireEvent.change(porPagina, { target: { value: '100' } });

    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 1, pageSize: 100 }));
  });
});

describe('ReferenciasTab — search and filters', () => {
  it('debounces the search and resets to page 1', async () => {
    await renderTab();
    await goToPage2();
    const calls = mockBuscarReferencias.mock.calls.length;

    fireEvent.change(screen.getByLabelText('Buscar referencia'), { target: { value: 'filtro' } });
    expect(mockBuscarReferencias.mock.calls.length).toBe(calls);

    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 1, q: 'filtro' }));
  });

  it('filters by línea comercial, with options from the distinct endpoint', async () => {
    await renderTab();
    const linea = screen.getByLabelText('Filtrar por línea comercial');
    await within(linea).findByRole('option', { name: 'ACCESORIOS' });

    fireEvent.change(linea, { target: { value: 'ACCESORIOS' } });

    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 1, lineaComercial: 'ACCESORIOS' }));
  });

  it.each([
    ['Activas', true],
    ['Inactivas', false],
  ])('filters by estado %s', async (label, activa) => {
    await renderTab();
    const estado = screen.getByLabelText('Filtrar por estado');

    fireEvent.change(estado, { target: { value: within(estado).getByRole('option', { name: label }).value } });

    await waitFor(() => expect(lastQuery()).toMatchObject({ activa }));
  });

  it('starts with every estado (no activa filter)', async () => {
    await renderTab();

    expect(lastQuery().activa).toBeNull();
  });
});

describe('ReferenciasTab — refetch after writes', () => {
  it('refetches the current page after creating a referencia', async () => {
    await renderTab();
    await goToPage2();
    mockBuscarReferencias.mockClear();

    fireEvent.change(screen.getByLabelText('Código', { selector: 'input' }), { target: { value: 'NUEVA' } });
    fireEvent.change(screen.getByLabelText(/Código del proveedor/, { selector: 'select' }), { target: { value: 'p1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear referencia' }));

    await waitFor(() => expect(mockBuscarReferencias).toHaveBeenCalled());
    expect(lastQuery()).toMatchObject({ page: 2 });
  });

  it('refetches the current page after deactivating a referencia', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    await renderTab();
    await goToPage2();
    mockBuscarReferencias.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Desactivar' }));

    await waitFor(() => expect(mockDeactivateMaestro).toHaveBeenCalledWith('referencias', 'r-new'));
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 2 }));
    window.confirm.mockRestore();
  });
});

describe('ReferenciasTab — sustituta type-ahead', () => {
  async function editRefNew() {
    await renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    return screen.getByRole('combobox', { name: /Código de referencia sustituta/ });
  }

  it('shows the current sustituta by its código when editing', async () => {
    const input = await editRefNew();

    expect(input).toHaveValue('REF-OLD');
  });

  it('keeps an inactive current sustituta (A->B->C chain): shown by código and saved unchanged', async () => {
    // The search endpoint only suggests active referencias, but the current
    // value comes from the row's `sustituta_codigo`, never from the search.
    const input = await editRefNew();
    expect(input).toHaveValue('REF-OLD');
    expect(mockBuscarSustitutas).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2].sustituida_por).toBe('r-old');
  });

  it('searches the server for the same proveedor, excluding the row itself', async () => {
    const input = await editRefNew();

    fireEvent.change(input, { target: { value: 'ALT' } });

    await waitFor(() => expect(mockBuscarSustitutas).toHaveBeenCalledWith({ proveedorId: 'p1', q: 'ALT', excludeId: 'r-new' }));
    const option = await screen.findByRole('option', { name: /REF-ALT/ });
    expect(option.getAttribute('style')).toMatch(/color/);
  });

  it('saves the id of the chosen sustituta', async () => {
    const input = await editRefNew();
    fireEvent.change(input, { target: { value: 'ALT' } });
    fireEvent.click(await screen.findByRole('option', { name: /REF-ALT/ }));

    expect(input).toHaveValue('REF-ALT');
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2].sustituida_por).toBe('r-alt');
  });

  it('clearing the text removes the sustituta', async () => {
    const input = await editRefNew();
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2].sustituida_por).toBeNull();
  });

  it('typed text that was never chosen from the list is not sent as a sustituta', async () => {
    const input = await editRefNew();
    fireEvent.change(input, { target: { value: 'ALT' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2].sustituida_por).toBeNull();
  });

  it('clears the sustituta when the proveedor changes', async () => {
    const input = await editRefNew();

    fireEvent.change(screen.getByLabelText(/Código del proveedor/, { selector: 'select' }), { target: { value: 'p2' } });

    expect(input).toHaveValue('');
  });

  it('is disabled until a proveedor is chosen', async () => {
    await renderTab();

    expect(screen.getByRole('combobox', { name: /Código de referencia sustituta/ })).toBeDisabled();
  });
});
