/**
 * Tests for `CoberturaBotIndicator` (sdd/motored-ventas-perdidas-bot, Phase
 * 7, task 7.2/7.3; spec "Most-recent BOT-origin date is a non-blocking
 * visibility aid"). Sourced from `GET /demanda-perdida/cobertura-bot`
 * (backend/app/motored/api/demanda_perdida.py, shipped in Phase 6) --
 * `[{sucursal_id, ultima_fecha_bot}]`, per-sucursal, never a single global
 * date.
 *
 * What's under test:
 * 1. Renders a per-sucursal "última carga por bot" summary when bot data
 *    exists.
 * 2. Renders nothing when there is no bot data yet (empty array) -- no
 *    error, no empty-state banner, just absent.
 * 3. A fetch failure (backend down, 5xx, network error) also renders
 *    nothing -- fails silently, never an error banner (spec: this is
 *    strictly advisory, it must never get in the way of the Excel upload
 *    flow it sits next to).
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const mockGetCoberturaBot = jest.fn();
const mockListMaestros = jest.fn();

jest.mock('../lib/motored/api', () => ({
  getCoberturaBot: (...args) => mockGetCoberturaBot(...args),
  listMaestros: (...args) => mockListMaestros(...args),
}));

import CoberturaBotIndicator from '../components/motored/cargas/CoberturaBotIndicator';

beforeEach(() => {
  mockGetCoberturaBot.mockReset();
  mockListMaestros.mockReset().mockResolvedValue([
    { id: 'suc-1', nombre: 'Bogotá Norte' },
    { id: 'suc-2', nombre: 'Medellín Centro' },
  ]);
});

describe('CoberturaBotIndicator', () => {
  it('shows the most recent bot date and how many sucursales have bot data', async () => {
    mockGetCoberturaBot.mockResolvedValue([
      { sucursal_id: 'suc-1', ultima_fecha_bot: '2026-09-20' },
      { sucursal_id: 'suc-2', ultima_fecha_bot: '2026-09-24' },
    ]);

    render(<CoberturaBotIndicator />);

    await waitFor(() => expect(screen.getByText(/Medellín Centro/)).toBeInTheDocument());
    expect(screen.getByText(/2026-09-24/)).toBeInTheDocument();
    expect(screen.getByText(/2 sucursales/)).toBeInTheDocument();
  });

  it('renders nothing when there is no bot data yet', async () => {
    mockGetCoberturaBot.mockResolvedValue([]);

    const { container } = render(<CoberturaBotIndicator />);

    await waitFor(() => expect(mockGetCoberturaBot).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('fails silently (renders nothing, no error banner) when the fetch rejects', async () => {
    mockGetCoberturaBot.mockRejectedValue(new Error('boom'));

    const { container } = render(<CoberturaBotIndicator />);

    await waitFor(() => expect(mockGetCoberturaBot).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });
});
