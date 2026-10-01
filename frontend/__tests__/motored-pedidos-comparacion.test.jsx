/**
 * Motored Fase 4 (F5b): the "Comparar" tab of a scenario corrida (SC-06..SC-13,
 * UX-31). Real | prueba | delta per tienda and reference, the delta with its
 * sign and an arrow (never colour alone), the real corrida to compare with
 * (the latest calculated one of the same corte by default), "solo con
 * diferencias", the tienda filter, totals per tienda and the tiendas that
 * cannot be compared. A scenario has no pedido controls (SC-05).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, pagina, setSession, D_DETALLE, D_ESCENARIO, COMPARACION, REALES,
  C_PRUEBA, C_ANULADA, C_FALLIDA,
} from './helpers/pedidosFetch';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useParams: () => ({ id: 'c5' }),
  usePathname: () => '/motored/pedidos/c5',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';
import { claseTexto, pedidoRealTexto, sumarTotales } from '../components/motored/pedidos/comparacion';

const rutas = (over = {}) => ({
  'GET /corridas/c5': jsonRes(D_ESCENARIO),
  'GET /corridas': jsonRes(pagina([...REALES, C_ANULADA, C_PRUEBA, C_FALLIDA])),
  'GET /corridas/c5/comparar': jsonRes(COMPARACION),
  ...over,
});

const comparaciones = (calls) => calls.filter((c) => c.path === '/corridas/c5/comparar');
const ultima = (calls) => comparaciones(calls).slice(-1)[0];

async function abrirComparar() {
  fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
  return screen.findByRole('table', { name: 'Comparación con la corrida real' });
}

const filaDe = (tabla, codigo, tienda) => within(tabla).getAllByText(codigo)
  .map((el) => el.closest('tr')).find((tr) => within(tr).queryByText(tienda));

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('ADMIN');
});

describe('the Comparar tab belongs to scenarios', () => {
  it('shows it on a scenario and not on a real corrida', async () => {
    installFetch(rutas());
    const { unmount } = render(<CorridaDetallePage />);
    expect(await screen.findByRole('tab', { name: 'Comparar' })).toBeInTheDocument();
    unmount();
    installFetch(rutas({ 'GET /corridas/c5': jsonRes(D_DETALLE) }));
    render(<CorridaDetallePage />);
    await screen.findByRole('tab', { name: 'Tiendas' });
    expect(screen.queryByRole('tab', { name: 'Comparar' })).not.toBeInTheDocument();
  });

  it('reads nothing of the comparison until the tab is opened', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await screen.findByRole('tab', { name: 'Comparar' });
    expect(comparaciones(calls)).toHaveLength(0);
    expect(calls.some((c) => c.path === '/corridas' && c.query.get('escenario') === 'false')).toBe(false);
  });

  it('marks the scenario with PRUEBA and gives its pedidos no controls (SC-05, SC-06)', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await screen.findByRole('table', { name: 'Tiendas del pedido' });
    expect(screen.getAllByText('PRUEBA').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Cerrar|Reabrir|Exportar|Marcar como enviado|Corregir número|Recalcular|Aplicar recorte/ })).not.toBeInTheDocument();
  });
});

describe('the Tiendas tab of a scenario', () => {
  it('flags only the tiendas whose calculation failed: a scenario tienda has no pedido but it is not a failure', async () => {
    const fallida = { ...D_ESCENARIO.sucursales[0], sucursal_id: 's4', nombre: 'Armenia', estado: 'FALLIDA', codigo: 'E-CORRIDA-020', mensaje: 'Sin precios.' };
    installFetch(rutas({ 'GET /corridas/c5': jsonRes({ ...D_ESCENARIO, sucursales: [...D_ESCENARIO.sucursales, fallida] }) }));
    render(<CorridaDetallePage />);
    const tabla = await screen.findByRole('table', { name: 'Tiendas del pedido' });
    const fondo = (nombre) => within(tabla).getByText(nombre).closest('tr').style.background;
    expect(fondo('Armenia')).toMatch(/danger/);
    expect(fondo('Manizales')).not.toMatch(/danger/);
  });
});

describe('the real corrida to compare with', () => {
  it('looks for real, calculated corridas of the same corte and proveedor', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const busqueda = calls.find((c) => c.path === '/corridas');
    expect(busqueda.query.get('escenario')).toBe('false');
    expect(busqueda.query.get('desde')).toBe('2026-10-01');
    expect(busqueda.query.get('hasta')).toBe('2026-10-01');
    expect(busqueda.query.get('proveedor_id')).toBe('p1');
  });

  it('offers only calculated real corridas (no scenario, annulled or failed one) and picks the latest', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const selector = screen.getByLabelText('Comparar con');
    const opciones = within(selector).getAllByRole('option');
    expect(opciones.map((o) => o.value)).toEqual(['c1', 'c10']);
    expect(opciones[0].textContent).toMatch(/PED-2026-S40-001/);
    expect(selector).toHaveValue('c1');
    expect(ultima(calls).query.get('con')).toBe('c1');
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
  });

  it('compares again, from the first page, when another real corrida is picked', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    fireEvent.change(screen.getByLabelText('Comparar con'), { target: { value: 'c10' } });
    await waitFor(() => expect(ultima(calls).query.get('con')).toBe('c10'));
    expect(ultima(calls).query.get('offset')).toBe('0');
  });

  it('never shows the rows of the previous pair while the new one loads', async () => {
    installFetch(rutas({
      'GET /corridas/c5/comparar': (url) => (url.searchParams.get('con') === 'c10' ? new Promise(() => {}) : jsonRes(COMPARACION)),
    }));
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    expect(within(tabla).getAllByText('94109-12000S').length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('Comparar con'), { target: { value: 'c10' } });
    expect(await screen.findByText('Cargando comparación...')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Comparación con la corrida real' })).not.toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Totales por tienda' })).not.toBeInTheDocument();
  });

  it('says there is nothing to compare with, and asks nothing, when no real corrida has that corte', async () => {
    const calls = installFetch(rutas({ 'GET /corridas': jsonRes(pagina([C_ANULADA, C_PRUEBA])) }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
    expect(await screen.findByText(/No hay una corrida real calculada con la fecha de corte 01\/10\/2026/)).toBeInTheDocument();
    expect(comparaciones(calls)).toHaveLength(0);
  });

  it('shows the error with its code when the real corridas cannot be read', async () => {
    installFetch(rutas({ 'GET /corridas': coded(500, 'E-CORRIDA-099', 'Error interno.') }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Error interno. (E-CORRIDA-099)');
  });
});

describe('the comparison table', () => {
  it('shows the scenario next to the real corrida, with the PRUEBA badge and what was tested', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const cabecera = screen.getByRole('region', { name: 'Escenario frente a la corrida real' });
    expect(within(cabecera).getByText('ESC-2026-S40-001')).toBeInTheDocument();
    expect(within(cabecera).getByText('PRUEBA')).toBeInTheDocument();
    expect(within(cabecera).getByText(/Sumar las ventas de la referencia sustituida: Sí/)).toBeInTheDocument();
    expect(within(cabecera).getByText(/Factores de cobertura por rotación: F 4 · M 2 · S 1/)).toBeInTheDocument();
  });

  it('shows real, prueba and the delta of each tienda and reference', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    const filtro = filaDe(tabla, '94109-12000S', 'Manizales');
    const celdas = within(filtro).getAllByRole('cell').map((c) => c.textContent);
    expect(celdas[0]).toBe('Manizales');
    expect(celdas[1]).toMatch(/94109-12000S.*Filtro de aceite/);
    expect(celdas[3]).toBe('48');
    expect(celdas[4]).toBe('60');
    expect(celdas[5]).toBe('+12');
    expect(within(filaDe(tabla, '55512-A', 'Manizales')).getByText('-10')).toBeInTheDocument();
  });

  it('counts a reference that only one side has as 0 on the other', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    const celdas = within(filaDe(tabla, '00123-AB', 'Manizales')).getAllByRole('cell').map((c) => c.textContent);
    expect(celdas[3]).toBe('0');
    expect(celdas[4]).toBe('12');
    expect(celdas[5]).toBe('+12');
  });

  it('writes the sign and an arrow, so the direction never depends on colour (UX-31)', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    const sube = within(filaDe(tabla, '94109-12000S', 'Manizales')).getByText('+12').closest('[data-direccion]');
    const baja = within(filaDe(tabla, '55512-A', 'Manizales')).getByText('-10').closest('[data-direccion]');
    expect(sube).toHaveAttribute('data-direccion', 'sube');
    expect(baja).toHaveAttribute('data-direccion', 'baja');
    expect(sube.querySelector('svg')).not.toBeNull();
    expect(baja.querySelector('svg')).not.toBeNull();
    expect(sube.querySelector('svg')).not.toBe(baja.querySelector('svg'));
    expect(sube).toHaveAttribute('title', 'Sube 12 unidades frente a la corrida real');
    expect(baja).toHaveAttribute('title', 'Baja 10 unidades frente a la corrida real');
  });

  it('marks a row without change as such when identical rows are shown', async () => {
    const igual = { ...COMPARACION.filas[2], sucursal_id: 's2', sucursal: 'Pereira', referencia_id: 'x', codigo: '11111-Z', sugerido_prueba: '48.00', delta: '0.00' };
    installFetch(rutas({ 'GET /corridas/c5/comparar': jsonRes({ ...COMPARACION, filas: [igual], total: 1 }) }));
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    const delta = within(filaDe(tabla, '11111-Z', 'Pereira')).getByText('0').closest('[data-direccion]');
    expect(delta).toHaveAttribute('data-direccion', 'igual');
    expect(delta).toHaveAttribute('title', 'Sin cambio frente a la corrida real');
  });

  it('shows the class of each side only when it changes, and the real pedido only when Compras adjusted it', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    expect(within(filaDe(tabla, '00123-AB', 'Manizales')).getByText('DS → BM')).toBeInTheDocument();
    const bujia = filaDe(tabla, '55512-A', 'Manizales');
    expect(within(bujia).getByText('CM')).toBeInTheDocument();
    expect(within(bujia).getByText('Pedido real: 60')).toBeInTheDocument();
    expect(within(filaDe(tabla, '94109-12000S', 'Manizales')).queryByText(/Pedido real/)).not.toBeInTheDocument();
  });

  it('explains Real, Prueba and Cambio in plain Spanish', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    const tabla = await abrirComparar();
    const notas = within(tabla).getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(notas.some((t) => /corrida real/.test(t))).toBe(true);
    expect(notas.some((t) => /escenario/.test(t))).toBe(true);
    expect(notas.some((t) => /prueba menos real|Prueba menos Real/i.test(t))).toBe(true);
  });
});

describe('totals and tiendas that cannot be compared (SC-09, SC-13)', () => {
  it('shows the totals of each tienda on both sides, with the signed difference', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const totales = screen.getByRole('table', { name: 'Totales por tienda' });
    const manizales = within(totales.querySelector('tbody')).getByText('Manizales').closest('tr');
    const celdas = within(manizales).getAllByRole('cell').map((c) => c.textContent);
    expect(celdas[1]).toBe('1.000');
    expect(celdas[2]).toBe('1.014');
    expect(celdas[3]).toBe('+14');
    expect(celdas[6]).toMatch(/^\+\$\s?120\.000$/);
  });

  it('titles the two tables so the reader knows what each one is', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    expect(screen.getByRole('heading', { name: 'Detalle por tienda y referencia' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Totales por tienda' })).toBeInTheDocument();
  });

  it('sums the network in a strip', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const resumen = screen.getByRole('group', { name: 'Resumen de la red' });
    expect(resumen).toHaveTextContent('Toda la red');
    expect(resumen).toHaveTextContent('Real 1.800 unidades');
    expect(resumen).toHaveTextContent('Prueba 1.826 unidades');
    expect(resumen).toHaveTextContent('+26 unidades');
  });

  it('lists the tiendas that cannot be compared, with the reason', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const aviso = screen.getByRole('note', { name: /Tiendas que no se comparan/ });
    expect(within(aviso).getByText(/Cali: El escenario no calculó la tienda \(FALLIDA\)\./)).toBeInTheDocument();
  });

  it('shows no such list when every tienda can be compared', async () => {
    installFetch(rutas({ 'GET /corridas/c5/comparar': jsonRes({ ...COMPARACION, no_comparables: [] }) }));
    render(<CorridaDetallePage />);
    await abrirComparar();
    expect(screen.queryByRole('note', { name: /Tiendas que no se comparan/ })).not.toBeInTheDocument();
  });
});

describe('filters and paging', () => {
  it('starts with "Solo con diferencias" on and asks for the first 100 rows', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    expect(screen.getByRole('checkbox', { name: 'Solo con diferencias' })).toBeChecked();
    expect(ultima(calls).query.get('solo_diferencias')).toBe('true');
    expect(ultima(calls).query.get('limite')).toBe('100');
    expect(ultima(calls).query.get('offset')).toBe('0');
    expect(ultima(calls).query.has('sucursal_id')).toBe(false);
  });

  it('shows the identical rows too when the box is unticked', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Solo con diferencias' }));
    await waitFor(() => expect(ultima(calls).query.get('solo_diferencias')).toBe('false'));
  });

  it('filters by tienda with the tiendas of the totals and styled options', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    const selector = screen.getByLabelText('Tienda');
    const opciones = within(selector).getAllByRole('option');
    expect(opciones.map((o) => o.textContent)).toEqual(['Todas', 'Manizales', 'Pereira']);
    opciones.forEach((o) => expect(o.style.color).toBe('rgb(26, 26, 24)'));
    fireEvent.change(selector, { target: { value: 's2' } });
    await waitFor(() => expect(ultima(calls).query.get('sucursal_id')).toBe('s2'));
  });

  it('pages by 100 rows and goes back to page 1 when a filter changes', async () => {
    const calls = installFetch(rutas({ 'GET /corridas/c5/comparar': jsonRes({ ...COMPARACION, total: 250 }) }));
    render(<CorridaDetallePage />);
    await abrirComparar();
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument();
    expect(screen.getByText('250 filas')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultima(calls).query.get('offset')).toBe('100'));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Solo con diferencias' }));
    await waitFor(() => expect(ultima(calls).query.get('offset')).toBe('0'));
  });

  it('shows no pager when everything fits in one page', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirComparar();
    expect(screen.queryByRole('button', { name: 'Siguiente' })).not.toBeInTheDocument();
  });
});

describe('states', () => {
  it('says the scenario asks for the same as the real corrida when no row differs', async () => {
    installFetch(rutas({ 'GET /corridas/c5/comparar': jsonRes({ ...COMPARACION, filas: [], total: 0 }) }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
    expect(await screen.findByText('Sin diferencias: el escenario pide lo mismo que la corrida real.')).toBeInTheDocument();
  });

  it('says there is nothing to show when identical rows are shown and there are none', async () => {
    installFetch(rutas({ 'GET /corridas/c5/comparar': jsonRes({ ...COMPARACION, filas: [], total: 0 }) }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
    await screen.findByText(/Sin diferencias/);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Solo con diferencias' }));
    expect(await screen.findByText('Sin pedidos para mostrar')).toBeInTheDocument();
  });

  it('shows the invalid pairing error with its code', async () => {
    installFetch(rutas({
      'GET /corridas/c5/comparar': coded(422, 'E-CORRIDA-063', 'No se puede comparar: las corridas tienen otra fecha de corte.'),
    }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se puede comparar: las corridas tienen otra fecha de corte. (E-CORRIDA-063)');
  });

  it('shows a loading message while the comparison is on its way', async () => {
    installFetch(rutas({ 'GET /corridas/c5/comparar': () => new Promise(() => {}) }));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Comparar' }));
    expect(await screen.findByText('Cargando comparación...')).toBeInTheDocument();
  });
});

describe('comparison rules', () => {
  it('sums the totals of every tienda on both sides', () => {
    expect(sumarTotales(COMPARACION.totales_por_sucursal)).toEqual({
      unidadesReal: 1800, unidadesPrueba: 1826, diferenciaUnidades: 26,
      valorReal: 8200000, valorPrueba: 8410000, diferenciaValor: 210000,
    });
  });

  it('sums nothing when there is no tienda', () => {
    expect(sumarTotales([])).toEqual({
      unidadesReal: 0, unidadesPrueba: 0, diferenciaUnidades: 0, valorReal: 0, valorPrueba: 0, diferenciaValor: 0,
    });
  });

  it('writes the class once when it does not change and both when it does', () => {
    expect(claseTexto({ clase_real: 'CM', clase_prueba: 'CM' })).toBe('CM');
    expect(claseTexto({ clase_real: 'DS', clase_prueba: 'BM' })).toBe('DS → BM');
    expect(claseTexto({ clase_real: null, clase_prueba: 'BM' })).toBe('— → BM');
  });

  it('shows the real pedido only when Compras adjusted it', () => {
    expect(pedidoRealTexto({ sugerido_real: '50.00', pedido_final_real: '60.00' })).toBe('Pedido real: 60');
    expect(pedidoRealTexto({ sugerido_real: '50.00', pedido_final_real: '50.00' })).toBeNull();
    expect(pedidoRealTexto({ sugerido_real: '0.00', pedido_final_real: '12.00' })).toBe('Pedido real: 12');
  });
});
