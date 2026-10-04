import { fireEvent, render, screen, within } from '@testing-library/react';
import TiendasTab from '../components/motored/kpis/tiendas/TiendasTab';
import { Scatter } from '../components/motored/kpis/charts';
import { TIENDAS, TIENDAS_SIN_PRESUPUESTO } from './helpers/kpisTiendasFixture';

const montar = (data = TIENDAS) => render(<TiendasTab data={data} />);
const seccion = (nombre) => screen.getByRole('region', { name: nombre });

describe('Tiendas tab: layout', () => {
  it('renders every card in the design order', () => {
    montar();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Tendencia · últimos 3 meses vs 3 anteriores',
      'Dónde cae cada tienda · cumplimiento may–jul',
      'Ranking de tiendas · may–jul',
      'Venta mensual por tienda · vs su promedio',
      'Venta vs margen',
    ]);
  });

  it('shows the trend donut with the store count and the legend counts', () => {
    montar();
    const tarjeta = seccion('Tendencia de las tiendas');
    expect(within(tarjeta).getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('Crecen 2'));
    expect(within(tarjeta).getByText('5')).toBeInTheDocument();
    expect(within(tarjeta).getByText('tiendas')).toBeInTheDocument();
    const filas = within(tarjeta).getAllByTestId('tendencia-leyenda').map((f) => f.textContent);
    expect(filas).toEqual(['Crecen2', 'Caen2', 'Nuevas1']);
  });

  it('shows the six figures with the store that owns each one', () => {
    montar();
    const mini = seccion('Indicadores de las tiendas');
    expect(within(mini).getByText('Venta promedio por tienda')).toBeInTheDocument();
    expect(within(mini).getByText('$175 M')).toBeInTheDocument();
    expect(within(mini).getByText('31,0%')).toBeInTheDocument();
    expect(within(mini).getByText('Medellín La 33')).toBeInTheDocument();
    expect(within(mini).getByText('+18,0%')).toBeInTheDocument();
    expect(within(mini).getByText('−20,0%')).toBeInTheDocument();
    expect(within(mini).getByText('Popayán')).toBeInTheDocument();
    expect(within(mini).getByText('$120.000')).toBeInTheDocument();
    expect(within(mini).getByText('98 días')).toBeInTheDocument();
    expect(within(mini).getByText('Cali Cra 1 Dos')).toBeInTheDocument();
    expect(within(mini).getAllByRole('note').length).toBeGreaterThanOrEqual(3);
  });

  it('counts the stores per compliance zone', () => {
    montar();
    const tarjeta = seccion('Dónde cae cada tienda');
    expect(within(tarjeta).getByText(/≥ 90%/)).toHaveTextContent('≥ 90% · 2');
    expect(within(tarjeta).getByText(/< 70%/)).toHaveTextContent('< 70% · 1');
  });
});

