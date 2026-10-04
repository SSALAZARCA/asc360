import {
  barPlacement, donutSegments, gaugeGeometry, heatLevel, heatRows, niceMax, semaforoTone,
  squarify, stackLevels, stackTop, stackedAreaGeometry, zoneStripLayout,
} from '../components/motored/kpis/charts/geometry';
import {
  decimales, millones, miles, moneda, pct, pctSigned,
} from '../components/motored/kpis/format';

describe('KPI format helpers (es-CO)', () => {
  it('groups thousands with a dot and uses a comma for decimals', () => {
    expect(miles(1554)).toBe('1.554');
    expect(miles(999)).toBe('999');
    expect(miles(1234567.6)).toBe('1.234.568');
    expect(decimales(1554.25, 1)).toBe('1.554,3');
    expect(decimales(7.7, 2)).toBe('7,70');
  });

  it('writes pesos in the millions style', () => {
    expect(millones(1554000000)).toBe('$1.554 M');
    expect(millones(32000000, 1)).toBe('$32,0 M');
    expect(moneda(85615)).toBe('$85.615');
  });

  it('writes percentages and signed variations', () => {
    expect(pct(0.0769)).toBe('7,7%');
    expect(pct(0.78, 0)).toBe('78%');
    expect(pctSigned(0.077)).toBe('+7,7%');
    expect(pctSigned(-0.032)).toBe('−3,2%');
  });

  it('shows a dash for missing values, never zero', () => {
    expect(miles(null)).toBe('—');
    expect(pct(undefined)).toBe('—');
    expect(millones(NaN)).toBe('—');
  });
});

describe('gaugeGeometry', () => {
  it('places the needle on the semicircle', () => {
    expect(gaugeGeometry(0)).toMatchObject({ needleX: 38, needleY: 104 });
    expect(gaugeGeometry(0.5)).toMatchObject({ needleX: 100, needleY: 42 });
    expect(gaugeGeometry(1)).toMatchObject({ needleX: 162, needleY: 104 });
  });

  it('clamps out-of-range values and sizes the arc dash', () => {
    const arc = Math.PI * 80;
    expect(gaugeGeometry(2).ratio).toBe(1);
    expect(gaugeGeometry(-1).ratio).toBe(0);
    expect(gaugeGeometry(0.78).dash).toBeCloseTo(0.78 * arc, 5);
    expect(gaugeGeometry(0.78).arc).toBeCloseTo(arc, 5);
  });
});

describe('semaforoTone', () => {
  const cortes = { verde_desde: 90, ambar_desde: 70 };

  it('cuts at the configured thresholds, inclusive', () => {
    expect(semaforoTone(90, cortes)).toBe('good');
    expect(semaforoTone(89.9, cortes)).toBe('mid');
    expect(semaforoTone(70, cortes)).toBe('mid');
    expect(semaforoTone(69.9, cortes)).toBe('bad');
    expect(semaforoTone(null, cortes)).toBe('none');
    expect(semaforoTone(NaN, cortes)).toBe('none');
  });

  it('falls back to 90/70 without cuts', () => {
    expect(semaforoTone(95)).toBe('good');
    expect(semaforoTone(75)).toBe('mid');
  });
});

describe('donutSegments', () => {
  it('splits the circumference in proportion to the values', () => {
    const c = 2 * Math.PI * 66;
    const segs = donutSegments([{ value: 3 }, { value: 1 }]);
    expect(segs[0].len).toBeCloseTo(c * 0.75, 5);
    expect(segs[1].len).toBeCloseTo(c * 0.25, 5);
    expect(segs[0].offset).toBeCloseTo(0, 5);
    expect(segs[1].offset).toBeCloseTo(-c * 0.75, 5);
    expect(segs[0].fraction).toBe(0.75);
  });

  it('returns no segments when everything is zero', () => {
    expect(donutSegments([{ value: 0 }, { value: 0 }])).toEqual([]);
    expect(donutSegments([])).toEqual([]);
  });
});

describe('barPlacement', () => {
  it('puts the value inside from 20% of width', () => {
    expect(barPlacement(20)).toBe('inside');
    expect(barPlacement(80)).toBe('inside');
    expect(barPlacement(19.9)).toBe('outside');
    expect(barPlacement(22, 22)).toBe('inside');
    expect(barPlacement(21, 22)).toBe('outside');
  });
});

