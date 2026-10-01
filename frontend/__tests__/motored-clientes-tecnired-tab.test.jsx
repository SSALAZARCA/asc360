/**
 * CLIENTES TECNIRED tab (feature motored-tablero-asesores, T2): read-only
 * list of the NITs currently loaded plus the bulk upload that REPLACES the
 * whole list. The upload modal gets its own columns and a replace warning.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListClientes = jest.fn();
const mockValidarCarga = jest.fn();
const mockSubirCarga = jest.fn();
const mockValidarCargaArchivo = jest.fn();
const mockSubirCargaArchivo = jest.fn();
const mockDescargarPlantilla = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listClientesTecnired: (...args) => mockListClientes(...args),
  validarCarga: (...args) => mockValidarCarga(...args),
  subirCarga: (...args) => mockSubirCarga(...args),
  validarCargaArchivo: (...args) => mockValidarCargaArchivo(...args),
  subirCargaArchivo: (...args) => mockSubirCargaArchivo(...args),
  descargarPlantilla: (...args) => mockDescargarPlantilla(...args),
  getSalud: () => Promise.resolve({ hallazgos: [] }),
  listMaestros: () => Promise.resolve([]),
}));

jest.mock('../app/motored/motored-layout', () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));

import MaestrosPage from '../app/motored/maestros/page';
import ClientesTecniredTab from '../components/motored/maestros/ClientesTecniredTab';
import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

const PAGINA = {
  items: [
    { id: 'c1', nit: '900123456', razon_social: 'ACME SAS' },
    { id: 'c2', nit: '800111222', razon_social: null },
  ],
  total: 120,
  page: 1,
  page_size: 50,
};

beforeEach(() => {
  mockListClientes.mockReset().mockResolvedValue(PAGINA);
  mockDescargarPlantilla.mockReset().mockResolvedValue(undefined);
});

async function renderTab() {
  render(<ClientesTecniredTab />);
  await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  return screen.getByRole('table');
}

describe('ClientesTecniredTab', () => {
  it('lists the NIT and razón social of the current list', async () => {
    const table = await renderTab();

    const headers = within(table).getAllByRole('columnheader').map((th) => th.textContent.trim());
    expect(headers).toEqual(['NIT', 'Razón social']);
    expect(within(table).getByText('900123456')).toBeInTheDocument();
    expect(within(table).getByText('ACME SAS')).toBeInTheDocument();
    expect(screen.getByText(/120 clientes/)).toBeInTheDocument();
  });

  it('warns that every upload replaces the whole list', async () => {
    await renderTab();

    expect(screen.getByText(/reemplaza la lista completa/i)).toBeInTheDocument();
  });

  it('searches by text and goes back to the first page', async () => {
    await renderTab();

    fireEvent.change(screen.getByLabelText(/Buscar/), { target: { value: '9001' } });
    fireEvent.submit(screen.getByRole('search'));

    await waitFor(() => expect(mockListClientes).toHaveBeenLastCalledWith({ page: 1, pageSize: 50, q: '9001' }));
  });

  it('pages forward with Siguiente', async () => {
    await renderTab();

    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));

    await waitFor(() => expect(mockListClientes).toHaveBeenLastCalledWith({ page: 2, pageSize: 50, q: '' }));
  });

  it('opens the upload modal for cliente_tecnired with its own columns', async () => {
    await renderTab();

    fireEvent.click(screen.getByRole('button', { name: /Cargar lista/ }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Clientes Tecnired/)).toBeInTheDocument();
    expect(within(dialog).getByText('NIT')).toBeInTheDocument();
    expect(within(dialog).getByText('Razón social')).toBeInTheDocument();
  });

  it('shows an error message when the list cannot be loaded', async () => {
    mockListClientes.mockReset().mockRejectedValue(new Error('Sin permiso'));
    render(<ClientesTecniredTab />);

    expect(await screen.findByText('Sin permiso')).toBeInTheDocument();
  });
});

describe('BulkUploadModal — cliente_tecnired', () => {
  it('lists NIT as required and Razón social as optional, with help text', () => {
    render(<BulkUploadModal entidad="cliente_tecnired" onClose={jest.fn()} onSuccess={jest.fn()} />);

    const items = screen.getAllByRole('listitem').map((li) => li.textContent);
    expect(items.some((t) => t.includes('NIT') && t.includes('(obligatoria)'))).toBe(true);
    expect(items.some((t) => t.includes('Razón social') && t.includes('(opcional)'))).toBe(true);
    expect(screen.getAllByRole('note').length).toBeGreaterThan(0);
  });

  it('uses a readable title and warns about the replacement', () => {
    render(<BulkUploadModal entidad="cliente_tecnired" onClose={jest.fn()} onSuccess={jest.fn()} />);

    expect(screen.getByRole('dialog', { name: /Clientes Tecnired/ })).toBeInTheDocument();
    expect(screen.queryByText(/cliente_tecnired/)).not.toBeInTheDocument();
    expect(screen.getByText(/reemplaza la lista completa/i)).toBeInTheDocument();
  });

  it('downloads the template for the exact entity', () => {
    render(<BulkUploadModal entidad="cliente_tecnired" onClose={jest.fn()} onSuccess={jest.fn()} />);

    fireEvent.click(screen.getByText(/Descargar plantilla/i));

    expect(mockDescargarPlantilla).toHaveBeenCalledWith('cliente_tecnired');
  });
});

describe('Maestros page — Clientes Tecnired tab', () => {
  it('is registered under the Maestros group', async () => {
    render(<MaestrosPage />);

    const tab = await screen.findByRole('button', { name: /Clientes Tecnired/ });
    const barra = tab.parentElement;
    const textos = Array.from(barra.children).map((el) => el.textContent.trim());
    const idxGrupoMaestros = textos.indexOf('Maestros');
    const idxGrupoMovimientos = textos.indexOf('Movimientos');
    const idxTab = textos.findIndex((t) => t.startsWith('Clientes Tecnired'));
    expect(idxTab).toBeGreaterThan(idxGrupoMaestros);
    expect(idxTab).toBeLessThan(idxGrupoMovimientos);
  });
});