describe('Tiendas tab: ranking', () => {
  it('starts on Venta with rank, value, invoices, ticket, margin chip vs the network and growth chip', () => {
    montar();
    const tarjeta = seccion('Ranking de tiendas');
    expect(within(tarjeta).getByRole('button', { name: 'Venta' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(tarjeta).getAllByTestId('rank-badge')).toHaveLength(5);
    expect(within(tarjeta).getByText('$300 M')).toBeInTheDocument();
    expect(within(tarjeta).getByText('2.500 facturas · ticket $120.000 · 41 días de inv.')).toBeInTheDocument();
    const margen = within(tarjeta).getByText('Margen 28,0%');
    expect(margen).toHaveAttribute('data-variant', 'up');
    expect(within(tarjeta).getByText('Margen 24,0%')).toHaveAttribute('data-variant', 'down');
    expect(within(tarjeta).getByText('▲ 18,0%')).toHaveAttribute('data-variant', 'up');
    expect(within(tarjeta).getByText('▼ 12,0%')).toHaveAttribute('data-variant', 'down');
    expect(within(tarjeta).getByText('Nueva')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Margen —')).toHaveAttribute('data-variant', 'flat');
  });

  it('puts the inventory cut date in the tooltip and a dash when the store has no inventory', () => {
    montar();
    const tarjeta = seccion('Ranking de tiendas');
    expect(within(tarjeta).getByText(/41 días de inv\./)).toHaveAttribute('title', 'Inventario al 31/07/2026');
    expect(within(tarjeta).getByText(/ticket \$52\.000 · — días de inv\./)).toHaveAttribute('title', 'Falta cargar el inventario con costo');
  });

  it('Crecimiento: diverging bars from the biggest riser to the biggest faller, without the new stores', () => {
    montar();
    const tarjeta = seccion('Ranking de tiendas');
    fireEvent.click(within(tarjeta).getByRole('button', { name: 'Crecimiento' }));
    expect(within(tarjeta).queryByText('Armenia Nueva')).not.toBeInTheDocument();
    expect(within(tarjeta).getByText('▼ cae')).toBeInTheDocument();
    expect(within(tarjeta).getByText('crece ▲')).toBeInTheDocument();
    const nombres = within(tarjeta).getAllByTestId('diverging-name').map((n) => n.textContent);
    expect(nombres).toEqual(['Bogotá Av. Boyacá', 'Medellín La 33', 'Cali Cra 1 Dos', 'Popayán']);
    expect(within(tarjeta).getAllByText('+18,0%')[0]).toHaveAttribute('data-side', 'pos');
    expect(within(tarjeta).getAllByText('−20,0%')[0]).toHaveAttribute('data-side', 'neg');
  });

  it('Mezcla: a 100% bar per store with the legend and the repuestos share at the right', () => {
    montar();
    const tarjeta = seccion('Ranking de tiendas');
    fireEvent.click(within(tarjeta).getByRole('button', { name: 'Mezcla' }));
    expect(within(tarjeta).getAllByTestId('mezcla-leyenda').map((l) => l.textContent)).toEqual(['Repuestos', 'Lubricantes', 'Accesorios', 'Llantas']);
    const filas = within(tarjeta).getAllByTestId('mezcla-fila');
    expect(filas).toHaveLength(5);
    expect(within(filas[0]).getByText('Bogotá Av. Boyacá')).toBeInTheDocument();
    expect(within(filas[0]).getByText('60%')).toBeInTheDocument();
    expect(within(filas[0]).getAllByTestId('segment')).toHaveLength(4);
  });
});

describe('Tiendas tab: heatmap and scatter', () => {
  it('heatmap: one row per store and one column per month, with a dash where the store had no sales', () => {
    montar();
    const tarjeta = seccion('Venta mensual por tienda');
    expect(within(tarjeta).getAllByTestId('heat-cell')).toHaveLength(15);
    ['May', 'Jun', 'Jul'].forEach((m) => expect(within(tarjeta).getByText(m)).toBeInTheDocument());
    expect(within(tarjeta).getAllByText('–')).toHaveLength(1);
    expect(within(tarjeta).getAllByTestId('heat-legend-item')).toHaveLength(6);
  });

  it('scatter: a dot per store with margin, quadrant lines, labels and axis texts; stores without cost are noted', () => {
    montar();
    const tarjeta = seccion('Venta vs margen');
    const grafico = within(tarjeta).getByRole('img', { name: /Venta vs margen/ });
    expect(grafico.querySelectorAll('[data-point]')).toHaveLength(4);
    expect(grafico.querySelector('[data-quadrant="x"]')).toBeInTheDocument();
    expect(grafico.querySelector('[data-quadrant="y"]')).toBeInTheDocument();
    expect(within(tarjeta).getByTestId('point-label-t1')).toHaveTextContent('Bogotá Av. Boyacá');
    expect(within(tarjeta).getByText('Alta venta · alto margen')).toBeInTheDocument();
    expect(within(tarjeta).getByText('Baja venta · bajo margen')).toBeInTheDocument();
    expect(within(tarjeta).getByText('crece')).toBeInTheDocument();
    expect(within(tarjeta).getByText('nueva')).toBeInTheDocument();
    expect(within(tarjeta).getByText(/1 tienda sin costo/)).toBeInTheDocument();
  });
});

describe('Tiendas tab: empty states', () => {
  it('shows the budgets link in the strip and dashes for the inventory days', () => {
    montar(TIENDAS_SIN_PRESUPUESTO);
    expect(within(seccion('Dónde cae cada tienda')).getByRole('link', { name: /Cargá los presupuestos/ })).toBeInTheDocument();
    const mini = seccion('Indicadores de las tiendas');
    expect(within(mini).getByText('Más días de inventario').closest('div')).toHaveTextContent('—');
    expect(within(mini).queryByText(/días$/)).not.toBeInTheDocument();
  });
});

describe('Scatter extras for the Tiendas tab', () => {
  const puntos = [{ id: 'a', x: 10, y: 20, r: 6, tip: 'Alfa · detalle', label: 'Alfa' }];

  it('labels a highlighted point with its `label` and keeps `tip` as the tooltip', () => {
    const { container } = render(<Scatter points={puntos} xDomain={[0, 20]} yDomain={[10, 30]} highlight={['a']} />);
    expect(screen.getByTestId('point-label-a')).toHaveTextContent('Alfa');
    expect(screen.getByTestId('point-label-a')).not.toHaveTextContent('detalle');
    expect(container.querySelector('title')).toHaveTextContent('Alfa · detalle');
  });

  it('draws y ticks, x ticks and corner labels as overlays', () => {
    render(
      <Scatter
        points={puntos} xDomain={[0, 20]} yDomain={[10, 30]}
        yTicks={[{ value: 10, label: '10%' }, { value: 30, label: '30%' }]} xTicks={[{ value: 0, label: '$0' }, { value: 20, label: '$20 M' }]}
        cornerLabels={{ topRight: 'Arriba derecha', bottomLeft: 'Abajo izquierda' }}
      />,
    );
    ['10%', '30%', '$0', '$20 M', 'Arriba derecha', 'Abajo izquierda'].forEach((t) => expect(screen.getByText(t)).toBeInTheDocument());
  });
});
