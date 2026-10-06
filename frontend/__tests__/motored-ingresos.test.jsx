/** "Registro de ingresos" (T10): ADMIN-only page, filters, table, pagination, sidebar entry. */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockList = jest.fn();
const pushMock = jest.fn();

jest.mock('../lib/motored/api', () => ({ listIngresos: (...a) => mockList(...a) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: pushMock }), usePathname: () => '/motored/ingresos' }));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div />;
  M.displayName = 'M';
  return M;
});

import IngresosPage from '../app/motored/ingresos/page';
import MotoredSidebar from '../components/motored/MotoredSidebar';

const CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const ITEMS = [
  { id: 'e1', fecha: '2026-09-30T20:15:00+00:00', email: 'ana@x.co', usuario_id: 'u1', usuario_nombre: 'Ana Salazar', resultado: 'EXITO', motivo: null, ip: '10.0.0.1', user_agent: CHROME },
  { id: 'e2', fecha: '2026-09-30T20:10:00+00:00', email: 'nadie@x.co', usuario_id: null, usuario_nombre: null, resultado: 'FALLO', motivo: 'CREDENCIALES', ip: '10.0.0.2', user_agent: 'curl/8.0' },
  { id: 'e3', fecha: '2026-09-30T20:05:00+00:00', email: 'ana@x.co', usuario_id: 'u1', usuario_nombre: 'Ana Salazar', resultado: 'BLOQUEADO', motivo: 'CUENTA_BLOQUEADA', ip: '10.0.0.1', user_agent: CHROME },
];
const lastQuery = () => mockList.mock.calls.at(-1)[0];

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem('motored_user', JSON.stringify({ id: 'a', role: 'ADMIN' }));
  sessionStorage.setItem('motored_token', 't');
  mockList.mockResolvedValue({ items: ITEMS, total: 120, page: 1, page_size: 50 });
});

describe('IngresosPage', () => {
  it('renders each attempt with Spanish result, motive, IP and short browser', async () => {
    render(<IngresosPage />);
    await waitFor(() => expect(screen.getAllByText('Ana Salazar').length).toBe(2));
    expect(mockList.mock.calls[0][0]).toMatchObject({ page: 1, page_size: 50, resultado: '' });
    const table = within(screen.getByRole('table'));
    expect(table.getByText('Éxito')).toBeInTheDocument();
    expect(table.getByText('Fallido')).toBeInTheDocument();
    expect(table.getByText('Bloqueado')).toBeInTheDocument();
    expect(screen.getByText('Contraseña o correo incorrectos')).toBeInTheDocument();
    expect(screen.getByText('Cuenta bloqueada')).toBeInTheDocument();
    expect(screen.getAllByText('Chrome').length).toBe(2);
    expect(screen.getByText('nadie@x.co')).toBeInTheDocument();
    expect(screen.getAllByText('10.0.0.1').length).toBe(2);
    expect(screen.getByText(/15:15/)).toBeInTheDocument(); // 20:15 UTC in Colombia
  });

  it('sends the filters as query params and resets to page 1', async () => {
    render(<IngresosPage />);
    await waitFor(() => expect(screen.getByText('nadie@x.co')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Resultado'), { target: { value: 'FALLO' } });
    await waitFor(() => expect(lastQuery().resultado).toBe('FALLO'));
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-09-01' } });
    await waitFor(() => expect(lastQuery().desde).toBe('2026-09-01'));
    fireEvent.change(screen.getByLabelText('Correo contiene'), { target: { value: 'ana' } });
    await waitFor(() => expect(lastQuery().texto).toBe('ana'));
    expect(lastQuery().page).toBe(1);
  });

  it('paginates', async () => {
    render(<IngresosPage />);
    await waitFor(() => expect(screen.getByText('Página 1 de 3')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(lastQuery().page).toBe(2));
  });

  it('styles every select option explicitly and explains the IP column', async () => {
    render(<IngresosPage />);
    await waitFor(() => expect(screen.getByText('nadie@x.co')).toBeInTheDocument());
    screen.getByLabelText('Resultado').querySelectorAll('option').forEach((o) => expect(o.style.color).not.toBe(''));
    expect(screen.getByRole('note', { name: /dirección desde donde/i })).toBeInTheDocument();
  });

  it('redirects non-ADMIN users away', () => {
    sessionStorage.setItem('motored_user', JSON.stringify({ id: 'b', role: 'COMPRAS' }));
    render(<IngresosPage />);
    expect(pushMock).toHaveBeenCalledWith('/motored/inicio');
    expect(mockList).not.toHaveBeenCalled();
  });
});

describe('sidebar entry', () => {
  const Real = jest.requireActual('../components/motored/MotoredSidebar').default;
  it('is shown to ADMIN inside the Configuración group and hidden from others', () => {
    // The Configuración group starts collapsed; open it to see its entries.
    const { unmount } = render(<Real user={{ nombre: 'U', role: 'ADMIN' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Configuración' }));
    const labels = screen.getAllByRole('button').map((b) => b.textContent);
    expect(labels[labels.indexOf('Gestión de usuarios') + 1]).toBe('Registro de ingresos');
    unmount();
    ['COMPRAS', 'CONSULTA', 'SUCURSAL', 'SERVICIO_CLIENTE'].forEach((role) => {
      const r = render(<Real user={{ nombre: 'U', role }} />);
      expect(screen.queryByText('Registro de ingresos')).toBeNull();
      r.unmount();
    });
  });
});
