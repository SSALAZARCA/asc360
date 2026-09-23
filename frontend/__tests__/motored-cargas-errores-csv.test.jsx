/**
 * Tests for `ErroresTab` (sdd/motored-pedidos-ingesta, Phase 10, task
 * 10.3): the error grid's CSV download and RBAC-driven resolve actions.
 * Mirrors the existing Motored mocking convention (mock `lib/motored/api`,
 * import the component after the mock is registered).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockGetErrores = jest.fn();
const mockResolver = jest.fn();
const mockDescargarCsv = jest.fn();
const mockListMaestros = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getErroresCarga: (...args) => mockGetErrores(...args),
  resolverErroresCarga: (...args) => mockResolver(...args),
  descargarErroresCargaCsv: (...args) => mockDescargarCsv(...args),
  listMaestros: (...args) => mockListMaestros(...args),
}));

import ErroresTab from '../components/motored/cargas/ErroresTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const ERRORES = [
  { id: 'e1', fila: 3, columna: 'Sucursal', valor: 'MR BUCARAMANGA LA 27', codigo_error: 'SUCURSAL_NO_ENCONTRADA', mensaje: 'No se encontró la sucursal.' },
  { id: 'e2', fila: 9, columna: 'Referencia', valor: 'ABC-999', codigo_error: 'REFERENCIA_NO_ENCONTRADA', mensaje: 'No se encontró la referencia.' },
];

function setRole(role) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role }));
}

beforeEach(() => {
  mockGetErrores.mockReset().mockResolvedValue(ERRORES);
  mockResolver.mockReset().mockResolvedValue({ acciones_aplicadas: 1, acciones_ignoradas: 0 });
  mockDescargarCsv.mockReset().mockResolvedValue(undefined);
  mockListMaestros.mockReset().mockResolvedValue([{ id: 's1', nombre: 'BUCARAMANGA LA 27' }]);
  sessionStorage.clear();
});

describe('ErroresTab', () => {
  it('renders every error row returned by the API', async () => {
    setRole('ADMIN');
    render(<ErroresTab carga={{ id: 'carga-1' }} />);

    await waitFor(() => expect(screen.getAllByTestId('error-row')).toHaveLength(2));
    expect(screen.getByText('No se encontró la sucursal.')).toBeInTheDocument();
    expect(screen.getByText('No se encontró la referencia.')).toBeInTheDocument();
  });

  it('downloads the CSV for the exact carga id when the button is clicked', async () => {
    setRole('ADMIN');
    render(<ErroresTab carga={{ id: 'carga-1' }} />);

    await waitFor(() => expect(screen.getAllByTestId('error-row')).toHaveLength(2));
    fireEvent.click(screen.getByText('Descargar CSV'));

    await waitFor(() => expect(mockDescargarCsv).toHaveBeenCalledWith('carga-1'));
  });

  it('shows a CSV error message if the download fails, without crashing the grid', async () => {
    setRole('ADMIN');
    mockDescargarCsv.mockRejectedValue(new Error('HTTP 502'));
    render(<ErroresTab carga={{ id: 'carga-1' }} />);

    await waitFor(() => expect(screen.getAllByTestId('error-row')).toHaveLength(2));
    fireEvent.click(screen.getByText('Descargar CSV'));

    await waitFor(() => expect(screen.getByText('HTTP 502')).toBeInTheDocument());
    expect(screen.getAllByTestId('error-row')).toHaveLength(2);
  });

  it('hides resolve actions for a read-only role (CONSULTA)', async () => {
    setRole('CONSULTA');
    render(<ErroresTab carga={{ id: 'carga-1' }} />);

    await waitFor(() => expect(screen.getAllByTestId('error-row')).toHaveLength(2));
    expect(screen.queryByText('Mapear')).not.toBeInTheDocument();
    expect(screen.queryByText('Crear como OTROS')).not.toBeInTheDocument();
  });

  it('calls resolverErroresCarga with a mapear_sucursal action and reloads the grid', async () => {
    setRole('COMPRAS');
    render(<ErroresTab carga={{ id: 'carga-1' }} />);

    await waitFor(() => expect(screen.getAllByTestId('error-row')).toHaveLength(2));
    await waitFor(() => expect(mockListMaestros).toHaveBeenCalledWith('sucursales'));

    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 's1' } });
    fireEvent.click(screen.getByText('Mapear'));

    await waitFor(() => expect(mockResolver).toHaveBeenCalledWith('carga-1', [
      { codigo_error: 'SUCURSAL_NO_ENCONTRADA', valor: 'MR BUCARAMANGA LA 27', accion: 'mapear_sucursal', sucursal_id: 's1' },
    ]));
    expect(mockGetErrores).toHaveBeenCalledTimes(2);
  });
});
