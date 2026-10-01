/**
 * Maestro de vendedores tab (feature motored-tablero-asesores, T3): list with
 * filters, manual create/edit (including linking an app Usuario), deactivate,
 * the Excel upload modal columns and the "Vendedores sin registrar" list that
 * prefills the create form.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListVendedores = jest.fn();
const mockCreateVendedor = jest.fn();
const mockUpdateVendedor = jest.fn();
const mockDeactivateVendedor = jest.fn();
const mockReactivateVendedor = jest.fn();
const mockListSinRegistrar = jest.fn();
const mockListUsuariosDisponibles = jest.fn();
const mockListMaestros = jest.fn();
const mockDescargarPlantilla = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listVendedores: (...args) => mockListVendedores(...args),
  createVendedor: (...args) => mockCreateVendedor(...args),
  updateVendedor: (...args) => mockUpdateVendedor(...args),
  deactivateVendedor: (...args) => mockDeactivateVendedor(...args),
  reactivateVendedor: (...args) => mockReactivateVendedor(...args),
  listVendedoresSinRegistrar: (...args) => mockListSinRegistrar(...args),
  listUsuariosDisponibles: (...args) => mockListUsuariosDisponibles(...args),
  listMaestros: (...args) => mockListMaestros(...args),
  validarCarga: jest.fn(),
  subirCarga: jest.fn(),
  validarCargaArchivo: jest.fn(),
  subirCargaArchivo: jest.fn(),
  descargarPlantilla: (...args) => mockDescargarPlantilla(...args),
  getSalud: () => Promise.resolve({ hallazgos: [] }),
  listClientesTecnired: () => Promise.resolve({ items: [], total: 0 }),
}));

jest.mock('../app/motored/motored-layout', () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));

import MaestrosPage from '../app/motored/maestros/page';
import VendedoresTab from '../components/motored/maestros/VendedoresTab';
import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

const ANA = {
  id: 'v1', nombre: 'Ana Pérez', nombre_norm: 'ANA PEREZ', cargo: 'ASESOR DE REPUESTOS',
  sucursal_id: 's1', sucursal_nombre: 'CALI NORTE', cedula: '1130', usuario_id: null,
  usuario_nombre: null, activo: true,
};
const LUIS = {
  id: 'v2', nombre: 'Luis Ríos', nombre_norm: 'LUIS RIOS', cargo: 'JEFE DE TALLER',
  sucursal_id: null, sucursal_nombre: null, cedula: null, usuario_id: 'u1',
  usuario_nombre: 'Luis Admin', activo: false,
};
const SIN_REGISTRAR = [
  { vendedor_norm: 'JUAN GOMEZ', vendedor_ejemplo: 'Juan Gómez', ultima_venta: '2026-09-30', lineas: 42 },
];

beforeEach(() => {
  mockListVendedores.mockReset().mockResolvedValue([ANA, LUIS]);
  mockCreateVendedor.mockReset().mockResolvedValue({});
  mockUpdateVendedor.mockReset().mockResolvedValue({});
  mockDeactivateVendedor.mockReset().mockResolvedValue({});
  mockReactivateVendedor.mockReset().mockResolvedValue({});
  mockListSinRegistrar.mockReset().mockResolvedValue(SIN_REGISTRAR);
  mockListUsuariosDisponibles.mockReset().mockResolvedValue([
    { id: 'u1', nombre: 'Luis Admin', role: 'COMPRAS' },
    { id: 'u2', nombre: 'Marta Mostrador', role: 'ASESOR_MOSTRADOR' },
  ]);
  mockListMaestros.mockReset().mockResolvedValue([{ id: 's1', nombre: 'CALI NORTE', activa: true }]);
  mockDescargarPlantilla.mockReset().mockResolvedValue(undefined);
  window.confirm = jest.fn(() => true);
});

async function renderTab() {
  render(<VendedoresTab />);
  await waitFor(() => expect(screen.getByRole('table', { name: /Vendedores$/ })).toBeInTheDocument());
}

const tablaVendedores = () => screen.getByRole('table', { name: /Vendedores$/ });

describe('VendedoresTab — list', () => {
  it('shows the people with cargo, sucursal, linked usuario and state', async () => {
    await renderTab();

    const headers = within(tablaVendedores()).getAllByRole('columnheader').map((th) => th.textContent.trim());
    expect(headers).toEqual(['Nombre vendedor', 'Cargo', 'Sucursal', 'Cédula', 'Usuario', 'Estado', '']);
    const filaAna = within(tablaVendedores()).getByText('Ana Pérez').closest('tr');
    expect(within(filaAna).getByText('ASESOR DE REPUESTOS')).toBeInTheDocument();
    expect(within(filaAna).getByText('CALI NORTE')).toBeInTheDocument();
    expect(within(filaAna).getByText('Activo')).toBeInTheDocument();
    const filaLuis = within(tablaVendedores()).getByText('Luis Ríos').closest('tr');
    expect(within(filaLuis).getByText('Luis Admin')).toBeInTheDocument();
    expect(within(filaLuis).getByText('Inactivo')).toBeInTheDocument();
  });

  it('filters by text, cargo and estado through the API', async () => {
    await renderTab();

    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'ana' } });
    fireEvent.change(screen.getByLabelText('Filtrar por cargo'), { target: { value: 'JEFE DE TALLER' } });
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'true' } });
    fireEvent.click(screen.getByRole('button', { name: 'Filtrar' }));

    await waitFor(() => expect(mockListVendedores).toHaveBeenLastCalledWith({ q: 'ana', cargo: 'JEFE DE TALLER', activo: 'true' }));
  });

  it('shows the load error', async () => {
    mockListVendedores.mockReset().mockRejectedValue(new Error('Sin permiso'));
    render(<VendedoresTab />);

    expect(await screen.findByText('Sin permiso')).toBeInTheDocument();
  });
});

describe('VendedoresTab — dark theme and help', () => {
  it('gives every <option> an explicit dark text color', async () => {
    await renderTab();

    const opciones = document.querySelectorAll('option');
    expect(opciones.length).toBeGreaterThan(8);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('explains that "Nombre vendedor" must match the ERP sales file', async () => {
    await renderTab();

    const ayudas = screen.getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(ayudas.some((t) => /ERP/.test(t) && /ventas/i.test(t))).toBe(true);
  });

  it('offers the suggested cargos while allowing free text', async () => {
    await renderTab();

    const campo = screen.getByLabelText(/^Cargo/, { selector: 'input' });
    expect(campo).toHaveAttribute('list');
    const lista = document.getElementById(campo.getAttribute('list'));
    const valores = Array.from(lista.querySelectorAll('option')).map((o) => o.value);
    expect(valores).toEqual([
      'ASESOR DE REPUESTOS', 'ASESOR DE REPUESTOS SUPERNUMERARIO',
      'ASESOR COMERCIAL DE SERVICIO POSVENTA', 'JEFE DE TALLER', 'CAJERO POSVENTA', 'OTRO',
    ]);
  });
});

describe('VendedoresTab — manual create and edit', () => {
  it('creates a vendedor with sucursal and no usuario', async () => {
    await renderTab();

    fireEvent.change(screen.getByLabelText(/^Nombre vendedor/, { selector: 'input' }), { target: { value: 'Pedro Soto' } });
    fireEvent.change(screen.getByLabelText(/^Cargo/, { selector: 'input' }), { target: { value: 'Otro' } });
    fireEvent.change(screen.getByLabelText(/^Sucursal/, { selector: 'select' }), { target: { value: 's1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear vendedor' }));

    await waitFor(() => expect(mockCreateVendedor).toHaveBeenCalledWith({
      nombre: 'Pedro Soto', cargo: 'Otro', sucursal_id: 's1', cedula: '', usuario_id: null,
    }));
    await waitFor(() => expect(mockListVendedores.mock.calls.length).toBeGreaterThan(1));
  });

  it('links an existing usuario when editing', async () => {
    await renderTab();
    const filaAna = within(tablaVendedores()).getByText('Ana Pérez').closest('tr');

    fireEvent.click(within(filaAna).getByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText(/^Usuario enlazado/, { selector: 'select' }), { target: { value: 'u2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateVendedor).toHaveBeenCalledWith('v1', expect.objectContaining({
      nombre: 'Ana Pérez', cargo: 'ASESOR DE REPUESTOS', sucursal_id: 's1', cedula: '1130', usuario_id: 'u2',
    })));
  });

  it('unlinks the usuario by sending null', async () => {
    await renderTab();
    const filaLuis = within(tablaVendedores()).getByText('Luis Ríos').closest('tr');

    fireEvent.click(within(filaLuis).getByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText(/^Usuario enlazado/, { selector: 'select' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateVendedor).toHaveBeenCalledWith('v2', expect.objectContaining({ usuario_id: null, sucursal_id: null })));
  });

  it('deactivates after confirming, never deleting', async () => {
    await renderTab();
    const filaAna = within(tablaVendedores()).getByText('Ana Pérez').closest('tr');

    fireEvent.click(within(filaAna).getByRole('button', { name: 'Desactivar' }));

    await waitFor(() => expect(mockDeactivateVendedor).toHaveBeenCalledWith('v1'));
  });

  it('reactivates an inactive vendedor', async () => {
    await renderTab();
    const filaLuis = within(tablaVendedores()).getByText('Luis Ríos').closest('tr');

    fireEvent.click(within(filaLuis).getByRole('button', { name: 'Reactivar' }));

    await waitFor(() => expect(mockReactivateVendedor).toHaveBeenCalledWith('v2'));
  });

  it('shows the API error when saving fails', async () => {
    mockCreateVendedor.mockRejectedValue(new Error('Ya existe un vendedor con ese nombre'));
    await renderTab();

    fireEvent.change(screen.getByLabelText(/^Nombre vendedor/, { selector: 'input' }), { target: { value: 'Ana Pérez' } });
    fireEvent.change(screen.getByLabelText(/^Cargo/, { selector: 'input' }), { target: { value: 'Otro' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear vendedor' }));

    expect(await screen.findByText('Ya existe un vendedor con ese nombre')).toBeInTheDocument();
  });
});

describe('VendedoresTab — vendedores sin registrar', () => {
  it('lists who sells but is not in the maestro', async () => {
    await renderTab();

    const tabla = await screen.findByRole('table', { name: /sin registrar/i });
    const fila = within(tabla).getByText('Juan Gómez').closest('tr');
    expect(within(fila).getByText('42')).toBeInTheDocument();
    expect(within(fila).getByText('2026-09-30')).toBeInTheDocument();
  });

  it('Agregar prefills the create form with the ERP name', async () => {
    await renderTab();
    const tabla = await screen.findByRole('table', { name: /sin registrar/i });

    fireEvent.click(within(tabla).getByRole('button', { name: /Agregar/ }));

    expect(screen.getByLabelText(/^Nombre vendedor/, { selector: 'input' })).toHaveValue('Juan Gómez');
    expect(screen.getByLabelText(/^Cargo/, { selector: 'input' })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Crear vendedor' })).toBeInTheDocument();
  });

  it('refreshes the unregistered list after creating the person', async () => {
    await renderTab();
    const tabla = await screen.findByRole('table', { name: /sin registrar/i });
    fireEvent.click(within(tabla).getByRole('button', { name: /Agregar/ }));
    fireEvent.change(screen.getByLabelText(/^Cargo/, { selector: 'input' }), { target: { value: 'Jefe de taller' } });
    mockListSinRegistrar.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Crear vendedor' }));

    await waitFor(() => expect(mockCreateVendedor).toHaveBeenCalledWith(expect.objectContaining({ nombre: 'Juan Gómez', cargo: 'Jefe de taller' })));
    await waitFor(() => expect(mockListSinRegistrar).toHaveBeenCalled());
  });

  it('says so when everyone is registered', async () => {
    mockListSinRegistrar.mockReset().mockResolvedValue([]);
    await renderTab();

    expect(await screen.findByText(/Todos los vendedores que aparecen en las ventas ya están registrados/)).toBeInTheDocument();
  });
});

describe('VendedoresTab — Excel upload', () => {
  it('opens the modal for vendedor', async () => {
    await renderTab();

    fireEvent.click(screen.getByRole('button', { name: /Carga masiva/ }));

    expect(await screen.findByRole('dialog', { name: /Vendedores/ })).toBeInTheDocument();
  });
});

describe('BulkUploadModal — vendedor', () => {
  it('lists the four columns with required flags and help', () => {
    render(<BulkUploadModal entidad="vendedor" onClose={jest.fn()} onSuccess={jest.fn()} />);

    const items = screen.getAllByRole('listitem').map((li) => li.textContent);
    const hay = (nombre, marca) => items.some((t) => t.includes(nombre) && t.includes(marca));
    expect(hay('Nombre vendedor', '(obligatoria)')).toBe(true);
    expect(hay('Cargo', '(obligatoria)')).toBe(true);
    expect(hay('Sucursal', '(opcional)')).toBe(true);
    expect(hay('Cédula', '(opcional)')).toBe(true);
    const ayudas = screen.getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(ayudas.some((t) => /ERP/.test(t))).toBe(true);
  });

  it('does not warn about replacing the list: uploading never deletes people', () => {
    render(<BulkUploadModal entidad="vendedor" onClose={jest.fn()} onSuccess={jest.fn()} />);

    expect(screen.queryByText(/reemplaza la lista completa/i)).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: /Vendedores/ })).toBeInTheDocument();
  });
});

describe('Maestros page — Vendedores tab', () => {
  it('is registered under the Maestros group', async () => {
    render(<MaestrosPage />);

    const tab = await screen.findByRole('button', { name: /^Vendedores/ });
    const textos = Array.from(tab.parentElement.children).map((el) => el.textContent.trim());
    const idxTab = textos.findIndex((t) => t.startsWith('Vendedores'));
    expect(idxTab).toBeGreaterThan(textos.indexOf('Maestros'));
    expect(idxTab).toBeLessThan(textos.indexOf('Movimientos'));
  });
});
