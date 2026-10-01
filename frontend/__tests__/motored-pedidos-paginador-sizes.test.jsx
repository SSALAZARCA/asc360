/** Motored Fase 4 (F2a): the Referencias paginator accepts its own page sizes. */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import ReferenciasPaginador from '../components/motored/maestros/ReferenciasPaginador';

const props = { page: 1, total: 300, onPageChange: () => {}, onPageSizeChange: () => {} };

describe('ReferenciasPaginador sizes', () => {
  it('offers the default sizes when no list is given', () => {
    render(<ReferenciasPaginador {...props} pageSize={50} />);
    const opciones = within(screen.getByRole('combobox')).getAllByRole('option').map((o) => o.textContent);
    expect(opciones).toEqual(['25', '50', '100', '200']);
  });

  it('offers the list given in sizes', () => {
    render(<ReferenciasPaginador {...props} pageSize={50} sizes={[50, 100, 200, 500]} />);
    const opciones = within(screen.getByRole('combobox')).getAllByRole('option').map((o) => o.textContent);
    expect(opciones).toEqual(['50', '100', '200', '500']);
  });

  it('lets the caller name the unit it counts', () => {
    render(<ReferenciasPaginador {...props} pageSize={50} unidad="líneas" />);
    expect(screen.getByText('300 líneas')).toBeInTheDocument();
  });

  it('names the paged unit in the navigation label', () => {
    render(<ReferenciasPaginador {...props} pageSize={50} unidad="líneas" />);
    expect(screen.getByRole('navigation', { name: 'Paginación de líneas' })).toBeInTheDocument();
  });

  it('keeps the referencias label by default', () => {
    render(<ReferenciasPaginador {...props} pageSize={50} />);
    expect(screen.getByRole('navigation', { name: 'Paginación de referencias' })).toBeInTheDocument();
  });
});
