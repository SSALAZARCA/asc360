/**
 * Tests for `VentasPerdidasFilters` (sdd/motored-ventas-perdidas-panel,
 * Phase 7, tasks 7.1/7.2). This is a pure controlled component (mirrors
 * `CargasHistoryTable.js`'s `Filtros` pattern) -- the 30-day default itself
 * is computed by the caller (`useVentasPerdidas`, tested separately); this
 * suite verifies the component renders whatever `filtros` it receives
 * (including the 30-day default values) and reports every field change up
 * via `setFiltros`, plus the "(inactiva)"/"(inactivo)" labelling for
 * deactivated sucursales/asesores (spec: deactivated entities stay
 * selectable, never hidden).
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import VentasPerdidasFilters from '../components/motored/ventas-perdidas/VentasPerdidasFilters';
import { calcularRangoUltimos30Dias } from '../components/motored/ventas-perdidas/fechaDefaults';

const SUCURSALES = [
  { id: 's1', nombre: 'Bogotá Norte', activa: true },
  { id: 's2', nombre: 'Cali Sur', activa: false },
];

const ASESORES = [
  { id: 'a1', nombre: 'Juan Asesor', activo: true },
  { id: 'a2', nombre: 'Marta Asesor', activo: false },
];

function baseFiltros(overrides = {}) {
  return { ...calcularRangoUltimos30Dias(), sucursalId: '', usuarioId: '', estado: '', ...overrides };
}

describe('VentasPerdidasFilters — 30-day default pre-fill on initial mount', () => {
  it('renders the desde/hasta inputs pre-filled with the 30-day default it receives on first render', () => {
    const filtros = baseFiltros();
    render(<VentasPerdidasFilters filtros={filtros} setFiltros={jest.fn()} sucursales={[]} asesores={[]} />);

    expect(screen.getByLabelText('Desde')).toHaveValue(filtros.desde);
    expect(screen.getByLabelText('Hasta')).toHaveValue(filtros.hasta);
  });
});

describe('VentasPerdidasFilters — applying filters', () => {
  it('reports a desde change via setFiltros, preserving the other fields', () => {
    const setFiltros = jest.fn();
    const filtros = baseFiltros();
    render(<VentasPerdidasFilters filtros={filtros} setFiltros={setFiltros} sucursales={SUCURSALES} asesores={ASESORES} />);

    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-01-01' } });

    expect(setFiltros).toHaveBeenCalledWith({ ...filtros, desde: '2026-01-01' });
  });

  it('reports a sucursal selection via setFiltros with the sucursal id', () => {
    const setFiltros = jest.fn();
    const filtros = baseFiltros();
    render(<VentasPerdidasFilters filtros={filtros} setFiltros={setFiltros} sucursales={SUCURSALES} asesores={ASESORES} />);

    fireEvent.change(screen.getByLabelText('Sucursal'), { target: { value: 's2' } });

    expect(setFiltros).toHaveBeenCalledWith({ ...filtros, sucursalId: 's2' });
  });

  it('reports an estado selection via setFiltros', () => {
    const setFiltros = jest.fn();
    const filtros = baseFiltros();
    render(<VentasPerdidasFilters filtros={filtros} setFiltros={setFiltros} sucursales={SUCURSALES} asesores={ASESORES} />);

    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'ANULADA' } });

    expect(setFiltros).toHaveBeenCalledWith({ ...filtros, estado: 'ANULADA' });
  });
});

describe('VentasPerdidasFilters — deactivated sucursal/asesor stay selectable', () => {
  it('labels an inactive sucursal option with "(inactiva)" but still renders it', () => {
    render(<VentasPerdidasFilters filtros={baseFiltros()} setFiltros={jest.fn()} sucursales={SUCURSALES} asesores={[]} />);

    expect(screen.getByRole('option', { name: 'Cali Sur (inactiva)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Bogotá Norte' })).toBeInTheDocument();
  });

  it('labels an inactive asesor option with "(inactivo)" but still renders it', () => {
    render(<VentasPerdidasFilters filtros={baseFiltros()} setFiltros={jest.fn()} sucursales={[]} asesores={ASESORES} />);

    expect(screen.getByRole('option', { name: 'Marta Asesor (inactivo)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Juan Asesor' })).toBeInTheDocument();
  });
});
