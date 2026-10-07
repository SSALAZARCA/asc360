/**
 * Tests for `ResumenTab`'s "rows not loaded" notice: rows with errors are NOT
 * loaded (the valid rows are), and both the informe previo and the result
 * after Aplicar must say so explicitly, without opening the Errores tab.
 * The count is `log.filas_con_error` (rejected rows + rows whose sucursal or
 * referencia could not be resolved), falling back to `filas_rechazadas` for
 * cargas processed before that field existed.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const mockGetInforme = jest.fn();
const mockAplicar = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: (...args) => mockAplicar(...args),
  anularCarga: jest.fn(),
}));

import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

function informe(overrides = {}) {
  return {
    id: 'carga-1',
    estado: 'VALIDADO',
    filas_leidas: 100,
    filas_validas: 90,
    filas_rechazadas: 3,
    periodo_desde: null,
    periodo_hasta: null,
    log: {},
    variacion_pct_vs_carga_anterior: null,
    ...overrides,
  };
}

const AVISO = /Revisá el detalle en Errores o descargá errores\.csv/;

beforeEach(() => {
  mockGetInforme.mockReset();
  mockAplicar.mockReset();
  sessionStorage.clear();
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'CONSULTA' }));
});

describe('ResumenTab -- aviso de filas con errores que no se cargaron', () => {
  it('in the informe previo, states how many rows with errors were NOT loaded, using filas_con_error', async () => {
    mockGetInforme.mockResolvedValue(informe({ log: { filas_con_error: 5 } }));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    const aviso = await screen.findByRole('alert');
    expect(aviso.textContent).toBe(
      '5 filas con errores no se cargaron. Revisá el detalle en Errores o descargá errores.csv'
    );
  });

  it('falls back to filas_rechazadas when the log has no filas_con_error (older cargas)', async () => {
    mockGetInforme.mockResolvedValue(informe({ filas_rechazadas: 7, log: {} }));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    expect(await screen.findByText(/^7 filas con errores no se cargaron\./)).toBeInTheDocument();
  });

  it('uses the singular wording for exactly one row', async () => {
    mockGetInforme.mockResolvedValue(informe({ log: { filas_con_error: 1 } }));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    const aviso = await screen.findByRole('alert');
    expect(aviso.textContent).toBe(
      '1 fila con errores no se cargó. Revisá el detalle en Errores o descargá errores.csv'
    );
  });

  it('shows no notice when every row loaded', async () => {
    mockGetInforme.mockResolvedValue(informe({ filas_rechazadas: 0, log: { filas_con_error: 0 } }));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    await waitFor(() => expect(screen.getByText(/Filas leídas/)).toBeInTheDocument());
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument();
  });

  it('keeps showing the notice for an already APLICADO carga', async () => {
    mockGetInforme.mockResolvedValue(informe({ estado: 'APLICADO', log: { filas_con_error: 4 } }));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'APLICADO' }} />);

    expect(await screen.findByText(/^4 filas con errores no se cargaron\./)).toBeInTheDocument();
    expect(screen.getByText(AVISO)).toBeInTheDocument();
  });

  it('still shows the notice right after pressing Aplicar', async () => {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'ADMIN' }));
    mockGetInforme
      .mockResolvedValueOnce(informe({ log: { filas_con_error: 2 } }))
      .mockResolvedValue(informe({ estado: 'APLICADO', log: { filas_con_error: 2 } }));
    mockAplicar.mockResolvedValue({});
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    fireEvent.click(await screen.findByText('Aplicar'));

    await waitFor(() => expect(mockAplicar).toHaveBeenCalledWith('carga-1', { confirmarVaciado: false }));
    await waitFor(() => expect(mockGetInforme).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/^2 filas con errores no se cargaron\./)).toBeInTheDocument();
  });
});
