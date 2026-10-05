/**
 * "Declarar sin datos" (odd/tasks/motored-cargas-sin-datos.md, T1): ADMIN
 * and COMPRAS can declare that HMCL has no backorder, facturas or ingresos
 * at a date. The declaration is listed with its own label instead of a
 * file name.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockListarCargas = jest.fn();
const mockDeclarar = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listarCargas: (...args) => mockListarCargas(...args),
  declararSinDatos: (...args) => mockDeclarar(...args),
  subirCargaMovimiento: jest.fn(),
  getCarga: jest.fn(),
  getCoberturaBot: jest.fn().mockResolvedValue([]),
  listMaestros: jest.fn().mockResolvedValue([]),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

import MovimientoTab from '../components/motored/cargas/MovimientoTab';
import CargasHistoryTable from '../components/motored/cargas/CargasHistoryTable';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

function setRole(role) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role }));
}

function hoyLocal() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

const DECLARADA = {
  id: 'd1', tipo: 'BACKORDER', nombre_archivo: 'Sin datos (declarado)',
  estado: 'APLICADO', periodo_desde: '2026-09-20', periodo_hasta: '2026-09-20',
  filas_leidas: 0, filas_validas: 0, filas_rechazadas: 0,
  created_at: '2026-09-20T15:00:00Z', sin_datos: true,
};

const SUBIDA = {
  ...DECLARADA, id: 'c1', nombre_archivo: 'backorder.xlsx', sin_datos: false,
  filas_leidas: 10, filas_validas: 9, filas_rechazadas: 1,
};

beforeEach(() => {
  mockListarCargas.mockReset().mockResolvedValue([]);
  mockDeclarar.mockReset();
  sessionStorage.clear();
});

describe('Declarar sin datos button', () => {
  it.each([
    ['BACKORDER', 'ADMIN'],
    ['FACTURAS_PEDIDOS', 'COMPRAS'],
    ['INGRESOS_FACTURAS', 'ADMIN'],
  ])('is shown on %s for %s', async (tipo, rol) => {
    setRole(rol);
    render(<MovimientoTab tipo={tipo} label="X" />);
    expect(await screen.findByRole('button', { name: 'Declarar sin datos' })).toBeInTheDocument();
  });

  it.each(['VENTAS', 'INVENTARIO', 'DEMANDA_PERDIDA'])('is never shown on %s', async (tipo) => {
    setRole('ADMIN');
    render(<MovimientoTab tipo={tipo} label="X" />);
    await screen.findByRole('button', { name: 'Subir archivo' });
    expect(screen.queryByRole('button', { name: 'Declarar sin datos' })).not.toBeInTheDocument();
  });

  it.each(['SUCURSAL', 'CONSULTA'])('is hidden for %s', async (rol) => {
    setRole(rol);
    render(<MovimientoTab tipo="BACKORDER" label="Backorder" />);
    await waitFor(() => expect(mockListarCargas).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Declarar sin datos' })).not.toBeInTheDocument();
  });
});

describe('Declarar sin datos dialog', () => {
  async function abrir(tipo = 'BACKORDER') {
    setRole('COMPRAS');
    render(<MovimientoTab tipo={tipo} label="X" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Declarar sin datos' }));
    return screen.getByRole('dialog');
  }

  it('defaults the date to today and explains the declaration', async () => {
    const dialogo = await abrir('BACKORDER');
    expect(within(dialogo).getByLabelText('Fecha')).toHaveValue(hoyLocal());
    expect(dialogo).toHaveTextContent(
      'Usalo solo si a esa fecha HMCL no tiene backorder pendientes. '
      + 'Queda registrado con tu usuario y se puede anular.'
    );
  });

  it.each([
    ['FACTURAS_PEDIDOS', 'facturas'],
    ['INGRESOS_FACTURAS', 'ingresos'],
  ])('names what is missing for %s', async (tipo, texto) => {
    const dialogo = await abrir(tipo);
    expect(dialogo).toHaveTextContent(`HMCL no tiene ${texto} pendientes.`);
  });

  it('sends tipo and fecha, closes, and reloads the list', async () => {
    mockDeclarar.mockResolvedValue(DECLARADA);
    const dialogo = await abrir('BACKORDER');
    await waitFor(() => expect(mockListarCargas).toHaveBeenCalledTimes(1));
    fireEvent.change(within(dialogo).getByLabelText('Fecha'), { target: { value: '2026-09-20' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Confirmar' }));

    await waitFor(() => expect(mockDeclarar).toHaveBeenCalledWith('BACKORDER', '2026-09-20'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(mockListarCargas).toHaveBeenCalledTimes(2));
  });

  it('shows the server error in Spanish and stays open', async () => {
    mockDeclarar.mockRejectedValue(new Error('Ya hay backorder cargado con fecha de corte 2026-09-20.'));
    const dialogo = await abrir('BACKORDER');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Confirmar' }));

    expect(await within(dialogo).findByText('Ya hay backorder cargado con fecha de corte 2026-09-20.'))
      .toBeInTheDocument();
    expect(mockListarCargas).toHaveBeenCalledTimes(1);
  });

  it('asks for a date before sending', async () => {
    const dialogo = await abrir('BACKORDER');
    fireEvent.change(within(dialogo).getByLabelText('Fecha'), { target: { value: '' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Confirmar' }));

    expect(await within(dialogo).findByText('Elegí una fecha.')).toBeInTheDocument();
    expect(mockDeclarar).not.toHaveBeenCalled();
  });

  it('closes on Cancelar without sending', async () => {
    const dialogo = await abrir('BACKORDER');
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mockDeclarar).not.toHaveBeenCalled();
  });
});

describe('Cargas list', () => {
  it('labels a declaration instead of showing a file name and row counts', async () => {
    mockListarCargas.mockResolvedValue([DECLARADA, SUBIDA]);
    render(<CargasHistoryTable refreshKey={0} tipoFijo="BACKORDER" />);

    const filas = await screen.findAllByRole('row');
    const declarada = filas[1];
    expect(within(declarada).getByText('Sin datos (declarado)')).toBeInTheDocument();
    expect(within(declarada).getByText('Sin filas')).toBeInTheDocument();
    expect(declarada).not.toHaveTextContent('0 / 0 / 0');
    expect(within(filas[2]).getByText('backorder.xlsx')).toBeInTheDocument();
    expect(filas[2]).toHaveTextContent('10 / 9 / 1');
  });
});
