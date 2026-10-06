/**
 * Tests for `VentasPerdidasContent` + `ventas-perdidas/page.js`
 * (sdd/motored-ventas-perdidas-panel, Phase 7, tasks 7.7/7.8; design D6).
 * Mirrors this project's established Motored mocking convention: mock
 * `lib/motored/api` and `lib/motored/useAdminGate`, import the page after
 * the mocks are registered (same pattern as `motored-usuarios-pending.test.jsx`).
 *
 * What's under test (composition-level, not re-testing Filters/Table units):
 * 1. ADMIN gate: a non-ADMIN sees nothing rendered from this page (the gate
 *    itself, `useAdminGate`, is unit-tested separately in Phase 5).
 * 2. Applying a filter re-fetches via listarBotLineas with the new params.
 * 3. An empty filtered list renders an explicit empty state.
 * 4. A listarBotLineas rejection renders an error state, not a crash.
 * 5. A successful anular shows the inconsistency banner when
 *    agregado_consistente=false.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockListarBotLineas = jest.fn();
const mockEditarBotLinea = jest.fn();
const mockAnularBotLinea = jest.fn();
const mockListMaestros = jest.fn();
const mockListUsuarios = jest.fn();

jest.mock('../lib/motored/api', () => ({
  listarBotLineas: (...args) => mockListarBotLineas(...args),
  editarBotLinea: (...args) => mockEditarBotLinea(...args),
  anularBotLinea: (...args) => mockAnularBotLinea(...args),
  listMaestros: (...args) => mockListMaestros(...args),
  listUsuarios: (...args) => mockListUsuarios(...args),
}));

jest.mock('../components/motored/MotoredSidebar', () => {
  const MockMotoredSidebar = () => <div data-testid="mock-motored-sidebar" />;
  MockMotoredSidebar.displayName = 'MockMotoredSidebar';
  return MockMotoredSidebar;
});

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/ventas-perdidas',
}));

import VentasPerdidasPage from '../app/motored/ventas-perdidas/page';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const LINEA = {
  linea_id: 'l1', carga_id: 'c1', fecha: '2026-09-01', cantidad: 3, estado: 'ACTIVA',
  metodo: 'manual', created_at: '2026-09-01T10:00:00Z',
  asesor: { id: 'a1', nombre: 'Juan Asesor', activo: true },
  sucursal: { id: 's1', nombre: 'Bogotá Norte', activa: true },
  referencia: { id: 'r1', codigo: 'X1', nombre: 'Filtro de aceite' },
  editado_por: null, editado_en: null, anulado_por: null, anulado_en: null,
};

function setSession(role) {
  sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ id: 'u1', nombre: 'Ana Admin', role }));
}

beforeEach(() => {
  mockListarBotLineas.mockReset().mockResolvedValue([LINEA]);
  mockEditarBotLinea.mockReset().mockResolvedValue({ ...LINEA, cantidad: 5 });
  mockAnularBotLinea.mockReset().mockResolvedValue({ ...LINEA, estado: 'ANULADA', agregado_consistente: true });
  mockListMaestros.mockReset().mockResolvedValue([{ id: 's1', nombre: 'Bogotá Norte', activa: true }]);
  mockListUsuarios.mockReset().mockResolvedValue([{ id: 'a1', nombre: 'Juan Asesor', role: 'ASESOR_MOSTRADOR', activo: true }]);
  pushMock.mockClear();
  sessionStorage.clear();
});

describe('VentasPerdidasPage — ADMIN gate', () => {
  it('redirects a non-ADMIN and renders nothing from this page', async () => {
    setSession('COMPRAS');
    render(<VentasPerdidasPage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/inicio'));
    expect(screen.queryByText('Ventas perdidas')).not.toBeInTheDocument();
    expect(mockListarBotLineas).not.toHaveBeenCalled();
  });
});

describe('VentasPerdidasPage — ADMIN can view and filter', () => {
  it('loads and renders the line list for an ADMIN', async () => {
    setSession('ADMIN');
    render(<VentasPerdidasPage />);

    await waitFor(() => expect(screen.getByText('X1 — Filtro de aceite')).toBeInTheDocument());
    expect(screen.getAllByText('Bogotá Norte').length).toBeGreaterThan(0);
  });

  it('re-fetches with the new filter value when the sucursal filter changes', async () => {
    setSession('ADMIN');
    render(<VentasPerdidasPage />);
    await waitFor(() => expect(mockListarBotLineas).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('Sucursal'), { target: { value: 's1' } });

    await waitFor(() => expect(mockListarBotLineas).toHaveBeenLastCalledWith(
      expect.objectContaining({ sucursalId: 's1' })
    ));
  });
});

describe('VentasPerdidasPage — empty and error states', () => {
  it('shows an explicit empty state when the filtered list is empty', async () => {
    setSession('ADMIN');
    mockListarBotLineas.mockResolvedValue([]);
    render(<VentasPerdidasPage />);

    await waitFor(() => expect(screen.getByText(/no hay líneas/i)).toBeInTheDocument());
  });

  it('shows an error state instead of crashing when listarBotLineas rejects', async () => {
    setSession('ADMIN');
    mockListarBotLineas.mockRejectedValue(new Error('Rango inválido'));
    render(<VentasPerdidasPage />);

    await waitFor(() => expect(screen.getByText('Rango inválido')).toBeInTheDocument());
  });
});

describe('VentasPerdidasPage — inconsistency banner', () => {
  it('shows a warning banner when an anular response has agregado_consistente=false', async () => {
    setSession('ADMIN');
    mockAnularBotLinea.mockResolvedValue({ ...LINEA, estado: 'ANULADA', agregado_consistente: false });
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    render(<VentasPerdidasPage />);

    await waitFor(() => expect(screen.getByText('X1 — Filtro de aceite')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Anular' }));

    await waitFor(() => expect(mockAnularBotLinea).toHaveBeenCalledWith('l1'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());

    window.confirm.mockRestore();
  });
});
