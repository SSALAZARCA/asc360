/**
 * `SucursalesTab` table and single-record form. The table shows the business
 * columns Nombre, Bodega principal, Departamento, Ciudad, Fecha apertura and
 * Estado, plus the "Tienda principal" relation. "SIC", "Días seguridad", "Días empaque" and "Días tránsito" are
 * hidden from the table (business decision) but stay as form fields.
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
  reactivateMaestro: jest.fn(),
}));

import SucursalesTab from '../components/motored/maestros/SucursalesTab';

const SUC = {
  id: 's1', nombre: 'NORTE', codigo_co: 'E05', sic: 'SIC-77', dias_seguridad: '3.5', dias_empaque: 4, dias_transito: 6,
  bodega_principal: 'BE051', departamento: 'Antioquia', ciudad: 'Medellín',
  fecha_apertura: '2020-01-15', activa: true,
};

const HIDDEN_LABELS = ['SIC', 'Días seguridad', 'Días empaque', 'Días tránsito'];

async function renderTab() {
  mockListMaestros.mockResolvedValue([SUC]);
  render(<SucursalesTab />);
  await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  return screen.getByRole('table');
}

const headerLabels = (table) => within(table).getAllByRole('columnheader').map((th) => th.textContent.trim());

describe('SucursalesTab — table', () => {
  it('shows only the remaining business columns in order', async () => {
    const table = await renderTab();

    expect(headerLabels(table)).toEqual([
      'Nombre', 'Código C.O.', 'Tienda principal', 'Bodega principal', 'Departamento', 'Ciudad', 'Fecha apertura', 'Estado', '',
    ]);
  });

  it('hides the SIC and days columns (headers and cells)', async () => {
    const table = await renderTab();
    const labels = headerLabels(table);
    const cells = within(table).getAllByRole('row')[1].querySelectorAll('td');

    HIDDEN_LABELS.forEach((l) => expect(labels).not.toContain(l));
    const texts = Array.from(cells).map((td) => td.textContent);
    expect(texts).not.toContain('SIC-77');
    expect(texts).not.toContain('3.5');
    expect(texts).not.toContain('4');
    expect(texts).not.toContain('6');
    expect(texts).toContain('BE051');
  });
});

describe('SucursalesTab — form', () => {
  it('keeps the SIC and days fields in the form', async () => {
    await renderTab();

    HIDDEN_LABELS.forEach((l) => {
      expect(screen.getByLabelText(new RegExp(l), { selector: 'input' })).toBeInTheDocument();
    });
  });

  it('still loads the hidden values into the form when editing', async () => {
    await renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));

    expect(screen.getByLabelText(/SIC/, { selector: 'input' })).toHaveValue('SIC-77');
    expect(screen.getByLabelText(/Días seguridad/, { selector: 'input' })).toHaveValue('3.5');
  });
});

const base = { sic: 'S', dias_seguridad: '2.5', activa: true };
const LA33 = { ...base, id: 'p1', nombre: 'LA 33', principal_id: null };
const EXPO1 = { ...base, id: 'a1', nombre: 'EXPO 1', principal_id: 'p1' };
const EXPO2 = { ...base, id: 'a2', nombre: 'EXPO 2', principal_id: 'p1', activa: false };
const CERRADA = { ...base, id: 'p2', nombre: 'CERRADA', principal_id: null, activa: false };
const GRUPO = [LA33, EXPO1, EXPO2, CERRADA];

async function renderGrupo() {
  mockListMaestros.mockResolvedValue(GRUPO);
  render(<SucursalesTab />);
  await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  return screen.getByRole('table');
}

const principalSelect = () => screen.getByLabelText(/Tienda principal/, { selector: 'select' });
const optionTexts = () => within(principalSelect()).getAllByRole('option').map((o) => o.textContent);
const rowOf = (table, nombre) => within(table).getByText(nombre).closest('tr');

describe('SucursalesTab — associated stores', () => {
  beforeEach(() => {
    mockCreateMaestro.mockReset().mockResolvedValue({});
    mockUpdateMaestro.mockReset().mockResolvedValue({});
  });

  it('offers only principals, inactive ones labelled, with an empty option', async () => {
    await renderGrupo();

    expect(optionTexts()).toEqual([
      '— Ninguna (es tienda principal) —', 'LA 33', 'CERRADA (inactiva)',
    ]);
  });

  it('gives every option an explicit color for the dark theme', async () => {
    await renderGrupo();

    within(principalSelect()).getAllByRole('option').forEach((o) => {
      expect(o.style.color).not.toBe('');
    });
  });

  it('never offers the store being edited as its own principal', async () => {
    const table = await renderGrupo();
    fireEvent.click(within(rowOf(table, 'CERRADA')).getByRole('button', { name: 'Editar' }));

    expect(optionTexts()).toEqual(['— Ninguna (es tienda principal) —', 'LA 33']);
  });

  it('preselects the principal when editing an associated store', async () => {
    const table = await renderGrupo();
    fireEvent.click(within(rowOf(table, 'EXPO 2')).getByRole('button', { name: 'Editar' }));

    expect(principalSelect()).toHaveValue('p1');
  });

  it('disables the select on a store that already has associated stores', async () => {
    const table = await renderGrupo();
    fireEvent.click(within(rowOf(table, 'LA 33')).getByRole('button', { name: 'Editar' }));

    expect(principalSelect()).toBeDisabled();
  });

  it('sends principal_id on create and null for the empty option', async () => {
    await renderGrupo();
    fireEvent.change(screen.getByLabelText(/Nombre/, { selector: 'input' }), { target: { value: 'EXPO 3' } });
    fireEvent.change(screen.getByLabelText(/Código C\.O\./, { selector: 'input' }), { target: { value: 'E13' } });
    fireEvent.change(principalSelect(), { target: { value: 'p1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear sucursal' }));

    await waitFor(() => expect(mockCreateMaestro).toHaveBeenCalled());
    expect(mockCreateMaestro.mock.calls[0][1].principal_id).toBe('p1');
  });

  it('sends null to dissociate when editing', async () => {
    const table = await renderGrupo();
    fireEvent.click(within(rowOf(table, 'EXPO 1')).getByRole('button', { name: 'Editar' }));
    fireEvent.change(principalSelect(), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2].principal_id).toBeNull();
  });

  it('shows the relation in the table', async () => {
    const table = await renderGrupo();

    expect(rowOf(table, 'EXPO 1')).toHaveTextContent('Asociada a: LA 33');
    expect(rowOf(table, 'LA 33')).toHaveTextContent('Principal de 2 puntos');
    expect(rowOf(table, 'CERRADA')).not.toHaveTextContent('Asociada a');
  });
});

const CO_TOOLTIP = 'Código del centro de operación en el ERP (ej: E05). Cada C.O. es una tienda distinta.';
const coInput = () => screen.getByLabelText(/Código C\.O\./, { selector: 'input' });

describe('SucursalesTab — Código C.O.', () => {
  beforeEach(() => {
    mockCreateMaestro.mockReset().mockResolvedValue({});
    mockUpdateMaestro.mockReset().mockResolvedValue({});
  });

  it('shows the code in the table, next to the name', async () => {
    mockListMaestros.mockResolvedValue([SUC, { ...SUC, id: 's2', nombre: 'SUR', codigo_co: null }]);
    render(<SucursalesTab />);
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    const table = screen.getByRole('table');

    const celdas = (nombre) => Array.from(rowOf(table, nombre).querySelectorAll('td')).map((td) => td.textContent);
    expect(celdas('NORTE').slice(0, 2)).toEqual(['NORTE', 'E05']);
    expect(celdas('SUR').slice(0, 2)).toEqual(['SUR', '—']);
  });

  it('has a form input with its tooltip and the format rule', async () => {
    await renderTab();

    expect(coInput()).toBeInTheDocument();
    expect(screen.getByRole('note', { name: CO_TOOLTIP })).toBeInTheDocument();
    expect(coInput()).toHaveAttribute('maxLength', '3');
    expect(coInput()).toHaveAttribute('pattern', '[A-Za-z][0-9]{2}');
  });

  it('loads the stored code when editing', async () => {
    await renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));

    expect(coInput()).toHaveValue('E05');
  });

  it('sends the code trimmed and upper-cased on create', async () => {
    await renderTab();
    fireEvent.change(screen.getByLabelText(/Nombre/, { selector: 'input' }), { target: { value: 'SUR' } });
    fireEvent.change(coInput(), { target: { value: ' c06' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear sucursal' }));

    await waitFor(() => expect(mockCreateMaestro).toHaveBeenCalled());
    expect(mockCreateMaestro.mock.calls[0][1].codigo_co).toBe('C06');
  });

  it('refuses to clear a stored code on edit', async () => {
    await renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    fireEvent.change(coInput(), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    expect(await screen.findByText('El Código C.O. no se puede borrar: identifica a la sucursal.')).toBeInTheDocument();
    expect(mockUpdateMaestro).not.toHaveBeenCalled();
  });
});

describe('SucursalesTab — the C.O. identifies the store', () => {
  beforeEach(() => {
    mockCreateMaestro.mockReset().mockResolvedValue({});
    mockUpdateMaestro.mockReset().mockResolvedValue({});
  });

  const nombreInput = () => screen.getByLabelText(/Nombre/, { selector: 'input' });

  it('puts the code first in the form and marks it required', async () => {
    await renderTab();

    const inputs = Array.from(document.querySelectorAll('form input'));
    expect(inputs[0]).toBe(coInput());
    expect(coInput().closest('label')).toHaveTextContent('Código C.O. *');
    expect(coInput()).toBeRequired();
  });

  it('blocks a create without a code', async () => {
    await renderTab();
    fireEvent.change(nombreInput(), { target: { value: 'SUR' } });
    fireEvent.submit(nombreInput().closest('form'));

    expect(await screen.findByText('El Código C.O. es obligatorio: identifica a la sucursal.')).toBeInTheDocument();
    expect(mockCreateMaestro).not.toHaveBeenCalled();
  });

  it('pre-validates the format before saving', async () => {
    await renderTab();
    fireEvent.change(nombreInput(), { target: { value: 'SUR' } });
    fireEvent.change(coInput(), { target: { value: '5' } });
    fireEvent.submit(nombreInput().closest('form'));

    expect(await screen.findByText(/Código C\.O\. '5' no es válido/)).toBeInTheDocument();
    expect(mockCreateMaestro).not.toHaveBeenCalled();
  });

  it('still edits a legacy store that has no code yet', async () => {
    mockListMaestros.mockResolvedValue([{ ...SUC, codigo_co: null }]);
    render(<SucursalesTab />);
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));

    expect(coInput()).not.toBeRequired();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2].codigo_co).toBeNull();
  });

  it('renames a store freely, keeping its code', async () => {
    await renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    fireEvent.change(nombreInput(), { target: { value: 'NORTE NUEVO' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await waitFor(() => expect(mockUpdateMaestro).toHaveBeenCalled());
    expect(mockUpdateMaestro.mock.calls[0][2]).toMatchObject({ nombre: 'NORTE NUEVO', codigo_co: 'E05' });
  });

  it('clears the form error once a save goes through', async () => {
    await renderTab();
    fireEvent.change(nombreInput(), { target: { value: 'SUR' } });
    fireEvent.submit(nombreInput().closest('form'));
    await screen.findByText('El Código C.O. es obligatorio: identifica a la sucursal.');

    fireEvent.change(coInput(), { target: { value: 'c06' } });
    fireEvent.submit(nombreInput().closest('form'));

    await waitFor(() => expect(mockCreateMaestro).toHaveBeenCalled());
    expect(screen.queryByText('El Código C.O. es obligatorio: identifica a la sucursal.')).not.toBeInTheDocument();
  });
});
