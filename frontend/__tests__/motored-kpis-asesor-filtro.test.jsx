import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { installFetch, jsonRes, setSession } from './helpers/pedidosFetch';
import { OPCIONES, VENTAS } from './helpers/kpisVentasFixture';
import { TIENDAS } from './helpers/kpisTiendasFixture';
import { COMISIONES } from './helpers/kpisComisionesFixture';
import { ASESOR_DETALLE, OPCIONES_ASESORES } from './helpers/kpisAsesorDetalleFixture';

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

const K = '/tablero-asesores/kpis';
const BOGOTA = OPCIONES.tiendas[0].id;
const [PRIMERA, ...RESTO] = OPCIONES_ASESORES.asesores;
const OPCIONES_DE = (url) => jsonRes(
  // The list follows the store filter: with one chosen only the Bogotá asesora is left.
  url.searchParams.get('sucursales') ? { asesores: [PRIMERA] } : OPCIONES_ASESORES);
const RUTAS = (extra = {}) => ({
  [`GET ${K}/opciones`]: jsonRes(OPCIONES),
  [`GET ${K}/ventas`]: jsonRes(VENTAS),
  [`GET ${K}/tiendas`]: jsonRes(TIENDAS),
  [`GET ${K}/comisiones`]: jsonRes(COMISIONES),
  [`GET ${K}/asesores/opciones`]: OPCIONES_DE,
  [`GET ${K}/asesores/detalle`]: jsonRes(ASESOR_DETALLE),
  ...extra,
});
const llamadasA = (calls, ruta) => calls.filter((c) => c.path === `${K}/${ruta}`);
const PILDORA_PRIMERA = /Jiménez Rangel Yulisa · Bogotá 1 de Mayo/;

async function abrirAsesores(extra) {
  setSession('GERENCIA');
  const calls = installFetch(RUTAS(extra));
  render(<KpisPage />);
  fireEvent.click(await screen.findByRole('tab', { name: 'Asesores' }));
  return calls;
}

async function abrirConDetalle(extra) {
  const calls = await abrirAsesores(extra);
  expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
  return calls;
}

async function elegir(nombre, actual = PILDORA_PRIMERA) {
  fireEvent.click(screen.getByRole('button', { name: actual }));
  const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
  fireEvent.click(within(dialogo).getByRole('button', { name: new RegExp(nombre) }));
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('Asesor filter', () => {
  it('is only on the Asesores tab, names the asesor and has neither "Todos" nor a clear button', async () => {
    setSession('ADMIN');
    installFetch(RUTAS());
    render(<KpisPage />);
    await screen.findByRole('tab', { name: 'Ventas' });
    expect(screen.queryByRole('button', { name: PILDORA_PRIMERA })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Asesores' }));
    expect(await screen.findByRole('button', { name: PILDORA_PRIMERA })).toBeInTheDocument();
    expect(screen.queryByText(/Todos los asesores/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Quitar asesor/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Tiendas' }));
    expect(screen.queryByRole('button', { name: PILDORA_PRIMERA })).not.toBeInTheDocument();
  });

  it('loads the options with the active period, stores and HMCL, and lists "Nombre · Tienda" without a "Todos" entry', async () => {
    const calls = await abrirConDetalle();
    const consulta = llamadasA(calls, 'asesores/opciones')[0].query;
    expect(consulta.get('meses')).toBe('2026-01,2026-02,2026-03,2026-04,2026-05,2026-06,2026-07');
    expect(consulta.get('hmcl')).toBe('incluir');
    expect(consulta.has('sucursales')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: PILDORA_PRIMERA }));
    const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
    expect(within(dialogo).getByText('Gómez Muñoz Paula')).toBeInTheDocument();
    expect(within(dialogo).getByText('Popayán')).toBeInTheDocument();
    expect(within(dialogo).getByText(/12 asesores/)).toBeInTheDocument();
    expect(within(dialogo).queryByText(/Todos los asesores/)).not.toBeInTheDocument();
  });

  it('searches by name (ignoring accents and case) and by cédula', async () => {
    await abrirConDetalle();
    fireEvent.click(screen.getByRole('button', { name: PILDORA_PRIMERA }));
    const dialogo = screen.getByRole('dialog', { name: 'Elegir asesor' });
    const buscar = within(dialogo).getByRole('searchbox', { name: 'Buscar asesor' });
    fireEvent.change(buscar, { target: { value: 'rojas' } });
    expect(within(dialogo).getByText('Rojas Zapata Alejandra')).toBeInTheDocument();
    expect(within(dialogo).queryByText('Gómez Muñoz Paula')).not.toBeInTheDocument();
    fireEvent.change(buscar, { target: { value: 'a8' } });
    expect(within(dialogo).getByText('Gómez Muñoz Paula')).toBeInTheDocument();
    fireEvent.change(buscar, { target: { value: 'zzz' } });
    expect(within(dialogo).getByText('Ningún asesor coincide.')).toBeInTheDocument();
  });

  it('styles the list items explicitly so the text shows on the dark theme', async () => {
    await abrirConDetalle();
    fireEvent.click(screen.getByRole('button', { name: PILDORA_PRIMERA }));
    const item = within(screen.getByRole('dialog', { name: 'Elegir asesor' })).getByRole('button', { name: /Gómez Muñoz Paula/ });
    expect(item.style.color).not.toBe('');
    expect(item.style.background).not.toBe('');
  });
});

describe('Default selection', () => {
  it('opens on the asesor with the most sales, with the detail view and none of the old general blocks', async () => {
    const calls = await abrirConDetalle();
    expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(1);
    expect(llamadasA(calls, 'asesores/detalle')[0].query.get('cedula')).toBe('a1');
    expect(llamadasA(calls, 'asesores')).toHaveLength(0);
    expect(screen.queryByRole('region', { name: 'Asesores' })).not.toBeInTheDocument();
    expect(screen.queryByText('Elegí un asesor para ver su detalle')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Top 10 · venta' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Tecnired por asesor' })).not.toBeInTheDocument();
  });

  it('shows a Spanish message and fetches no detail when nobody sold with the chosen filters', async () => {
    const calls = await abrirAsesores({ [`GET ${K}/asesores/opciones`]: jsonRes({ asesores: [] }) });
    expect(await screen.findByText('No hay asesores con venta en los filtros elegidos.')).toBeInTheDocument();
    expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(0);
    expect(screen.queryByRole('region', { name: 'Detalle del asesor' })).not.toBeInTheDocument();
  });
});

