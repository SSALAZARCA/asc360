import { render, screen, within } from '@testing-library/react';
import AsesorDetalle from '../components/motored/kpis/asesores/AsesorDetalle';
import TiendasTab from '../components/motored/kpis/tiendas/TiendasTab';
import { matrizMensual } from '../components/motored/kpis/tiendas/datos';
import VentasTab from '../components/motored/kpis/ventas/VentasTab';
import { ventaPorLinea } from '../components/motored/kpis/ventas/datos';
import { barrasMensuales } from '../components/motored/kpis/ventas/tecniredDatos';
import { ASESOR_DETALLE } from './helpers/kpisAsesorDetalleFixture';
import { TIENDAS } from './helpers/kpisTiendasFixture';
import { LINEAS, VENTAS } from './helpers/kpisVentasFixture';

const NOTA = 'Últimos 12 meses · no cambia con el período';
const VENTANA = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'];
const M = 1e6;
const FILTROS = { meses: ['2026-07'], sucursales: [], hmcl: 'incluir' };
const seccion = (nombre) => screen.getByRole('region', { name: nombre });

const ventaDeMes = (i) => (100 + i * 10) * M;
const totalDeVentana = {
  ...VENTAS.total,
  venta: {
    ...VENTAS.total.venta,
    total: VENTANA.reduce((s, _, i) => s + ventaDeMes(i), 0),
    por_mes: Object.fromEntries(VENTANA.map((m, i) => [m, ventaDeMes(i)])),
    por_linea: Object.fromEntries(LINEAS.map((l, j) => [l, (7 - j) * 100 * M])),
    por_mes_linea: Object.fromEntries(VENTANA.map((m) => [m, Object.fromEntries(LINEAS.map((l, j) => [l, (7 - j) * 10 * M]))])),
  },
};
const tecniredDeVentana = {
  ...VENTAS.tecnired, venta: 70 * M, clientes: 33, venta_por_cliente: 70 * M / 33,
  por_mes: Object.fromEntries(VENTANA.map((m, i) => [m, { venta: (5 + i * 5) * M, clientes: 10 + i }])),
  por_linea: { REPUESTOS: 50 * M, LUBRICANTES: 20 * M },
};
const ventasDelMes = {
  ...VENTAS,
  meses: ['2026-07'],
  ventana_meses: VENTANA,
  ventana: { total: totalDeVentana, tecnired: tecniredDeVentana },
};

describe('Ventas tab: the monthly charts ignore the period', () => {
  it('"Venta mensual por línea" has every month of the window, not only the selected one', () => {
    const { meses, lineas } = ventaPorLinea(ventasDelMes);
    expect(meses).toEqual(VENTANA);
    expect(lineas[0].values).toHaveLength(7);
    expect(lineas[0].total).toBe(700 * M);
  });

  it('shows the note under the title, and the share tiles come from the window', () => {
    render(<VentasTab data={ventasDelMes} filtros={FILTROS} />);
    const tarjeta = within(seccion('Venta mensual por línea'));
    expect(tarjeta.getByText(NOTA)).toBeInTheDocument();
    expect(tarjeta.getAllByText('Repuestos')[1].parentElement).toHaveTextContent('25,0%'); // 700 of 2.800
  });

  it('"Clientes Tecnired" names the window months and draws a bar per month with the window figures', () => {
    render(<VentasTab data={ventasDelMes} filtros={FILTROS} />);
    const tarjeta = within(seccion('Clientes Tecnired'));
    expect(tarjeta.getByRole('heading', { level: 2 })).toHaveTextContent('Clientes Tecnired · ene–jul');
    expect(tarjeta.getByText(NOTA)).toBeInTheDocument();
    expect(tarjeta.getByText('33')).toBeInTheDocument(); // clients of the window
    expect(barrasMensuales(ventasDelMes).map((b) => b.mes)).toEqual(VENTANA);
    expect(tarjeta.getByText('▲ 5,0% → 21,9% de la venta')).toBeInTheDocument();
  });

  it('the top 5 clients keep following the period', () => {
    render(<VentasTab data={ventasDelMes} filtros={FILTROS} />);
    expect(screen.getByRole('heading', { name: 'Top 5 clientes Tecnired · julio' })).toBeInTheDocument();
  });

  it('an older payload without the window still draws the period', () => {
    expect(ventaPorLinea(VENTAS).meses).toEqual(['2026-05', '2026-06', '2026-07']);
    render(<VentasTab data={VENTAS} filtros={FILTROS} />);
    expect(screen.getByRole('heading', { name: 'Clientes Tecnired · may–jul' })).toBeInTheDocument();
  });
});

const tiendasDeVentana = TIENDAS.tiendas.map((t) => ({
  sucursal_id: t.sucursal_id, nombre: t.nombre,
  venta: { total: 7 * 50 * M, por_mes: Object.fromEntries(VENTANA.map((m) => [m, 50 * M])) },
}));
const tiendasDelMes = { ...TIENDAS, meses: ['2026-07'], ventana_meses: VENTANA, ventana: { tiendas: tiendasDeVentana } };

describe('Tiendas tab: the heatmap ignores the period', () => {
  it('has a column per month of the window and the window average of each store', () => {
    const { columns, rows } = matrizMensual(tiendasDelMes);
    expect(columns).toEqual(['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul']);
    expect(rows).toHaveLength(5);
    expect(rows[0].values).toEqual([50, 50, 50, 50, 50, 50, 50]);
  });

  it('shows the note under the title', () => {
    render(<TiendasTab data={tiendasDelMes} />);
    expect(within(seccion('Venta mensual por tienda')).getByText(NOTA)).toBeInTheDocument();
  });

  it('an older payload without the window still draws the period', () => {
    expect(matrizMensual(TIENDAS).columns).toEqual(['May', 'Jun', 'Jul']);
  });
});

describe('Asesor detail: the compliance trend ignores the period', () => {
  const tendencia = VENTANA.map((mes, i) => ({ mes, pct: i === 2 ? null : 0.8 + i * 0.03, red_pct: 0.85 }));

  it('draws the whole window and says so under the title', () => {
    render(<AsesorDetalle data={{ ...ASESOR_DETALLE, meses: ['2026-07'], ventana_meses: VENTANA, tendencia }} />);
    const tarjeta = within(seccion('Tendencia de cumplimiento'));
    expect(tarjeta.getByText(NOTA)).toBeInTheDocument();
    expect(tarjeta.getByText('Ene')).toBeInTheDocument();
    expect(tarjeta.getByText(/Cumplió \(≥ 90%\) en 3 de 6 meses con presupuesto/)).toBeInTheDocument();
  });
});
