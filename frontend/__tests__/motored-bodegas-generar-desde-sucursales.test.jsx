/**
 * Tests for the "Generar desde sucursales" bulk-create shortcut in
 * BodegasTab.js. Today the relationship is 1-to-1 (owner-confirmed, direct
 * request 2026-09-16): every sucursal already carries its own bodega's
 * code in `sucursal.bodega_principal` (spec §4.1's "código de la bodega
 * principal de esta sucursal"), so instead of retyping 47 rows by hand,
 * this button creates one bodega per sucursal using that exact field as
 * the new bodega's `codigo` and the sucursal's `nombre` as its
 * `descripcion`. Sucursales without a `bodega_principal`, or whose code
 * already matches an existing bodega, are skipped (not duplicated) --
 * safe to run more than once as more sucursales get their field filled in.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockListMaestros = jest.fn();
const mockCreateMaestro = jest.fn();
jest.mock('../lib/motored/api', () => ({
  listMaestros: (...args) => mockListMaestros(...args),
  createMaestro: (...args) => mockCreateMaestro(...args),
  updateMaestro: jest.fn(),
  deactivateMaestro: jest.fn(),
}));

import BodegasTab from '../components/motored/maestros/BodegasTab';

const SUCURSALES = [
  { id: 's1', nombre: 'CALI NORTE', bodega_principal: 'BA061' },
  { id: 's2', nombre: 'BOGOTA CENTRO', bodega_principal: 'BA062' },
  { id: 's3', nombre: 'SIN BODEGA CARGADA', bodega_principal: '' },
];

function setupListMaestros(bodegasExistentes) {
  mockListMaestros.mockImplementation((entidad) => {
    if (entidad === 'sucursales') return Promise.resolve(SUCURSALES);
    if (entidad === 'bodegas') return Promise.resolve(bodegasExistentes);
    return Promise.resolve([]);
  });
}

beforeEach(() => {
  mockListMaestros.mockReset();
  mockCreateMaestro.mockReset().mockResolvedValue({});
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('BodegasTab — generar desde sucursales', () => {
  it('crea una bodega por cada sucursal con "Bodega principal" cargado, salteando las que ya existen o no la tienen', async () => {
    setupListMaestros([{ id: 'b1', codigo: 'BA062', descripcion: 'ya existente' }]);

    render(<BodegasTab />);

    const boton = await screen.findByText('Generar desde sucursales');
    await waitFor(() => expect(boton).not.toBeDisabled());
    fireEvent.click(boton);

    await waitFor(() => expect(mockCreateMaestro).toHaveBeenCalledTimes(1));
    expect(mockCreateMaestro).toHaveBeenCalledWith('bodegas', {
      codigo: 'BA061',
      descripcion: 'CALI NORTE',
      sucursal_id: 's1',
    });

    await waitFor(() => expect(screen.getByText(/1 bodega\(s\) generada/)).toBeInTheDocument());
    expect(screen.getByText(/BOGOTA CENTRO: ya existe una bodega/)).toBeInTheDocument();
    expect(screen.getByText(/SIN BODEGA CARGADA: sin "Bodega principal"/)).toBeInTheDocument();
  });

  it('no crea nada si el usuario cancela la confirmación', async () => {
    window.confirm.mockReturnValue(false);
    setupListMaestros([]);

    render(<BodegasTab />);

    const boton = await screen.findByText('Generar desde sucursales');
    await waitFor(() => expect(boton).not.toBeDisabled());
    fireEvent.click(boton);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockCreateMaestro).not.toHaveBeenCalled();
  });

  it('no crea nada si ya existe una bodega con el código de cada sucursal', async () => {
    setupListMaestros([
      { id: 'b1', codigo: 'BA061', descripcion: 'x' },
      { id: 'b2', codigo: 'BA062', descripcion: 'x' },
    ]);

    render(<BodegasTab />);

    const boton = await screen.findByText('Generar desde sucursales');
    await waitFor(() => expect(boton).not.toBeDisabled());
    fireEvent.click(boton);

    await waitFor(() => expect(screen.getByText(/0 bodega\(s\) generada/)).toBeInTheDocument());
    expect(mockCreateMaestro).not.toHaveBeenCalled();
  });
});
