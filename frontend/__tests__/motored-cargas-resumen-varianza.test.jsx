/**
 * Tests for `ResumenTab`'s `VarianzaAviso` warning (sdd/motored-pedidos-ingesta,
 * verify-report WARNING #1): the ±40% volume-drop red flag vs. the prior
 * APLICADO load of the same tipo. Mirrors the existing Motored mocking
 * convention (mock `lib/motored/api`, import the component after the mock
 * is registered) -- see `motored-cargas-errores-csv.test.jsx`.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const mockGetInforme = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: jest.fn(),
  anularCarga: jest.fn(),
}));

import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

function setRole(role) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role }));
}

function informeCon(variacion) {
  return {
    id: 'carga-1',
    estado: 'VALIDADO',
    filas_leidas: 100,
    filas_validas: 90,
    filas_rechazadas: 10,
    periodo_desde: null,
    periodo_hasta: null,
    log: {},
    variacion_pct_vs_carga_anterior: variacion,
  };
}

beforeEach(() => {
  mockGetInforme.mockReset();
  sessionStorage.clear();
  setRole('CONSULTA');
});

describe('ResumenTab -- VarianzaAviso (±40% warning)', () => {
  it('shows no warning text when there is no prior APLICADO load of the same tipo (variación null)', async () => {
    mockGetInforme.mockResolvedValue(informeCon(null));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    await waitFor(() => expect(screen.getByText(/Filas leídas/)).toBeInTheDocument());
    expect(screen.queryByText(/Variación vs\. la carga anterior/)).not.toBeInTheDocument();
  });

  it('shows the variance line without the red-flag wording above the -40% threshold (-39%)', async () => {
    mockGetInforme.mockResolvedValue(informeCon(-39));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    const aviso = await screen.findByText(/Variación vs\. la carga anterior del mismo tipo: -39\.0%/);
    expect(aviso).toBeInTheDocument();
    expect(aviso.textContent).not.toMatch(/posible archivo incompleto/);
  });

  it('shows the red-flag wording exactly at the -40% threshold', async () => {
    mockGetInforme.mockResolvedValue(informeCon(-40));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    const aviso = await screen.findByText(/Variación vs\. la carga anterior del mismo tipo: -40\.0%/);
    expect(aviso.textContent).toMatch(/posible archivo incompleto/);
  });

  it('shows the red-flag wording below the -40% threshold (-55%)', async () => {
    mockGetInforme.mockResolvedValue(informeCon(-55));
    render(<ResumenTab carga={{ id: 'carga-1', estado: 'VALIDADO' }} />);

    const aviso = await screen.findByText(/Variación vs\. la carga anterior del mismo tipo: -55\.0%/);
    expect(aviso.textContent).toMatch(/posible archivo incompleto/);
  });
});
