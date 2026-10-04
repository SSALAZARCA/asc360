import { fireEvent, render, screen, within } from '@testing-library/react';
import VentasTab from '../components/motored/kpis/ventas/VentasTab';
import { crecimiento3m, filasCumplimiento } from '../components/motored/kpis/ventas/datos';
import { VENTAS, VENTAS_SIN_PRESUPUESTO } from './helpers/kpisVentasFixture';

const FILTROS = { meses: ['2026-05', '2026-06', '2026-07'], sucursales: [], hmcl: 'incluir' };
const montar = (data = VENTAS) => render(<VentasTab data={data} filtros={FILTROS} />);
const seccion = (nombre) => screen.getByRole('region', { name: nombre });

describe('Ventas tab: layout', () => {
  it('renders every section in the design order', () => {
    montar();
    const titulos = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(titulos).toEqual([
      'Cumplimiento presupuesto · may–jul',
      'Dónde cae cada tienda · cumplimiento may–jul',
      'Cumplimiento por tienda · may–jul',
      'Venta mensual por línea',
      'Clientes Tecnired · may–jul',
      'Top 5 clientes Tecnired · may–jul',
    ]);
  });

  it('shows the gauge with the compliance and the "$X M de $Y M" label formatted es-CO', () => {
    montar();
    const gauge = within(seccion('Cumplimiento presupuesto')).getByRole('img');
    expect(gauge).toHaveAttribute('aria-label', expect.stringContaining('78,0%'));
    expect(gauge).toHaveAttribute('data-tone', 'mid');
    expect(screen.getByText('$1.554 M de $1.993 M')).toBeInTheDocument();
  });

  it('shows the six mini KPIs with the HMCL and discount chips', () => {
    montar();
    const mini = seccion('Indicadores de la red');
    expect(within(mini).getByText('Venta 3 meses')).toBeInTheDocument();
    expect(within(mini).getByText('$1.330 M')).toBeInTheDocument();
    expect(within(mini).getByText('27,1%')).toBeInTheDocument();
    expect(within(mini).getByText('$85.615')).toBeInTheDocument();
    expect(within(mini).getByText('154.387')).toBeInTheDocument();
    expect(within(mini).getByText('95.289')).toBeInTheDocument();
    expect(within(mini).getByText('HMCL 8,0%')).toBeInTheDocument();
    expect(within(mini).getByText('$176 M')).toBeInTheDocument();
    expect(within(mini).getByText('1,31%')).toBeInTheDocument();
  });

  it('has a tooltip on the non-obvious KPIs', () => {
    montar();
    expect(within(seccion('Indicadores de la red')).getAllByRole('note').length).toBeGreaterThanOrEqual(3);
  });
});

