import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { OPCIONES, VENTAS } from './helpers/kpisVentasFixture';
import { TIENDAS } from './helpers/kpisTiendasFixture';
import { ASESOR_DETALLE, OPCIONES_ASESORES } from './helpers/kpisAsesorDetalleFixture';
import { COMISIONES } from './helpers/kpisComisionesFixture';
import { INVENTARIO } from './helpers/kpisInventarioFixture';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/motored/tablero-asesores',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});
import KpisPage from '../app/motored/tablero-asesores/page';

const RUTAS = () => ({
  'GET /tablero-asesores/kpis/opciones': jsonRes(OPCIONES),
  'GET /tablero-asesores/kpis/ventas': jsonRes(VENTAS),
  'GET /tablero-asesores/kpis/tiendas': jsonRes(TIENDAS),
  'GET /tablero-asesores/kpis/comisiones': jsonRes(COMISIONES),
  'GET /tablero-asesores/kpis/inventario': jsonRes(INVENTARIO),
  'GET /tablero-asesores/kpis/asesores/opciones': jsonRes(OPCIONES_ASESORES),
  'GET /tablero-asesores/kpis/asesores/detalle': jsonRes(ASESOR_DETALLE),
});
const llamadasA = (calls, ruta) => calls.filter((c) => c.path === ruta);

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe("KPI's shell", () => {
  it('shows the header, the three tabs and loads Ventas for the year to date', async () => {
    setSession('GERENCIA');
    const calls = installFetch(RUTAS());
    render(<KpisPage />);
    expect(await screen.findByRole('heading', { name: "KPI's" })).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(tabs).toEqual(['Ventas', 'Tiendas', 'Asesores', 'Comisiones', 'Inventario']);
    expect(screen.getByRole('tab', { name: 'Ventas' })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(1));
    const consulta = llamadasA(calls, '/tablero-asesores/kpis/ventas')[0].query;
    expect(consulta.get('meses')).toBe('2026-01,2026-02,2026-03,2026-04,2026-05,2026-06,2026-07');
    expect(consulta.get('hmcl')).toBe('incluir');
    expect(consulta.has('sucursales')).toBe(false);
  });

  it('fetches again when a filter changes, with the new filters', async () => {
    setSession('ADMIN');
    const calls = installFetch(RUTAS());
    render(<KpisPage />);
    await screen.findByRole('tab', { name: 'Ventas' });
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: /Incluir HMCL/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('radio', { name: /Solo HMCL/ }));
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(2));
    expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')[1].query.get('hmcl')).toBe('solo');
  });

  it('loads Tiendas and Asesores with the same filters, each one once, and keeps Ventas cached', async () => {
    setSession('COMPRAS');
    const calls = installFetch(RUTAS());
    render(<KpisPage />);
    await screen.findByRole('tab', { name: 'Tiendas' });
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(1));
    fireEvent.click(screen.getByRole('tab', { name: 'Tiendas' }));
    expect(await screen.findByRole('region', { name: 'Tiendas' })).toBeInTheDocument();
    expect(llamadasA(calls, '/tablero-asesores/kpis/tiendas')).toHaveLength(1);
    expect(llamadasA(calls, '/tablero-asesores/kpis/tiendas')[0].query.get('hmcl')).toBe('incluir');
    fireEvent.click(screen.getByRole('tab', { name: 'Asesores' }));
    expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
    expect(llamadasA(calls, '/tablero-asesores/kpis/asesores/opciones')).toHaveLength(1);
    expect(llamadasA(calls, '/tablero-asesores/kpis/asesores/detalle')).toHaveLength(1);
    expect(llamadasA(calls, '/tablero-asesores/kpis/asesores')).toHaveLength(0);
    fireEvent.click(screen.getByRole('tab', { name: 'Ventas' }));
    expect(llamadasA(calls, '/tablero-asesores/kpis/ventas')).toHaveLength(1);
  });

  it('loads Inventario and a store click refetches it narrowed to that store', async () => {
    setSession('GERENCIA');
    const calls = installFetch(RUTAS());
    render(<KpisPage />);
    await screen.findByRole('tab', { name: 'Inventario' });
    fireEvent.click(screen.getByRole('tab', { name: 'Inventario' }));
    expect(await screen.findByRole('region', { name: 'Inventario' })).toBeInTheDocument();
    expect(llamadasA(calls, '/tablero-asesores/kpis/inventario')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Medellín La 33' }));
    await waitFor(() => expect(llamadasA(calls, '/tablero-asesores/kpis/inventario')).toHaveLength(2));
    expect(llamadasA(calls, '/tablero-asesores/kpis/inventario')[1].query.get('sucursales')).toBe('t2');
  });

  it('loads Comisiones with the same filters when its tab is opened', async () => {
    setSession('GERENCIA');
    const calls = installFetch(RUTAS());
    render(<KpisPage />);
    await screen.findByRole('tab', { name: 'Comisiones' });
    fireEvent.click(screen.getByRole('tab', { name: 'Comisiones' }));
    expect(await screen.findByText('Mes liquidado: julio 2026')).toBeInTheDocument();
    expect(llamadasA(calls, '/tablero-asesores/kpis/comisiones')).toHaveLength(1);
    expect(llamadasA(calls, '/tablero-asesores/kpis/comisiones')[0].query.get('hmcl')).toBe('incluir');
  });

  it('shows a Spanish error when the data cannot be loaded', async () => {
    setSession('ADMIN');
    installFetch({ ...RUTAS(), 'GET /tablero-asesores/kpis/ventas': jsonRes({ detail: 'x' }, 500) });
    render(<KpisPage />);
    expect(await screen.findByText(/No pudimos cargar los KPI's/)).toBeInTheDocument();
  });

  it('tells there are no sales yet when the network has none', async () => {
    setSession('ADMIN');
    installFetch({ ...RUTAS(), 'GET /tablero-asesores/kpis/opciones': jsonRes({ meses_disponibles: [], ultimo_mes: null, tiendas: [] }) });
    render(<KpisPage />);
    expect(await screen.findByText(/Todavía no hay ventas cargadas/)).toBeInTheDocument();
  });

  it('sends roles outside the gate back to Maestros without fetching', async () => {
    setSession('SUCURSAL');
    const calls = installFetch(RUTAS());
    render(<KpisPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/motored/mi-cuenta'));
    expect(calls).toHaveLength(0);
  });
});