describe('zone strip stacking', () => {
  it('stacks colliding dots deterministically above and below the lane', () => {
    expect(stackLevels([10, 10, 10, 10])).toEqual([0, 1, 2, 3]);
    expect([0, 1, 2, 3, 4].map(stackTop)).toEqual([32, 18, 46, 4, 60]);
  });

  it('stacks values on a slot edge the same way whatever float noise they carry', () => {
    // 2.1 / 1.4 = 1.5000000000000002 while 0.7 / 1.4 = 0.5: both sit on a bucket edge
    expect(stackLevels([2.1, 2.1000000000000001, 2.1])).toEqual([0, 1, 2]);
    expect(stackLevels([0.7, 0.70000000001])).toEqual([0, 1]);
    expect(stackLevels([2.1, 2.09999999999])).toEqual([0, 1]);
  });

  it('keeps separated dots on the lane', () => {
    expect(stackLevels([0, 50, 100])).toEqual([0, 0, 0]);
  });

  it('lays out zones, lines, ticks and dots on a 0-150 axis', () => {
    const layout = zoneStripLayout({
      dots: [{ value: 75, color: '#111', tip: 'a' }, { value: 75, color: '#222', tip: 'b' }, { value: 400, color: '#333', tip: 'c' }],
      min: 0,
      max: 150,
      zones: [{ hasta: 70, bg: '#a' }, { hasta: 90, bg: '#b' }, { hasta: 150, bg: '#c' }],
      lines: [70, 90],
      ticks: [{ value: 0, label: '0%' }, { value: 90, label: '90%', strong: true }, { value: 150, label: '150%+' }],
    });
    expect(layout.zones.map((z) => z.widthPct)).toEqual([46.67, 13.33, 40]);
    expect(layout.zones.reduce((s, z) => s + z.widthPct, 0)).toBeCloseTo(100, 5);
    expect(layout.lines).toEqual([46.67, 60]);
    expect(layout.dots.map((d) => d.leftPct)).toEqual([50, 50, 100]);
    expect(layout.dots.map((d) => d.top)).toEqual([32, 18, 32]);
    expect(layout.ticks.map((t) => t.transform)).toEqual(['none', 'translateX(-50%)', 'translateX(-100%)']);
  });
});

describe('heatLevel', () => {
  it.each([
    [1.3, 1], [1.15, 1], [1.149, 2], [1.05, 2], [1.049, 3], [1, 3], [0.95, 3],
    [0.949, 4], [0.85, 4], [0.849, 5], [0.75, 5], [0.749, 6], [0.1, 6],
  ])('ratio %s is level %i', (ratio, level) => {
    expect(heatLevel(ratio).level).toBe(level);
  });

  it('treats a missing or non-finite ratio as no data instead of crashing', () => {
    expect(heatLevel(undefined).level).toBeNull();
    expect(heatLevel(NaN).level).toBeNull();
  });

  it('uses white text on the two solid levels only', () => {
    expect(heatLevel(1.5).fg).toBe('#FFFFFF');
    expect(heatLevel(0.2).fg).toBe('#FFFFFF');
    expect(heatLevel(1).fg).not.toBe('#FFFFFF');
  });

  it('compares every cell with the average of the row own active months', () => {
    const [row] = heatRows([{ name: 'A', values: [100, 100, 100, 0, null, 160] }]);
    // average of 100,100,100,160 = 115 -> 160/115 = 1.39 (level 1), 100/115 = 0.87 (level 4)
    expect(row.cells.map((c) => c.level)).toEqual([4, 4, 4, null, null, 1]);
    expect(row.cells[3].value).toBeNull();
  });
});

describe('squarify', () => {
  const items = [{ id: 'a', value: 60 }, { id: 'b', value: 25 }, { id: 'c', value: 10 }, { id: 'd', value: 5 }];

  it('fills the box with tiles whose area is proportional to the value', () => {
    const tiles = squarify(items, 200, 100);
    const area = (t) => t.w * t.h;
    expect(tiles.reduce((s, t) => s + area(t), 0)).toBeCloseTo(200 * 100, 4);
    tiles.forEach((t, i) => expect(area(t) / (200 * 100)).toBeCloseTo(items[i].value / 100, 6));
  });

  it('keeps every tile inside the box and drops non-positive values', () => {
    const tiles = squarify([...items, { id: 'z', value: 0 }, { id: 'n', value: -3 }], 200, 100);
    expect(tiles).toHaveLength(4);
    tiles.forEach((t) => {
      expect(t.x).toBeGreaterThanOrEqual(-1e-9);
      expect(t.y).toBeGreaterThanOrEqual(-1e-9);
      expect(t.x + t.w).toBeLessThanOrEqual(200 + 1e-9);
      expect(t.y + t.h).toBeLessThanOrEqual(100 + 1e-9);
    });
  });

  it('is deterministic', () => {
    expect(squarify(items, 200, 100)).toEqual(squarify(items, 200, 100));
  });
});

describe('stacked area geometry', () => {
  const series = [
    { name: 'A', color: '#1', values: [100, 200, 300] },
    { name: 'B', color: '#2', values: [50, 50, 100] },
  ];

  it('rounds the axis up to a readable maximum', () => {
    expect(niceMax(1871.9)).toBe(2000);
    expect(niceMax(400)).toBe(400);
    expect(niceMax(0)).toBeGreaterThan(0);
    expect(niceMax(NaN)).toBeGreaterThan(0);
  });

  it('stacks the series and reports the total of every month', () => {
    const g = stackedAreaGeometry(series, 3);
    expect(g.totals.map((t) => t.value)).toEqual([150, 250, 400]);
    expect(g.layers).toHaveLength(2);
    expect(g.layers[0].path.startsWith('M')).toBe(true);
    expect(g.grid.map((x) => x.value)).toEqual([0, 100, 200, 300, 400]);
    expect(g.totals[0].leftPct).toBeLessThan(g.totals[2].leftPct);
  });
});
