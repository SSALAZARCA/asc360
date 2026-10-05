import React from 'react';
import { render, screen, within } from '@testing-library/react';
import SucursalesContadores from '../components/motored/maestros/SucursalesContadores';

const suc = (id, extra = {}) => ({ id, nombre: id, activa: true, principal_id: null, ...extra });

const valueOf = (label) => within(screen.getByText(label).closest('[data-contador]')).getByTestId('contador-valor').textContent;

describe('SucursalesContadores', () => {
  it('counts active sucursales and excludes inactive ones', () => {
    render(<SucursalesContadores sucursales={[suc('a'), suc('b'), suc('c', { activa: false })]} />);
    expect(valueOf('Sucursales activas')).toBe('2');
  });

  it('counts only active sucursales without principal_id as principal stores', () => {
    render(
      <SucursalesContadores
        sucursales={[
          suc('a'),
          suc('b', { principal_id: 'a' }),
          suc('c', { activa: false }),
          suc('d'),
        ]}
      />,
    );
    expect(valueOf('Sucursales activas')).toBe('3');
    expect(valueOf('Tiendas principales')).toBe('2');
  });

  it('shows the help tooltips', () => {
    render(<SucursalesContadores sucursales={[suc('a')]} />);
    expect(screen.getAllByRole('note', { name: 'Total de sucursales en estado Activa.' })).toHaveLength(1);
    expect(
      screen.getAllByRole('note', {
        name: 'Sucursales activas que tienen pedido propio; no cuenta las tiendas asociadas a otra.',
      }),
    ).toHaveLength(1);
  });

  it('updates when the list changes', () => {
    const { rerender } = render(<SucursalesContadores sucursales={[suc('a')]} />);
    expect(valueOf('Sucursales activas')).toBe('1');
    rerender(<SucursalesContadores sucursales={[suc('a'), suc('b')]} />);
    expect(valueOf('Sucursales activas')).toBe('2');
    rerender(<SucursalesContadores sucursales={[]} />);
    expect(valueOf('Tiendas principales')).toBe('0');
  });
});
