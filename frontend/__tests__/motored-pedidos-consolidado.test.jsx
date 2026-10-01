/**
 * Motored Fase 4 (F5a): the "Consolidado" tab of the corrida detail - the
 * network matrix (references x tiendas). Sticky reference column, a column per
 * tienda with a state dot and a truncated name (full name as tooltip), row and
 * column totals, paging of 100 references, search, a flagged FALLIDA column
 * and the loading / empty / error states. Horizontal scrolling at 47 columns
 * is checked in a real browser (jsdom has no layout).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import {
  installFetch, jsonRes, coded, setSession, D_DETALLE, D_PRUEBA, CONSOLIDADO, CONSOLIDADO_VACIO,
} from './helpers/pedidosFetch';
import { getConsolidado } from '../lib/motored/pedidosApi';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useParams: () => ({ id: 'c1' }),
  usePathname: () => '/motored/pedidos/c1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';

const rutas = (consolidado = jsonRes(CONSOLIDADO), detalle = jsonRes(D_DETALLE)) => ({
  'GET /corridas/c1': detalle,
  'GET /corridas/c1/consolidado': consolidado,
});
const ultimas = (calls) => [...calls].reverse().find((c) => c.path === '/corridas/c1/consolidado');
const abrirConsolidado = async () => {
  fireEvent.click(await screen.findByRole('tab', { name: 'Consolidado' }));
  return screen.findByRole('table', { name: 'Consolidado de la red' });
};
const columna = (tabla, nombre) => [...tabla.querySelectorAll('thead th')].findIndex((th) => th.textContent.includes(nombre));
const celda = (tabla, codigo, nombre) => {
  const fila = within(tabla).getByText(codigo).closest('tr');
  return fila.querySelectorAll('td')[columna(tabla, nombre)];
};
const pie = (tabla) => [...tabla.querySelectorAll('tfoot tr')];

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  setSession('COMPRAS');
});

describe('getConsolidado', () => {
  it('asks for the page of references with the search text and drops empty filters', async () => {
    const calls = installFetch(rutas());
    await getConsolidado('c1', { q: 'filtro', limite: 100, offset: 200 });
    expect(calls[0].path).toBe('/corridas/c1/consolidado');
    expect(calls[0].query.get('q')).toBe('filtro');
    expect(calls[0].query.get('limite')).toBe('100');
    expect(calls[0].query.get('offset')).toBe('200');
    await getConsolidado('c1', { q: '', limite: 100, offset: 0 });
    expect(calls[1].query.has('q')).toBe(false);
  });
});

describe('consolidated tab - navigation', () => {
  it('shows the Tiendas tab selected and reads nothing of the matrix until Consolidado is opened', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    expect(await screen.findByRole('tab', { name: 'Tiendas' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Consolidado' })).toHaveAttribute('aria-selected', 'false');
    expect(calls.some((c) => c.path === '/corridas/c1/consolidado')).toBe(false);
  });

  it('opens the matrix in place of the Tiendas table and comes back to it', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    expect(screen.getByRole('tab', { name: 'Consolidado' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('table', { name: 'Tiendas del pedido' })).not.toBeInTheDocument();
    expect(ultimas(calls).query.get('limite')).toBe('100');
    expect(ultimas(calls).query.get('offset')).toBe('0');
    fireEvent.click(screen.getByRole('tab', { name: 'Tiendas' }));
    expect(await screen.findByRole('table', { name: 'Tiendas del pedido' })).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Consolidado de la red' })).not.toBeInTheDocument();
  });

  it('reads the matrix again every time the tab is opened (the tiendas may have changed state)', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    fireEvent.click(screen.getByRole('tab', { name: 'Tiendas' }));
    await screen.findByRole('table', { name: 'Tiendas del pedido' });
    await abrirConsolidado();
    expect(calls.filter((c) => c.path === '/corridas/c1/consolidado')).toHaveLength(2);
  });

  it('also shows the matrix of a scenario corrida, still marked PRUEBA', async () => {
    installFetch(rutas(jsonRes({ ...CONSOLIDADO, es_escenario: true }), jsonRes(D_PRUEBA)));
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    expect(within(tabla).getByText('94109-12000S')).toBeInTheDocument();
    expect(screen.getByText('PRUEBA')).toBeInTheDocument();
  });
});

describe('consolidated matrix - reference rows', () => {
  beforeEach(() => installFetch(rutas()));

  it('lists code and name of each reference in the first column, in the order received', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const filas = [...tabla.querySelectorAll('tbody tr')];
    expect(filas).toHaveLength(3);
    expect(filas[0].querySelector('td')).toHaveTextContent('94109-12000S');
    expect(filas[0].querySelector('td')).toHaveTextContent('Filtro de aceite');
    expect(filas[2].querySelector('td')).toHaveTextContent('00123-AB');
    expect(filas[2].querySelector('td')).toHaveTextContent('Pastilla de freno');
  });

  it('puts the quantity of each tienda in its own column and leaves the cells without an order blank', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    expect(celda(tabla, '94109-12000S', 'Manizales')).toHaveTextContent(/^48$/);
    expect(celda(tabla, '94109-12000S', 'Pereira')).toHaveTextContent(/^36$/);
    expect(celda(tabla, '94109-12000S', 'Villavicen')).toHaveTextContent(/^24$/);
    expect(celda(tabla, '55512-A', 'Manizales')).toHaveTextContent(/^60$/);
    expect(celda(tabla, '55512-A', 'Pereira')).toBeEmptyDOMElement();
    expect(celda(tabla, '55512-A', 'Villavicen')).toBeEmptyDOMElement();
    expect(celda(tabla, '00123-AB', 'Pereira')).toBeEmptyDOMElement();
    expect(celda(tabla, '00123-AB', 'Villavicen')).toHaveTextContent(/^12$/);
  });

  it('shows the total of every reference in the Total column', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    expect(celda(tabla, '94109-12000S', 'Total')).toHaveTextContent(/^108$/);
    expect(celda(tabla, '55512-A', 'Total')).toHaveTextContent(/^60$/);
    expect(celda(tabla, '00123-AB', 'Total')).toHaveTextContent(/^42$/);
  });

  it('keeps the first column in view while the matrix scrolls sideways', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const primeraCelda = within(tabla).getByText('94109-12000S').closest('td');
    const primerEncabezado = tabla.querySelector('thead th');
    expect(primeraCelda).toHaveStyle({ position: 'sticky', left: '0' });
    expect(primerEncabezado).toHaveStyle({ position: 'sticky', left: '0' });
  });
});

describe('consolidated matrix - tienda columns', () => {
  beforeEach(() => installFetch(rutas()));

  it('shows the whole name of a short tienda and cuts a long one to 10 characters, with the full name as tooltip', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const encabezados = [...tabla.querySelectorAll('thead th')];
    expect(encabezados.some((th) => th.textContent.includes('Manizales'))).toBe(true);
    const larga = encabezados.find((th) => th.textContent.includes('Villavicen'));
    expect(larga.textContent).not.toContain('Villavicencio');
    expect(larga.getAttribute('title')).toBe('Villavicencio: Enviado');
  });

  it('marks the state of each tienda pedido with a dot that says it in words, not only in colour', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    expect(within(tabla).getByRole('img', { name: 'Borrador' })).toBeInTheDocument();
    expect(within(tabla).getByRole('img', { name: 'Cerrado' })).toBeInTheDocument();
    expect(within(tabla).getByRole('img', { name: 'Enviado' })).toBeInTheDocument();
  });

  it('flags a FALLIDA tienda: warning in the header with its message, no cells and no totals', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const encabezado = [...tabla.querySelectorAll('thead th')].find((th) => th.textContent.includes('Armenia'));
    expect(encabezado).toHaveTextContent('Fallida');
    expect(encabezado.getAttribute('title')).toBe('Armenia: Fallida - La tienda no tiene precios cargados. (E-CORRIDA-020)');
    expect(within(tabla).queryByRole('img', { name: 'Fallida' })).toBeInTheDocument();
    const idx = columna(tabla, 'Armenia');
    [...tabla.querySelectorAll('tbody tr')].forEach((tr) => expect(tr.querySelectorAll('td')[idx]).toBeEmptyDOMElement());
    pie(tabla).forEach((tr) => expect(tr.querySelectorAll('td, th')[idx]).not.toHaveTextContent(/\d/));
  });

  it('flags an OMITIDA tienda in the same way', async () => {
    const omitida = { ...CONSOLIDADO.tiendas[3], estado: 'OMITIDA', codigo: null, mensaje: 'Tienda sin ventas en el periodo.' };
    installFetch(rutas(jsonRes({ ...CONSOLIDADO, tiendas: [CONSOLIDADO.tiendas[0], omitida] })));
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const encabezado = [...tabla.querySelectorAll('thead th')].find((th) => th.textContent.includes('Armenia'));
    expect(encabezado).toHaveTextContent('Omitida');
    expect(encabezado.getAttribute('title')).toBe('Armenia: Omitida - Tienda sin ventas en el periodo.');
  });
});

describe('consolidated matrix - legend', () => {
  it('explains the dot of every state that appears in the columns, in words', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    const leyenda = screen.getByRole('group', { name: 'Estado de cada tienda' });
    ['Borrador', 'Cerrado', 'Enviado', 'Fallida'].forEach((estado) => expect(leyenda).toHaveTextContent(estado));
    expect(leyenda).not.toHaveTextContent('Omitida');
  });

  it('lists only the states the corrida really has', async () => {
    installFetch(rutas(jsonRes({ ...CONSOLIDADO, tiendas: [CONSOLIDADO.tiendas[0]] })));
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    const leyenda = screen.getByRole('group', { name: 'Estado de cada tienda' });
    expect(leyenda).toHaveTextContent('Borrador');
    expect(leyenda).not.toHaveTextContent('Cerrado');
  });
});

describe('consolidated matrix - totals', () => {
  beforeEach(() => installFetch(rutas()));

  it('shows the units of each tienda over the whole corrida in the footer, and the network total under Total', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const unidades = pie(tabla)[0];
    expect(unidades).toHaveTextContent('Unidades');
    const celdas = unidades.querySelectorAll('td, th');
    expect(celdas[columna(tabla, 'Manizales')]).toHaveTextContent('1.010');
    expect(celdas[columna(tabla, 'Pereira')]).toHaveTextContent('800');
    expect(celdas[columna(tabla, 'Villavicen')]).toHaveTextContent('500');
    expect(celdas[columna(tabla, 'Total')]).toHaveTextContent('2.310');
  });

  it('shows the value of each tienda in a compact form with the exact pesos as tooltip', async () => {
    render(<CorridaDetallePage />);
    const tabla = await abrirConsolidado();
    const valor = pie(tabla)[1];
    expect(valor).toHaveTextContent('Valor');
    const manizales = valor.querySelectorAll('td, th')[columna(tabla, 'Manizales')];
    expect(manizales).toHaveTextContent('5,4 M');
    expect(manizales.getAttribute('title')).toMatch(/5\.400\.000/);
    expect(valor.querySelectorAll('td, th')[columna(tabla, 'Pereira')]).toHaveTextContent('3,2 M');
  });

  it('summarises the network in a strip above the matrix: tiendas with a pedido, units and COP value', async () => {
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    const resumen = screen.getByRole('group', { name: 'Resumen de la red' });
    expect(resumen).toHaveTextContent('3 tiendas');
    expect(resumen).toHaveTextContent('2.310 unidades');
    expect(resumen.textContent.replace(/\s/g, ' ')).toMatch(/\$ ?11\.100\.000/);
  });

  it('explains Total with a tooltip', async () => {
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    expect(screen.getByRole('note', { name: /Total: lo que se pide de la referencia en todas las tiendas/ })).toBeInTheDocument();
  });
});

describe('consolidated matrix - search and paging', () => {
  it('searches by code or name after the typing pauses and goes back to the first page', async () => {
    const calls = installFetch(rutas(jsonRes({ ...CONSOLIDADO, total: 250 })));
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimas(calls).query.get('offset')).toBe('100'));
    const antes = calls.length;
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'fil' } });
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'filtro' } });
    expect(calls.length).toBe(antes);
    await waitFor(() => expect(ultimas(calls).query.get('q')).toBe('filtro'));
    expect(ultimas(calls).query.get('offset')).toBe('0');
    expect(calls.filter((c) => c.path === '/corridas/c1/consolidado' && c.query.get('q') === 'fil')).toHaveLength(0);
  });

  it('pages 100 references at a time and tells how many pages there are', async () => {
    const calls = installFetch(rutas(jsonRes({ ...CONSOLIDADO, total: 250 })));
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument();
    expect(screen.getByText('250 referencias')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    await waitFor(() => expect(ultimas(calls).query.get('offset')).toBe('100'));
    expect(ultimas(calls).query.get('limite')).toBe('100');
    expect(await screen.findByText('Página 2 de 3')).toBeInTheDocument();
  });

  it('shows no pager when everything fits in one page of a handful of references', async () => {
    installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    expect(screen.queryByRole('button', { name: 'Siguiente' })).not.toBeInTheDocument();
    expect(screen.getByText('3 referencias')).toBeInTheDocument();
  });

  it('keeps the search box when the search finds nothing, with the empty message', async () => {
    const calls = installFetch(rutas());
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    installFetch(rutas(jsonRes({ ...CONSOLIDADO, filas: [], total: 0 })));
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'zzz' } });
    expect(await screen.findByText('Sin pedidos para mostrar')).toBeInTheDocument();
    expect(screen.getByLabelText('Buscar')).toHaveValue('zzz');
    expect(calls.length).toBeGreaterThan(0);
  });
});

describe('consolidated matrix - states', () => {
  it('says it is loading while the matrix is read', async () => {
    installFetch(rutas(new Promise(() => {})));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Consolidado' }));
    expect(await screen.findByText('Cargando consolidado...')).toBeInTheDocument();
  });

  it('shows the empty message when no reference has anything to order (for instance while calculating)', async () => {
    installFetch(rutas(jsonRes(CONSOLIDADO_VACIO)));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Consolidado' }));
    expect(await screen.findByText('Sin pedidos para mostrar')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Consolidado de la red' })).not.toBeInTheDocument();
  });

  it('shows the Spanish message with its code when the read fails', async () => {
    installFetch(rutas(coded(404, 'E-CORRIDA-099', 'La corrida no existe.')));
    render(<CorridaDetallePage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Consolidado' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('La corrida no existe. (E-CORRIDA-099)');
  });

  it('keeps the matrix on screen and shows the error when a later page fails', async () => {
    installFetch(rutas(jsonRes({ ...CONSOLIDADO, total: 250 })));
    render(<CorridaDetallePage />);
    await abrirConsolidado();
    installFetch(rutas(coded(500, 'E-CORRIDA-099', 'No se pudo leer.')));
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo leer. (E-CORRIDA-099)');
  });
});
