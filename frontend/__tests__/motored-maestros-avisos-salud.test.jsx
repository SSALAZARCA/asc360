/**
 * Maestros health dot: the active tab lists WHICH records carry a warning,
 * grouped by reason, so the user knows exactly what to fix.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

const mockGetSalud = jest.fn();
jest.mock('../lib/motored/api', () => ({
  getSalud: (...args) => mockGetSalud(...args),
}));

import MaestrosTabs from '../components/motored/maestros/MaestrosTabs';
import AvisosSalud from '../components/motored/maestros/AvisosSalud';

const TABS = [
  { id: 'ref', label: 'Referencias', entidadSalud: 'referencia', render: () => <p>contenido referencias</p> },
  { id: 'prov', label: 'Proveedores', entidadSalud: 'proveedor', render: () => <p>contenido proveedores</p> },
];

const HALLAZGOS = [
  { tipo: 'referencia_sin_precio', entidad: 'referencia', mensaje: "Referencia 'A-1' no tiene precio_normal", bloqueante: false },
  { tipo: 'referencia_sin_precio', entidad: 'referencia', mensaje: "Referencia 'B-2' no tiene precio_normal", bloqueante: false },
  { tipo: 'unidad_empaque_corregida', entidad: 'referencia', mensaje: "Referencia 'C-3' tenía unidad_empaque 0/nulo -- corregida a 1", bloqueante: false },
];

beforeEach(() => {
  mockGetSalud.mockReset().mockResolvedValue({ estado: 'advertencia', hallazgos: HALLAZGOS });
});

describe('MaestrosTabs health warnings', () => {
  it('shows a collapsed warning summary on the active tab', async () => {
    render(<MaestrosTabs tabs={TABS} />);
    const boton = await screen.findByRole('button', { name: /3 advertencias/ });
    expect(boton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('A-1')).toBeNull();
  });

  it('lists the codes grouped by reason when expanded', async () => {
    render(<MaestrosTabs tabs={TABS} />);
    fireEvent.click(await screen.findByRole('button', { name: /3 advertencias/ }));
    expect(screen.getByText(/Sin precio normal \(2\)/)).toBeInTheDocument();
    expect(screen.getByText('A-1')).toBeInTheDocument();
    expect(screen.getByText('B-2')).toBeInTheDocument();
    expect(screen.getByText(/Unidad de empaque corregida a 1 \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('C-3')).toBeInTheDocument();
  });

  it('shows nothing on a tab without warnings', async () => {
    render(<MaestrosTabs tabs={TABS} />);
    await screen.findByRole('button', { name: /3 advertencias/ });
    fireEvent.click(screen.getByRole('button', { name: /Proveedores/ }));
    expect(screen.queryByRole('button', { name: /advertencias/ })).toBeNull();
  });

  it('falls back to the raw message for an unknown reason', async () => {
    mockGetSalud.mockResolvedValue({ estado: 'advertencia', hallazgos: [
      { tipo: 'nuevo_chequeo', entidad: 'referencia', mensaje: 'Algo raro en X', bloqueante: false },
    ] });
    render(<MaestrosTabs tabs={TABS} />);
    fireEvent.click(await screen.findByRole('button', { name: /1 advertencia/ }));
    expect(screen.getByText('Algo raro en X')).toBeInTheDocument();
  });
});

describe('AvisosSalud — associated stores', () => {
  it('groups the associated-store warnings with a title and the store name', () => {
    render(<AvisosSalud hallazgos={[
      { tipo: 'asociada_principal_inactiva', entidad: 'sucursal', mensaje: "La sucursal 'EXPO 2' está asociada a 'LA 33', que está inactiva", bloqueante: false },
      { tipo: 'asociada_activa', entidad: 'sucursal', mensaje: "La sucursal 'EXPO 1' está activa pero asociada a 'LA 33'", bloqueante: false },
    ]} />);
    fireEvent.click(screen.getByRole('button', { name: /2 advertencias/ }));

    expect(screen.getByText(/Asociada a una tienda principal inactiva \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('EXPO 2')).toBeInTheDocument();
    expect(screen.getByText(/Tienda asociada activa \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('EXPO 1')).toBeInTheDocument();
  });
});

describe('AvisosSalud — stores without C.O.', () => {
  it('groups them under their own title with the store name', () => {
    render(<AvisosSalud hallazgos={[
      { tipo: 'sucursal_sin_codigo_co', entidad: 'sucursal', mensaje: "Sucursal 'CALI' no tiene Código C.O. asignado", bloqueante: false },
    ]} />);
    fireEvent.click(screen.getByRole('button', { name: /1 advertencia/ }));

    expect(screen.getByText(/Sin Código C\.O\. \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('CALI')).toBeInTheDocument();
  });
});
