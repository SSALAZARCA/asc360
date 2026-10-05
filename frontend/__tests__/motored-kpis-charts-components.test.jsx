import { fireEvent, render, screen, within } from '@testing-library/react';
import {
  BarList, Donut, DivergingBars, Gauge, Heatmap, KpiMiniGrid, Scatter, SegmentedToggle,
  ShareTiles, StackedArea, StackedBar100, Treemap, TrafficLightGrid, ZoneStrip,
} from '../components/motored/kpis/charts';

const CORTES = { verde_desde: 90, ambar_desde: 70 };

describe('Gauge', () => {
  it('summarizes the value for assistive tech and paints by semaforo', () => {
    render(<Gauge value={0.78} cortes={CORTES} title="Cumplimiento" label="$1.554 M de $1.993 M" />);
    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('aria-label', expect.stringContaining('78,0%'));
    expect(img).toHaveAttribute('aria-label', expect.stringContaining('$1.554 M de $1.993 M'));
    expect(img).toHaveAttribute('data-tone', 'mid');
    expect(screen.getByText('$1.554 M de $1.993 M')).toBeInTheDocument();
  });

  it('is green from the green cut and violet below the amber cut', () => {
    const { rerender } = render(<Gauge value={0.9} cortes={CORTES} />);
    expect(screen.getByRole('img')).toHaveAttribute('data-tone', 'good');
    rerender(<Gauge value={0.5} cortes={CORTES} />);
    expect(screen.getByRole('img')).toHaveAttribute('data-tone', 'bad');
  });

  it('has no text nodes inside the svg and shows a dash without value', () => {
    const { container, rerender } = render(<Gauge value={0.78} cortes={CORTES} />);
    expect(container.querySelector('svg text')).toBeNull();
    rerender(<Gauge value={null} cortes={CORTES} />);
    expect(screen.getByRole('img')).toHaveAttribute('data-tone', 'none');
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('Donut', () => {
  const segments = [
    { label: 'Repuestos', value: 75, color: '#111' },
    { label: 'Lubricantes', value: 25, color: '#222' },
  ];

  it('draws one arc per segment and a legend with counts and percentages', () => {
    const { container } = render(<Donut segments={segments} centerTitle="100" centerSubtitle="ventas" legend />);
    expect(container.querySelectorAll('circle[data-segment]')).toHaveLength(2);
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('Repuestos 75 (75,0%)'));
    const item = screen.getByText('Repuestos').closest('li');
    expect(within(item).getByText('75')).toBeInTheDocument();
    expect(within(item).getByText('75,0%')).toBeInTheDocument();
    expect(screen.getByText('ventas')).toBeInTheDocument();
  });

  it('omits the legend when not asked and survives an empty set', () => {
    const { container, rerender } = render(<Donut segments={segments} />);
    expect(screen.queryByRole('list')).toBeNull();
    rerender(<Donut segments={[]} />);
    expect(container.querySelectorAll('circle[data-segment]')).toHaveLength(0);
  });
});

describe('ZoneStrip', () => {
  it('renders dots with tooltips, stacked when they collide', () => {
    render(
      <ZoneStrip
        min={0} max={150} lines={[90]}
        zones={[{ hasta: 90, bg: '#a' }, { hasta: 150, bg: '#b' }]}
        dots={[{ value: 80, color: '#1', tip: 'Tienda A' }, { value: 80, color: '#2', tip: 'Tienda B' }]}
        ticks={[{ value: 0, label: '0%' }, { value: 150, label: '150%+' }]}
        ariaLabel="Dónde cae cada tienda"
      />,
    );
    expect(screen.getByRole('img', { name: 'Dónde cae cada tienda' })).toBeInTheDocument();
    expect(screen.getByTitle('Tienda A')).toHaveAttribute('data-level', '0');
    expect(screen.getByTitle('Tienda B')).toHaveAttribute('data-level', '1');
    expect(screen.getByText('150%+')).toBeInTheDocument();
  });
});

describe('BarList', () => {
  const items = [
    { name: 'Alfa', sub: 'Medellín', value: 100, valueText: '$100 M', chips: [{ text: 'Margen 30%', variant: 'up' }] },
    { name: 'Beta', value: 50, valueText: '$50 M' },
    { name: 'Gama', value: 10, valueText: '$10 M' },
    { name: 'Delta', value: 5, valueText: '$5 M' },
  ];

  it('numbers the rows with medal colors, then neutral', () => {
    render(<BarList items={items} />);
    const badges = screen.getAllByTestId('rank-badge');
    expect(badges.map((b) => b.textContent)).toEqual(['1', '2', '3', '4']);
    expect(badges.map((b) => b.getAttribute('data-medal'))).toEqual(['1', '2', '3', 'rest']);
  });

  it('writes the value inside the bar from 20% width and outside below it', () => {
    render(<BarList items={items} />);
    expect(screen.getByText('$100 M')).toHaveAttribute('data-label', 'inside');
    expect(screen.getByText('$50 M')).toHaveAttribute('data-label', 'inside');
    expect(screen.getByText('$10 M')).toHaveAttribute('data-label', 'outside');
    expect(screen.getByText('$5 M')).toHaveAttribute('data-label', 'outside');
  });

  it('shows name, subtitle and chips; scrolls inside its own box', () => {
    const { container } = render(<BarList items={items} maxHeight={240} />);
    expect(screen.getByText('Medellín')).toBeInTheDocument();
    expect(screen.getByText('Margen 30%')).toHaveAttribute('data-variant', 'up');
    expect(container.firstChild).toHaveStyle({ maxHeight: '240px', overflowY: 'auto' });
  });

  it('draws the reference line at its share of the scale', () => {
    render(<BarList items={[{ name: 'A', value: 120, valueText: '120%' }]} maxValue={150} reference={{ at: 100, label: 'Meta' }} />);
    expect(screen.getByTestId('reference-line')).toHaveAttribute('data-left', '66.67');
    expect(screen.getByText('Meta')).toBeInTheDocument();
  });
});

describe('DivergingBars', () => {
  it('sends negatives left and positives right, label inside from 22%', () => {
    render(
      <DivergingBars
        items={[
          { name: 'Sube', value: 40, valueText: '+40%' },
          { name: 'Baja', value: -20, valueText: '-20%' },
          { name: 'Poco', value: 5, valueText: '+5%' },
        ]}
      />,
    );
    expect(screen.getByText('+40%')).toHaveAttribute('data-side', 'pos');
    expect(screen.getByText('+40%')).toHaveAttribute('data-label', 'inside');
    expect(screen.getByText('-20%')).toHaveAttribute('data-side', 'neg');
    expect(screen.getByText('-20%')).toHaveAttribute('data-label', 'inside');
    expect(screen.getByText('+5%')).toHaveAttribute('data-label', 'outside');
  });
});

describe('StackedArea', () => {
  const props = {
    months: ['Ene', 'Feb', 'Mar'],
    series: [
      { name: 'Repuestos', color: '#111', values: [100, 200, 300] },
      { name: 'GPS', color: '#222', values: [50, 50, 100] },
    ],
    formatValue: (v) => `$${v} M`,
  };

  it('writes totals and months as HTML overlays, never svg text', () => {
    const { container } = render(<StackedArea {...props} />);
    expect(container.querySelector('svg text')).toBeNull();
    expect(screen.getAllByTestId('area-total').map((t) => t.textContent)).toEqual(['$150 M', '$250 M', '$400 M']);
    ['Ene', 'Feb', 'Mar'].forEach((m) => expect(screen.getByText(m)).toBeInTheDocument());
    expect(container.querySelectorAll('path[data-series]')).toHaveLength(2);
  });

  it('adds a legend and per-series share tiles on request', () => {
    render(<StackedArea {...props} showTiles />);
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('Repuestos'));
    // Repuestos 600 of 800 = 75%, GPS 200 of 800 = 25%
    expect(screen.getByText('75,0%')).toBeInTheDocument();
    expect(screen.getByText('25,0%')).toBeInTheDocument();
  });
});

describe('ShareTiles and StackedBar100', () => {
  const items = [
    { name: 'Repuestos', value: 600, color: '#1', valueText: '$600 M' },
    { name: 'GPS', value: 300, color: '#2', valueText: '$300 M' },
    { name: 'Otros', value: 100, color: '#3', valueText: '$100 M' },
  ];

  it('shows percentage and value per tile', () => {
    render(<ShareTiles items={items} />);
    expect(screen.getByText('60,0%')).toBeInTheDocument();
    expect(screen.getByText('$300 M')).toBeInTheDocument();
  });

  it('draws a 100% bar whose segments add up to the full width', () => {
    render(<StackedBar100 segments={items.map((i) => ({ label: i.name, value: i.value, color: i.color }))} />);
    const segs = screen.getAllByTestId('segment');
    const widths = segs.map((s) => Number(s.getAttribute('data-width')));
    expect(widths).toEqual([60, 30, 10]);
    expect(widths.reduce((a, b) => a + b, 0)).toBeCloseTo(100, 5);
    expect(screen.getByTitle('Repuestos 60,0%')).toBeInTheDocument();
  });
});

describe('Heatmap', () => {
  const rows = [{ name: 'Tienda 1', values: [100, 100, 100, 160, 0] }, { name: 'Tienda 2', values: [10, 10, 10, 10, 10] }];

  it('colors each cell against the row own average with 6 levels', () => {
    render(<Heatmap columns={['Ene', 'Feb', 'Mar', 'Abr', 'May']} rows={rows} />);
    const cells = screen.getAllByTestId('heat-cell');
    expect(cells[3]).toHaveAttribute('data-level', '1');
    expect(cells[0]).toHaveAttribute('data-level', '4');
    expect(cells[4]).toHaveAttribute('data-level', 'none');
    expect(cells[4]).toHaveTextContent('–');
    expect(cells[5]).toHaveAttribute('data-level', '3');
  });

  it('has a legend of 6 levels, a sticky header and its own scroll', () => {
    const { container } = render(<Heatmap columns={['Ene', 'Feb', 'Mar', 'Abr', 'May']} rows={rows} maxHeight={300} />);
    expect(screen.getAllByTestId('heat-legend-item')).toHaveLength(6);
    expect(container.querySelector('thead th')).toHaveStyle({ position: 'sticky' });
    expect(screen.getByTestId('heatmap-scroll')).toHaveStyle({ maxHeight: '300px', overflow: 'auto' });
  });
});

describe('Treemap', () => {
  const items = [
    { id: 'a', label: 'Bogotá', value: 600, colorValue: 1.2, sub: '+12%', valueText: '$600 M' },
    { id: 'b', label: 'Cali', value: 300, colorValue: 0.9 },
    { id: 'c', label: 'Pasto', value: 100, colorValue: 1 },
  ];

  it('draws tiles proportional to the value, covering the whole box', () => {
    render(<Treemap items={items} />);
    const tiles = screen.getAllByTestId('treemap-tile');
    const areas = tiles.map((t) => Number(t.getAttribute('data-area')));
    expect(areas.reduce((a, b) => a + b, 0)).toBeCloseTo(100, 1);
    expect(areas[0]).toBeCloseTo(60, 1);
    expect(areas[1]).toBeCloseTo(30, 1);
  });

  it('labels the tiles and accepts a color scale', () => {
    const scale = jest.fn(() => ({ bg: '#123456', fg: '#FFFFFF' }));
    render(<Treemap items={items} colorScale={scale} />);
    expect(screen.getByText('Bogotá')).toBeInTheDocument();
    expect(screen.getByText('$600 M')).toBeInTheDocument();
    expect(screen.getByText('+12%')).toBeInTheDocument();
    expect(scale).toHaveBeenCalledWith(1.2, expect.any(Object));
  });
});

describe('Gauge input coercion', () => {
  it('treats a numeric string like the number it spells', () => {
    const { rerender } = render(<Gauge value={0.78} cortes={CORTES} />);
    const num = screen.getByRole('img');
    const ref = [num.getAttribute('aria-label'), num.getAttribute('data-tone')];
    rerender(<Gauge value="0.78" cortes={CORTES} />);
    const str = screen.getByRole('img');
    expect([str.getAttribute('aria-label'), str.getAttribute('data-tone')]).toEqual(ref);
  });

  it('draws the arc that its label announces', () => {
    const { container } = render(<Gauge value="0.9" cortes={CORTES} />);
    expect(container.querySelector('path[stroke-dasharray]')).not.toBeNull();
    expect(screen.getByRole('img')).toHaveAttribute('data-tone', 'good');
  });

  it('rejects non-numeric input consistently', () => {
    const { container } = render(<Gauge value="abc" cortes={CORTES} />);
    expect(screen.getByRole('img')).toHaveAttribute('data-tone', 'none');
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('—');
    expect(container.querySelector('path[stroke-dasharray]')).toBeNull();
  });
});

describe('Scatter degenerate domains', () => {
  const noNaN = (container) => {
    const markup = container.innerHTML;
    expect(markup).not.toMatch(/NaN|Infinity/);
  };

  it('keeps finite positions when min equals max', () => {
    const pts = [{ id: 'a', x: 5, y: 7, tip: 'A' }, { id: 'b', x: 5, y: 7, tip: 'B' }];
    const { container } = render(<Scatter points={pts} xDomain={[5, 5]} yDomain={[7, 7]} quadrant={{ x: 5, y: 7 }} highlight={['a']} />);
    noNaN(container);
  });

  it('renders with no points and no domain', () => {
    const { container } = render(<Scatter points={[]} quadrant={{ x: 1, y: 1 }} />);
    noNaN(container);
  });

  it('derives the domain from the points when it is not given', () => {
    const pts = [{ id: 'a', x: 1, y: 2, tip: 'A' }, { id: 'b', x: 3, y: 4, tip: 'B' }];
    const { container } = render(<Scatter points={pts} />);
    noNaN(container);
  });
});

describe('Scatter', () => {
  const points = [
    { id: 'a', x: 10, y: 20, r: 6, color: '#111', tip: 'Tienda A' },
    { id: 'b', x: 30, y: 80, r: 4, color: '#222', tip: 'Tienda B' },
    { id: 'c', x: 50, y: 50, tip: 'Tienda C' },
  ];

  it('draws one dot per point with title tooltips and the quadrant lines', () => {
    const { container } = render(
      <Scatter points={points} xDomain={[0, 100]} yDomain={[0, 100]} quadrant={{ x: 25, y: 50 }}
        xLabel="Margen" yLabel="Cumplimiento" highlight={['b']} ariaLabel="Margen vs cumplimiento" />,
    );
    expect(screen.getByRole('img', { name: 'Margen vs cumplimiento' })).toBeInTheDocument();
    expect(container.querySelectorAll('circle[data-point]')).toHaveLength(3);
    expect(container.querySelector('circle[data-point="a"] title')).toHaveTextContent('Tienda A');
    expect(container.querySelectorAll('line[data-quadrant]')).toHaveLength(2);
    expect(screen.getByText('Margen')).toBeInTheDocument();
    expect(screen.getByText('Cumplimiento')).toBeInTheDocument();
  });

  it('labels only the highlighted points, as HTML', () => {
    const { container } = render(
      <Scatter points={points} xDomain={[0, 100]} yDomain={[0, 100]} highlight={['b']} />,
    );
    expect(screen.getByTestId('point-label-b')).toHaveTextContent('Tienda B');
    expect(screen.queryByTestId('point-label-a')).toBeNull();
    expect(container.querySelector('svg text')).toBeNull();
  });
});

describe('BarList long value text', () => {
  const largo = '$450 M / $2.133 M';
  const items = [
    { name: 'Alfa', value: 100, valueText: '$9 M' },
    { name: 'Beta', value: 22, valueText: largo, sub: 'Cali' },
  ];

  it('writes it outside the fill, in dark ink, when the bar is too short to hold it', () => {
    render(<BarList items={items} />);
    const texto = screen.getByText(largo);
    expect(texto).toHaveAttribute('data-label', 'outside');
    expect(texto).toHaveStyle({ color: '#3D3D3A' });
  });

  it('moves it to the sub-line when it fits neither inside nor outside', () => {
    render(<BarList items={[{ name: 'Beta', value: 45, valueText: largo, sub: 'Cali' }, { name: 'Alfa', value: 100, valueText: '$9 M' }]} trackWidth={180} />);
    expect(screen.getByText(`${largo} · Cali`)).toBeInTheDocument();
    expect(screen.queryByText(largo)).toBeNull();
  });
});

describe('Scatter label collisions', () => {
  it('keeps crowded labels apart and clear of the corner caption', () => {
    const pts = [
      { id: 'a', x: 90, y: 80, r: 6, label: 'Bogotá Av. Boyacá' },
      { id: 'b', x: 91, y: 79, r: 6, label: 'Cali Cra 1 Dos' },
      { id: 'c', x: 98, y: 97, r: 6, label: 'Bogotá Bosa' },
    ];
    render(<Scatter points={pts} xDomain={[0, 100]} yDomain={[0, 100]} highlight={['a', 'b', 'c']} cornerLabels={{ topRight: 'Alta venta · alto margen' }} />);
    const caja = (id) => {
      const el = screen.queryByTestId(`point-label-${id}`);
      if (!el) return null;
      return { left: parseFloat(el.style.left) * 6, top: parseFloat(el.style.top) * 3.2, w: el.textContent.length * 6, h: 14 };
    };
    const cajas = ['a', 'b', 'c'].map(caja).filter(Boolean);
    expect(cajas.length).toBeGreaterThanOrEqual(2);
    const esquina = { left: 600 - 26 - 24 * 6, top: 22, w: 24 * 6, h: 14 };
    cajas.forEach((c, i) => {
      const choca = (p, q) => p.left < q.left + q.w && q.left < p.left + p.w && p.top < q.top + q.h && q.top < p.top + p.h;
      expect(choca(c, esquina)).toBe(false);
      cajas.slice(i + 1).forEach((o) => expect(choca(c, o)).toBe(false));
    });
  });
});

describe('SegmentedToggle', () => {
  const options = [{ id: 'semaforo', label: 'Semáforo' }, { id: 'barras', label: 'Barras' }];

  it('marks the active option and reports changes', () => {
    const onChange = jest.fn();
    render(<SegmentedToggle options={options} value="semaforo" onChange={onChange} ariaLabel="Vista" />);
    expect(screen.getByRole('group', { name: 'Vista' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Semáforo' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Barras' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'Barras' }));
    expect(onChange).toHaveBeenCalledWith('barras');
  });

  it('keeps a 36px touch target', () => {
    render(<SegmentedToggle options={options} value="barras" onChange={() => {}} />);
    expect(screen.getByRole('button', { name: 'Barras' })).toHaveStyle({ minHeight: '36px' });
  });
});

describe('KpiMiniGrid', () => {
  it('shows label, value and a chip with its variant', () => {
    render(
      <KpiMiniGrid items={[
        { label: 'Mayor ticket', value: '$167.655', chip: '2x la red', chipVariant: 'up' },
        { label: 'Margen red', value: '27,1%', chip: 'ene-ago', chipVariant: 'flat' },
        { label: 'Sin chip', value: '1' },
      ]}
      />,
    );
    expect(screen.getByText('Mayor ticket')).toBeInTheDocument();
    expect(screen.getByText('$167.655')).toBeInTheDocument();
    expect(screen.getByText('2x la red')).toHaveAttribute('data-variant', 'up');
    expect(screen.getByText('ene-ago')).toHaveAttribute('data-variant', 'flat');
  });
});

describe('TrafficLightGrid', () => {
  const items = [
    { id: 1, name: 'Bogotá 1 de Mayo Dos', pct: 1.414 },
    { id: 2, name: 'Pereira', pct: 0.899 },
    { id: 3, name: 'Armenia', pct: 0.001 },
    { id: 4, name: 'Sin presupuesto', pct: null },
  ];

  it('colors each store by the semaforo and shows its percentage', () => {
    render(<TrafficLightGrid items={items} cortes={CORTES} />);
    const cells = screen.getAllByTestId('traffic-cell');
    expect(cells.map((c) => c.getAttribute('data-tone'))).toEqual(['good', 'mid', 'bad', 'none']);
    expect(screen.getByText('141,4%')).toBeInTheDocument();
    expect(screen.getByText('89,9%')).toBeInTheDocument();
    expect(screen.getByText('Pereira')).toHaveStyle({ textOverflow: 'ellipsis' });
  });
});
