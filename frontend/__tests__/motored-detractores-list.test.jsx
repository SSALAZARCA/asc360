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
  id: 'c1', numero: 12, codigo: 'DET-2026-000012', estado: 'ABIERTO', resultado: null,
  created_at: '2026-09-20T15:30:00', cerrado_at: null, asignado_a: null,
  cliente: { nombre: 'Ana Pérez', cedula: '1012345678', celular: '3001234567', placa: 'ABC12D', linea: 'Xpeed 125', centro_servicio: 'Taller Norte' },
  satisfaccion_general: 2, autoriza_datos: true, ultima_accion_at: '2026-09-21T10:00:00',
};
const ITEM_NO = {
  ...ITEM, id: 'c2', numero: 13, codigo: 'DET-2026-000013', autoriza_datos: false,
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
    expect(row).toHaveTextContent('DET-2026-000012');
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

  it('puts the action column first and keeps short tokens on one line', async () => {
    await renderPage();
    const row = (await screen.findByText('Ana Pérez')).closest('tr');
    expect(within(row.cells[0]).getByRole('button', { name: 'Tomar caso' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('Acción');
    expect(row.cells[1].style.whiteSpace).toBe('nowrap');
    expect(row.cells[4].style.whiteSpace).toBe('nowrap');
  });

  it('ABIERTO row offers only a primary Tomar caso button and is not clickable', async () => {
    await renderPage();
    const row = (await screen.findByText('Ana Pérez')).closest('tr');
    const tomar = within(row).getByRole('button', { name: 'Tomar caso' });
    expect(tomar).toHaveClass('motored-btn-primary');
    expect(within(row).queryByRole('button', { name: 'Ver caso' })).not.toBeInTheDocument();
    expect(row).not.toHaveAttribute('tabindex');
    fireEvent.click(row);
    expect(pushMock).not.toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('EN_GESTION and CERRADO rows offer a secondary Ver caso that opens the detail', async () => {
    const cerrado = { ...ITEM_NO, id: 'c3', codigo: 'DET-2026-000014', estado: 'CERRADO', cliente: { ...ITEM_NO.cliente, nombre: 'Eva Soto' } };
    mockFetch.mockResolvedValue(res(listBody({ items: [ITEM_NO, cerrado] })));
    await renderPage();
    const row = (await screen.findByText('Luis Gómez')).closest('tr');
    expect(within(row).queryByRole('button', { name: 'Tomar caso' })).not.toBeInTheDocument();
    const ver = within(row).getByRole('button', { name: 'Ver caso' });
    expect(ver).toHaveClass('motored-btn-secondary');
    fireEvent.click(ver);
    expect(pushMock).toHaveBeenCalledWith('/motored/detractores/c2');
    expect(within(screen.getByText('Eva Soto').closest('tr')).getByRole('button', { name: 'Ver caso' })).toBeInTheDocument();
  });

  it('Tomar caso posts to /tomar and opens the management page on success', async () => {
    mockFetch.mockImplementation(async (path, opts = {}) => (
      opts.method === 'POST' ? res({ id: 'c1', estado: 'EN_GESTION' }) : res(listBody())
    ));
    await renderPage();
    fireEvent.click(within((await screen.findByText('Ana Pérez')).closest('tr')).getByRole('button', { name: 'Tomar caso' }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/detractores/c1'));
    const post = mockFetch.mock.calls.find(([, o]) => o && o.method === 'POST');
    expect(post[0]).toBe('/detractores/c1/tomar');
  });

  it('on 409 shows the backend message on that row and refreshes the list', async () => {
    mockFetch.mockImplementation(async (path, opts = {}) => (
      opts.method === 'POST' ? res({ detail: 'Este caso ya lo tomó Carla Gomez.' }, 409) : res(listBody())
    ));
    await renderPage();
    const row = (await screen.findByText('Ana Pérez')).closest('tr');
    const before = mockFetch.mock.calls.length;
    fireEvent.click(within(row).getByRole('button', { name: 'Tomar caso' }));
    expect(await within(row).findByText('Este caso ya lo tomó Carla Gomez.')).toBeInTheDocument();
    await waitFor(() => expect(mockFetch.mock.calls.filter(([, o]) => !o).length).toBeGreaterThanOrEqual(2));
    expect(mockFetch.mock.calls.length).toBeGreaterThan(before + 1);
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('never shows customer comments in the list', async () => {
    mockFetch.mockResolvedValue(res(listBody({ items: [{ ...ITEM, observaciones: 'Texto privado del cliente' }] })));
    await renderPage();
    await screen.findByText('Ana Pérez');
    expect(screen.queryByText('Texto privado del cliente')).not.toBeInTheDocument();
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
