/**
 * Motored Fase 4 (F3, verify G5, UX-36): annulling a carga. The confirmation
 * copy says that a carga used by a closed or sent pedido cannot be annulled,
 * and a 409 E-CARGA-050 shows the server message (it names the tienda and the
 * corrida) with its code instead of a generic error.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockGetInforme = jest.fn();
const mockAnular = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: jest.fn(),
  anularCarga: (...args) => mockAnular(...args),
}));

import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const INFORME = {
  id: 'carga-1', estado: 'APLICADA', filas_leidas: 100, filas_validas: 100, filas_rechazadas: 0,
  periodo_desde: null, periodo_hasta: null, log: {}, variacion_pct_vs_carga_anterior: null,
};
const MENSAJE_050 = 'La carga la usa el pedido cerrado de Manizales (corrida PED-2026-S40-001) y no se puede anular.';

function bloqueo409() {
  const error = new Error(MENSAJE_050);
  error.status = 409;
  error.code = 'E-CARGA-050';
  return error;
}

async function renderizar(role = 'COMPRAS') {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role }));
  render(<ResumenTab carga={{ id: 'carga-1', estado: 'APLICADA' }} />);
  return screen.findByRole('button', { name: 'Anular' });
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  mockGetInforme.mockResolvedValue(INFORME);
});
afterEach(() => jest.restoreAllMocks());

describe('anular una carga - texto de confirmación (G5)', () => {
  it('says that a carga used by a closed or sent pedido cannot be annulled', async () => {
    const confirmar = jest.spyOn(window, 'confirm').mockReturnValue(false);
    fireEvent.click(await renderizar());
    expect(confirmar).toHaveBeenCalledTimes(1);
    const texto = confirmar.mock.calls[0][0];
    expect(texto).toContain('Se borran las filas en proceso (staging)');
    expect(texto).toContain('pedido cerrado o enviado de alguna tienda');
    expect(texto).toContain('no permitirá anularla');
    expect(texto).not.toContain('queda registrada para revisión de corridas futuras');
    expect(mockAnular).not.toHaveBeenCalled();
  });

  it('annuls when the user confirms', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    mockAnular.mockResolvedValue({});
    fireEvent.click(await renderizar());
    await waitFor(() => expect(mockAnular).toHaveBeenCalledWith('carga-1'));
    expect(screen.queryByText(/E-CARGA-050/)).not.toBeInTheDocument();
  });
});

describe('anular una carga - 409 E-CARGA-050 (UX-36)', () => {
  it('shows the server message and the code', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    mockAnular.mockRejectedValue(bloqueo409());
    fireEvent.click(await renderizar());
    expect(await screen.findByText(`${MENSAJE_050} (E-CARGA-050)`)).toBeInTheDocument();
  });

  it('announces it as an alert and keeps the buttons usable', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    mockAnular.mockRejectedValue(bloqueo409());
    fireEvent.click(await renderizar());
    expect(await screen.findByRole('alert')).toHaveTextContent('Manizales');
    expect(screen.getByRole('button', { name: 'Anular' })).toBeEnabled();
  });

  it('keeps a plain failure readable when it carries no code', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    mockAnular.mockRejectedValue(new Error('La carga ya está anulada.'));
    fireEvent.click(await renderizar());
    expect(await screen.findByText('La carga ya está anulada.')).toBeInTheDocument();
  });

  it('falls back to the generic message when the error has no text', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    mockAnular.mockRejectedValue(new Error(''));
    fireEvent.click(await renderizar());
    expect(await screen.findByText('No se pudo anular la carga')).toBeInTheDocument();
  });
});