describe('Ventas tab: compliance per store', () => {
  it('counts the stores per semaforo zone with the configured cuts', () => {
    montar();
    const tarjeta = seccion('Cumplimiento por tienda');
    expect(within(tarjeta).getByText(/≥ 90%/)).toHaveTextContent('≥ 90% · 1');
    expect(within(tarjeta).getByText(/70–90%/)).toHaveTextContent('70–90% · 1');
    expect(within(tarjeta).getByText(/< 70%/)).toHaveTextContent('< 70% · 1');
  });

  it('starts as traffic lights and switches to bars and back', () => {
    montar();
    const tarjeta = seccion('Cumplimiento por tienda');
    expect(within(tarjeta).getAllByTestId('traffic-cell')).toHaveLength(4);
    expect(within(tarjeta).getByRole('button', { name: 'Semáforo' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(within(tarjeta).getByRole('button', { name: 'Barras' }));
    expect(within(tarjeta).queryAllByTestId('traffic-cell')).toHaveLength(0);
    const filas = within(tarjeta).getAllByTestId('cumplimiento-fila');
    expect(filas.map((f) => within(f).getByTestId('cumplimiento-nombre').textContent)).toEqual([
      'Bogotá Av. Boyacá', 'Cali Cra 1 Dos', 'Popayán', 'Tienda Sin Presupuesto',
    ]);
    expect(within(filas[0]).getByText('$200 M / $180 M')).toBeInTheDocument();
    expect(within(filas[0]).getByText('111,1%')).toBeInTheDocument();
    expect(within(filas[3]).getByText('Sin presupuesto')).toBeInTheDocument();
    expect(within(tarjeta).getByTestId('referencia-100')).toBeInTheDocument();
    expect(tarjeta.querySelector('[data-testid="cumplimiento-lista"]')).toHaveStyle({ maxHeight: '340px' });
    fireEvent.click(within(tarjeta).getByRole('button', { name: 'Semáforo' }));
    expect(within(tarjeta).getAllByTestId('traffic-cell')).toHaveLength(4);
  });

  it('puts stores without budget at the end, grey, in the traffic lights too', () => {
    montar();
    const celdas = within(seccion('Cumplimiento por tienda')).getAllByTestId('traffic-cell');
    expect(celdas[3]).toHaveAttribute('data-tone', 'none');
    expect(celdas[3]).toHaveTextContent('Sin presupuesto');
  });

  it('draws one dot per budgeted store in the zone strip with the counts in the legend', () => {
    montar();
    const franja = seccion('Dónde cae cada tienda');
    expect(franja.querySelectorAll('[data-level]')).toHaveLength(3);
    expect(within(franja).getByText(/≥ 90%/)).toHaveTextContent('≥ 90% · 1');
  });

  it('orders the rows by compliance, highest first', () => {
    const filas = filasCumplimiento(VENTAS);
    expect(filas.map((f) => f.nombre)).toEqual(['Bogotá Av. Boyacá', 'Cali Cra 1 Dos', 'Popayán', 'Tienda Sin Presupuesto']);
    expect(filas[3].fraccion).toBeNull();
  });
});

describe('Ventas tab: monthly sales by line and Tecnired', () => {
  it('shows a tile per line with its share and value, and the stacked area with totals', () => {
    montar();
    const tarjeta = seccion('Venta mensual por línea');
    expect(within(tarjeta).getAllByText('Repuestos')).toHaveLength(2);
    expect(within(tarjeta).getAllByText('60,2%').length).toBeGreaterThan(0);
    expect(within(tarjeta).getAllByTestId('area-total')).toHaveLength(3);
    expect(within(tarjeta).getAllByText('Baterías')).toHaveLength(2);
  });

  it('shows the Tecnired donut, stats, monthly bars with percentages and the line mix', () => {
    montar();
    const tarjeta = seccion('Clientes Tecnired');
    expect(within(tarjeta).getAllByText('$945 M').length).toBeGreaterThan(0);
    expect(within(tarjeta).getByText('6,3% del total')).toBeInTheDocument();
    expect(within(tarjeta).getByText('542')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$1,7 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('$280 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('May')).toBeInTheDocument();
    expect(within(tarjeta).getByText(/Repuestos/)).toBeInTheDocument();
    expect(within(tarjeta).getByText(/Otras/)).toBeInTheDocument();
    expect(within(tarjeta).getByRole('img', { name: /Repuestos 74,1%/ })).toBeInTheDocument();
  });

  it('lists the top 5 Tecnired clients with rank badges', () => {
    montar();
    const top = seccion('Top 5 clientes Tecnired');
    expect(within(top).getAllByTestId('top-cliente')).toHaveLength(5);
    expect(within(top).getByText('Taller Uno SAS')).toBeInTheDocument();
    expect(within(top).getByText('$90 M')).toBeInTheDocument();
    expect(within(top).getByText('5')).toBeInTheDocument();
  });
});

describe('Ventas tab: empty states and growth', () => {
  it('asks to load the budgets when there are none', () => {
    montar(VENTAS_SIN_PRESUPUESTO);
    const avisos = screen.getAllByText(/Cargá los presupuestos en Maestros → Presupuestos/);
    expect(avisos.length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByRole('link', { name: /Maestros → Presupuestos/ })[0]).toHaveAttribute('href', '/motored/maestros');
    expect(screen.queryByRole('img', { name: /Cumplimiento:/ })).toBeNull();
  });

  it('shows the margin as a dash with a tooltip when there is no cost data', () => {
    montar(VENTAS_SIN_PRESUPUESTO);
    const mini = seccion('Indicadores de la red');
    expect(within(mini).getByText('Margen').closest('div')).toHaveTextContent('—');
    expect(within(mini).getByText('Falta cargar el inventario con costo')).toBeInTheDocument();
  });

  it('computes the 3 months vs previous 3 months growth only over contiguous calendar months', () => {
    const porMes = { '2026-01': 100, '2026-02': 100, '2026-03': 100, '2026-04': 110, '2026-05': 110, '2026-06': 110 };
    expect(crecimiento3m(porMes)).toBeCloseTo(0.1);
    expect(crecimiento3m({ '2026-05': 1, '2026-06': 1, '2026-07': 1 })).toBeNull();
    expect(crecimiento3m({ ...porMes, '2026-02': undefined, '2026-08': 5 })).toBeNull();
  });

  it('shows the growth chip when six months are selected', () => {
    const meses = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06'];
    const data = {
      ...VENTAS, meses,
      total: { ...VENTAS.total, venta: { ...VENTAS.total.venta, por_mes: Object.fromEntries(meses.map((m, i) => [m, i < 3 ? 100 : 90])) } },
    };
    render(<VentasTab data={data} filtros={{ ...FILTROS, meses }} />);
    expect(within(seccion('Indicadores de la red')).getByText('▼ 10,0% 3M')).toBeInTheDocument();
  });
});