describe('Selection', () => {
  it('picking one shows her detail with the same filters and the cédula, and the pill names her', async () => {
    const calls = await abrirConDetalle();
    await elegir('Gómez Muñoz Paula');
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2));
    expect(screen.queryByRole('dialog', { name: 'Elegir asesor' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Gómez Muñoz Paula · Popayán' })).toBeInTheDocument();
    const consulta = llamadasA(calls, 'asesores/detalle')[1].query;
    expect(consulta.get('cedula')).toBe('a8');
    expect(consulta.get('hmcl')).toBe('incluir');
    expect(consulta.get('meses')).toBe('2026-01,2026-02,2026-03,2026-04,2026-05,2026-06,2026-07');
  });

  it('keeps the asesor when the period changes, asking for the new options and the new months', async () => {
    const calls = await abrirConDetalle();
    await elegir('Gómez Muñoz Paula');
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: /Año corrido/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Último mes' }));
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(3));
    expect(llamadasA(calls, 'asesores/opciones')[1].query.get('meses')).toBe('2026-07');
    const consulta = llamadasA(calls, 'asesores/detalle')[2].query;
    expect(consulta.get('meses')).toBe('2026-07');
    expect(consulta.get('cedula')).toBe('a8');
    expect(screen.getByRole('button', { name: 'Gómez Muñoz Paula · Popayán' })).toBeInTheDocument();
  });

  it('falls back to the new default when the store filter leaves her out', async () => {
    const calls = await abrirConDetalle();
    await elegir('Gómez Muñoz Paula');
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2));
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox', { name: /Bogotá Av. Boyacá/ }));
    await waitFor(() => expect(llamadasA(calls, 'asesores/opciones')).toHaveLength(2));
    expect(llamadasA(calls, 'asesores/opciones')[1].query.get('sucursales')).toBe(BOGOTA);
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(3));
    expect(llamadasA(calls, 'asesores/detalle')[2].query.get('cedula')).toBe('a1');
    expect(screen.getByRole('button', { name: PILDORA_PRIMERA })).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
  });

  it('keeps her when the new store filter still includes her', async () => {
    const calls = await abrirConDetalle();
    await elegir('Jiménez Rangel Yulisa');
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox', { name: /Bogotá Av. Boyacá/ }));
    await waitFor(() => expect(llamadasA(calls, 'asesores/opciones')).toHaveLength(2));
    expect(await screen.findByRole('button', { name: PILDORA_PRIMERA })).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: 'Detalle del asesor' })).toBeInTheDocument();
    expect(llamadasA(calls, 'asesores/detalle').at(-1).query.get('cedula')).toBe('a1');
  });

  it('the default is the first of the list even when the list changes order', async () => {
    const reordenada = { asesores: [...RESTO, PRIMERA] };
    const calls = await abrirConDetalle({ [`GET ${K}/asesores/opciones`]: jsonRes(reordenada) });
    expect(llamadasA(calls, 'asesores/detalle')[0].query.get('cedula')).toBe('a2');
  });
});

describe('Detail states', () => {
  it('shows a Spanish message when the asesor is not found with the chosen filters', async () => {
    await abrirAsesores({ [`GET ${K}/asesores/detalle`]: jsonRes({ detail: 'Asesor no encontrado' }, 404) });
    expect(await screen.findByText('No encontramos a este asesor con los filtros elegidos.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: PILDORA_PRIMERA })).toBeInTheDocument();
  });

  it('shows the general error when the detail cannot be loaded', async () => {
    await abrirAsesores({ [`GET ${K}/asesores/detalle`]: jsonRes({ detail: 'x' }, 500) });
    expect(await screen.findByText(/No pudimos cargar los KPI's/)).toBeInTheDocument();
  });

  it('caches the detail per asesor and filters: going back to the same one does not fetch again', async () => {
    const calls = await abrirConDetalle();
    await elegir('Gómez Muñoz Paula');
    await waitFor(() => expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2));
    await elegir('Jiménez Rangel Yulisa', /Gómez Muñoz Paula · Popayán/);
    await screen.findByRole('button', { name: PILDORA_PRIMERA });
    expect(llamadasA(calls, 'asesores/detalle')).toHaveLength(2);
  });
});
