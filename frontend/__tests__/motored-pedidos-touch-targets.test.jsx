/**
 * Motored Fase 4 (sdd/motored-pedidos-ui, correction V1 of verify W3, spec
 * UX-32): the controls measured under 40 px are raised to the 44 px tablet
 * touch target. The paginators get an opt-in `touch` prop so the other
 * screens that share them (Detractores, Ingresos, Referencias) keep their
 * size.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import DetractoresPagination from '../components/motored/detractores/DetractoresPagination';
import ReferenciasPaginador from '../components/motored/maestros/ReferenciasPaginador';
import LineasFiltros from '../components/motored/pedidos/LineasFiltros';
import CorridasFiltros from '../components/motored/pedidos/CorridasFiltros';

const TOUCH = '44px';

describe('DetractoresPagination touch target', () => {
  const props = { page: 2, pageSize: 50, total: 300, onChange: () => {} };

  it('raises Anterior and Siguiente to 44 px when asked', () => {
    render(<DetractoresPagination {...props} touch />);
    expect(screen.getByRole('button', { name: 'Anterior' }).style.minHeight).toBe(TOUCH);
    expect(screen.getByRole('button', { name: 'Siguiente' }).style.minHeight).toBe(TOUCH);
  });

  it('leaves the other screens at their size by default', () => {
    render(<DetractoresPagination {...props} />);
    expect(screen.getByRole('button', { name: 'Anterior' }).style.minHeight).toBe('');
    expect(screen.getByRole('button', { name: 'Siguiente' }).style.minHeight).toBe('');
  });
});

describe('ReferenciasPaginador touch target', () => {
  const props = { page: 2, pageSize: 50, total: 300, onPageChange: () => {}, onPageSizeChange: () => {} };

  it('raises both buttons and the page size select to 44 px when asked', () => {
    render(<ReferenciasPaginador {...props} touch />);
    expect(screen.getByRole('button', { name: 'Anterior' }).style.minHeight).toBe(TOUCH);
    expect(screen.getByRole('button', { name: 'Siguiente' }).style.minHeight).toBe(TOUCH);
    expect(screen.getByRole('combobox').style.minHeight).toBe(TOUCH);
  });

  it('leaves the Referencias tab at its size by default', () => {
    render(<ReferenciasPaginador {...props} />);
    expect(screen.getByRole('button', { name: 'Anterior' }).style.minHeight).toBe('');
    expect(screen.getByRole('combobox').style.minHeight).toBe('');
  });
});

describe('Corridas list filters', () => {
  it('are 44 px tall and keep every option readable', () => {
    render(<CorridasFiltros filters={{ estado: '', escenario: '', pedidos: '' }} setFilter={() => {}} />);
    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(3);
    selects.forEach((select) => {
      expect(select.style.minHeight).toBe(TOUCH);
      within(select).getAllByRole('option').forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
    });
  });
});

describe('Line table filters (found by the real-browser measurement)', () => {
  const filters = { clase: '', estado_quiebre: '', q: '', solo_editadas: false, incluir_excluidas: false };

  it('keep the class and quiebre selects and the search box at 44 px with readable options', () => {
    render(<LineasFiltros filters={filters} setFilter={() => {}} />);
    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(2);
    selects.forEach((select) => {
      expect(select.style.minHeight).toBe(TOUCH);
      within(select).getAllByRole('option').forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
    });
    expect(screen.getByRole('searchbox').style.minHeight).toBe(TOUCH);
  });
});
