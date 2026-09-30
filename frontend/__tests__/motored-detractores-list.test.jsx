/**
 * Detractors panel (T8): list view — tabs, filters, table, gating.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockFetch = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/motoredFetch', () => ({
  ...jest.requireActual('../lib/motored/motoredFetch'),
  motoredFetch: (...a) => mockFetch(...a),
}));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/detractores',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import DetractoresPage from '../app/motored/detractores/page';

const res = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

const ITEM = {
  id: 'c1', numero: 12, estado: 'ABIERTO', resultado: null,
  created_at: '2026-09-20T15:30:00', cerrado_at: null, asignado_a: null,
  cliente: { nombre: 'Ana Pérez', cedula: '1012345678', celular: '3001234567', placa: 'ABC12D', linea: 'Xpeed 125', centro_servicio: 'Taller Norte' },
  satisfaccion_general: 2, autoriza_datos: true, ultima_accion_at: '2026-09-21T10:00:00',
};
const ITEM_NO = {
  ...ITEM, id: 'c2', numero: 13, autoriza_datos: false,
  cliente: { ...ITEM.cliente, nombre: 'Luis Gómez', cedula: '900', placa: 'XYZ98A' },
  asignado_a: { id: 'u1', nombre: 'Marta Ruiz' }, estado: 'EN_GESTION',
};

function listBody(over = {}) {
  return {
    items: [ITEM, ITEM_NO], total: 2, page: 1, page_size: 25,
    conteo_por_estado: { ABIERTO: 5, EN_GESTION: 3, CERRADO: 7 }, ...over,
  };
}

function lastQuery() {
  const path = mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0];
  return new URL(`http://x${path}`).searchParams;
}

async function renderPage(role = 'SERVICIO_CLIENTE') {
  sessionStorage.setItem('motored_user', JSON.stringify({ nombre: 'U', role }));
  sessionStorage.setItem('motored_token', 't');
  render(<DetractoresPage />);
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  mockFetch.mockResolvedValue(res(listBody()));
});

describe('Detractores list — gating', () => {
  it.each(['ADMIN', 'SERVICIO_CLIENTE'])('renders for %s', async (role) => {
    await renderPage(role);
    expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
  });

  it('redirects other roles away without fetching', async () => {
    await renderPage('CONSULTA');
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/maestros'));
    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.queryByText('Detractores')).not.toBeInTheDocument();
  });
});

describe('Detractores list — tabs', () => {
  it('shows the four tabs with counts and Abiertos selected by default', async () => {
    await renderPage();
    await screen.findByText('Ana Pérez');
    const tabs = screen.getByRole('tablist');
    expect(within(tabs).getByRole('tab', { name: /Abiertos/ })).toHaveTextContent('5');
    expect(within(tabs).getByRole('tab', { name: /En gestión/ })).toHaveTextContent('3');
    expect(within(tabs).getByRole('tab', { name: /Cerrados/ })).toHaveTextContent('7');
    expect(within(tabs).getByRole('tab', { name: /Todos/ })).toHaveTextContent('15');
    expect(within(tabs).getByRole('tab', { name: /Abiertos/ })).toHaveAttribute('aria-selected', 'true');
    expect(lastQuery().get('estado')).toBe('ABIERTO');
  });

  it('switches estado, and Todos sends no estado param', async () => {
    await renderPage();
    await screen.findByText('Ana Pérez');
    fireEvent.click(screen.getByRole('tab', { name: /En gestión/ }));
    await waitFor(() => expect(lastQuery().get('estado')).toBe('EN_GESTION'));
    fireEvent.click(screen.getByRole('tab', { name: /Todos/ }));
    await waitFor(() => expect(lastQuery().has('estado')).toBe(false));
  });
});

describe('Detractores list — filters', () => {
  it('sends q (debounced), centro, autoriza and date params', async () => {
    await renderPage();
    await screen.findByText('Ana Pérez');
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'ana' } });
    await waitFor(() => expect(lastQuery().get('q')).toBe('ana'));
    fireEvent.change(screen.getByLabelText('Centro de servicio'), { target: { value: 'Norte' } });
    await waitFor(() => expect(lastQuery().get('centro_servicio')).toBe('Norte'));
    fireEvent.change(screen.getByLabelText('Autorizó datos'), { target: { value: 'false' } });
    await waitFor(() => expect(lastQuery().get('autoriza_datos')).toBe('false'));
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-09-30' } });
    await waitFor(() => {
      expect(lastQuery().get('desde')).toBe('2026-09-01');
      expect(lastQuery().get('hasta')).toBe('2026-09-30');
    });
  });

  it('styles every select option explicitly', async () => {
    await renderPage();
    await screen.findByText('Ana Pérez');
    document.querySelectorAll('select option').forEach((o) => {
      expect(o.style.color).not.toBe('');
    });
  });

  it('paginates with page params', async () => {
    mockFetch.mockResolvedValue(res(listBody({ total: 60 })));
    await renderPage();
    await screen.findByText('Ana Pérez');
    expect(screen.getByText(/Página 1 de 3/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(lastQuery().get('page')).toBe('2'));
  });
});

describe('Detractores list — table', () => {
  it('renders the case row fields', async () => {
    await renderPage();
    const row = (await screen.findByText('Ana Pérez')).closest('tr');
    expect(row).toHaveTextContent('12');
    expect(row).toHaveTextContent('1012345678');
    expect(row).toHaveTextContent('ABC12D');
    expect(row).toHaveTextContent('Taller Norte');
    expect(row).toHaveTextContent('2/5');
    expect(row).toHaveTextContent('Abierto');
  });

  it('flags NO autorizó only on rows where autoriza_datos is false, and shows responsable', async () => {
    await renderPage();
    const rowNo = (await screen.findByText('Luis Gómez')).closest('tr');
    expect(within(rowNo).getByText('NO autorizó')).toBeInTheDocument();
    expect(rowNo).toHaveTextContent('Marta Ruiz');
    const rowYes = screen.getByText('Ana Pérez').closest('tr');
    expect(within(rowYes).queryByText('NO autorizó')).not.toBeInTheDocument();
    expect(within(rowYes).getByText('Sí')).toBeInTheDocument();
  });

  it('opens the detail on row click', async () => {
    await renderPage();
    fireEvent.click((await screen.findByText('Ana Pérez')).closest('tr'));
    expect(pushMock).toHaveBeenCalledWith('/motored/detractores/c1');
  });

  it('shows an empty state', async () => {
    mockFetch.mockResolvedValue(res(listBody({ items: [], total: 0 })));
    await renderPage();
    expect(await screen.findByText('No hay casos con estos filtros.')).toBeInTheDocument();
  });

  it('shows the backend error', async () => {
    mockFetch.mockResolvedValue(res({ detail: 'Sin permiso' }, 403));
    await renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Sin permiso');
  });
});
