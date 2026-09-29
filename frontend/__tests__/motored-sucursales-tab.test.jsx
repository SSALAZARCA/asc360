/**
 * `SucursalesTab` table and single-record form. The table shows the business
 * columns Nombre, Bodega principal, Departamento, Ciudad, Fecha apertura and
 * Estado. "SIC", "Días seguridad", "Días empaque" and "Días tránsito" are
 * hidden from the table (business decision) but stay as form fields.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListMaestros = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  createMaestro: jest.fn(),
  updateMaestro: jest.fn(),
  deactivateMaestro: jest.fn(),
  reactivateMaestro: jest.fn(),
}));

import SucursalesTab from '../components/motored/maestros/SucursalesTab';

const SUC = {
  id: 's1', nombre: 'NORTE', sic: 'SIC-77', dias_seguridad: '3.5', dias_empaque: 4, dias_transito: 6,
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
      'Nombre', 'Bodega principal', 'Departamento', 'Ciudad', 'Fecha apertura', 'Estado', '',
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
