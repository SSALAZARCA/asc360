/**
 * Motored Fase 4 (sdd/motored-pedidos-ui, correction V1 of verify W2, spec
 * UX-06): the corridas list warns, on the row, when a corrida's input data
 * was older than its limit. The age comes from `antiguedad_peor` (the worst
 * dataset of the frozen evidence); the detail keeps the full per-dataset list.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { installFetch, jsonRes, pagina, setSession, C_CALCULADA, C_LIMPIA } from './helpers/pedidosFetch';
import { avisoAntiguedad } from '../components/motored/pedidos/reglas';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/motored/pedidos',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import PedidosPage from '../app/motored/pedidos/page';

const VIEJA = { dataset: 'facturas', antiguedad_dias: 9, limite_dias: 7, supera_limite: true };
const AL_DIA = { dataset: 'backorder', antiguedad_dias: 6, limite_dias: 7, supera_limite: false };

const C_VIEJA = { ...C_CALCULADA, id: 'c20', codigo: 'PED-2026-S40-020', antiguedad_peor: VIEJA };
const C_AL_DIA = { ...C_LIMPIA, id: 'c21', codigo: 'PED-2026-S40-021', antiguedad_peor: AL_DIA };
const C_SIN_DATO = { ...C_LIMPIA, id: 'c22', codigo: 'PED-2026-S40-022', antiguedad_peor: null };

const fila = async (codigo) => (await screen.findByText(codigo)).closest('tr');

describe('avisoAntiguedad (pure rule)', () => {
  it('words the warning with the dataset, its age and its limit', () => {
    expect(avisoAntiguedad({ antiguedad_peor: VIEJA })).toEqual({
      texto: 'Datos desactualizados',
      ayuda: 'Los datos de Facturas de pedidos tenían 9 días de antigüedad al calcular; el máximo permitido es 7.',
    });
  });

  it('uses the singular for one day', () => {
    const aviso = avisoAntiguedad({ antiguedad_peor: { dataset: 'inventario', antiguedad_dias: 1, limite_dias: 0, supera_limite: true } });
    expect(aviso.ayuda).toBe('Los datos de Inventario tenían 1 día de antigüedad al calcular; el máximo permitido es 0.');
  });

  it.each([
    [{ antiguedad_peor: AL_DIA }], [{ antiguedad_peor: null }], [{}],
  ])('gives no warning when the data is within its limit or unknown (%j)', (corrida) => {
    expect(avisoAntiguedad(corrida)).toBeNull();
  });
});

describe('Pedidos list - stale data (UX-06)', () => {
  beforeEach(() => {
    setSession();
    installFetch({ 'GET /corridas': jsonRes(pagina([C_VIEJA, C_AL_DIA, C_SIN_DATO])) });
  });

  it('warns on the row whose data is older than the limit', async () => {
    render(<PedidosPage />);
    expect(within(await fila('PED-2026-S40-020')).getByText('Datos desactualizados')).toBeInTheDocument();
  });

  it('explains the warning in a tooltip with the dataset and the numbers', async () => {
    render(<PedidosPage />);
    const row = await fila('PED-2026-S40-020');
    const notas = within(row).getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(notas).toContain('Los datos de Facturas de pedidos tenían 9 días de antigüedad al calcular; el máximo permitido es 7.');
  });

  it('shows no warning for fresh data or for a corrida without evidence', async () => {
    render(<PedidosPage />);
    expect(within(await fila('PED-2026-S40-021')).queryByText('Datos desactualizados')).not.toBeInTheDocument();
    expect(within(await fila('PED-2026-S40-022')).queryByText('Datos desactualizados')).not.toBeInTheDocument();
  });

  it('shows the warning once, beside the other row warnings', async () => {
    installFetch({ 'GET /corridas': jsonRes(pagina([{ ...C_VIEJA, invalidada: true }])) });
    render(<PedidosPage />);
    const row = await fila('PED-2026-S40-020');
    expect(within(row).getAllByText('Datos desactualizados')).toHaveLength(1);
    expect(within(row).getByText('Datos invalidados')).toBeInTheDocument();
  });
});
