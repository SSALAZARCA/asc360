import { pct } from '../format';
import { COLOR, CATEGORIA } from '../tokens';
import { shares, stackedAreaGeometry } from './geometry';
import { ShareTiles } from './ShareTiles';

const ETIQUETA = { position: 'absolute', transform: 'translateX(-50%)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' };

function Leyenda({ series }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 12, color: COLOR.muted, marginTop: 8 }}>
      {series.map((s) => (
        <span key={s.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 999, background: s.color }} />
          {s.name}
        </span>
      ))}
    </div>
  );
}

function Etiquetas({ geometry, months, formatValue }) {
  return (
    <>
      {geometry.grid.map((g) => (
        <span key={g.value} style={{ position: 'absolute', left: 0, top: `${g.topPct}%`, transform: 'translateY(-50%)', fontSize: 10.5, color: COLOR.soft }}>
          {g.value === 0 ? '0' : formatValue(g.value)}
        </span>
      ))}
      {geometry.totals.map((t, i) => (
        <span key={`t${i}`} data-testid="area-total" style={{ ...ETIQUETA, left: `${t.leftPct}%`, top: `${t.topPct}%`, color: COLOR.ink }}>{formatValue(t.value)}</span>
      ))}
      {months.map((m, i) => (
        <span key={`m${i}`} style={{ ...ETIQUETA, left: `${geometry.xs[i]}%`, top: '93%', fontWeight: 500, color: COLOR.soft }}>{m}</span>
      ))}
    </>
  );
}

/**
 * Months x series stacked area. `series` [{name, color, values[]}] (default blue scale), `months` labels.
 * Totals, months and the y grid are HTML overlays (dynamic SVG text distorts when the box scales).
 */
export default function StackedArea({ months, series, formatValue = String, showLegend = true, showTiles = false }) {
  const pintadas = series.map((s, i) => ({ ...s, color: s.color || CATEGORIA[i % CATEGORIA.length] }));
  const g = stackedAreaGeometry(pintadas, months.length);
  const items = pintadas.map((s) => ({ name: s.name, color: s.color, value: s.values.reduce((a, b) => a + (b || 0), 0) }));
  const resumen = shares(items).map((s) => `${s.name} ${pct(s.fraction)}`).join(', ');
  return (
    <div>
      <div role="img" aria-label={`Evolución mensual por serie: ${resumen}`} style={{ position: 'relative', width: '100%', aspectRatio: `${g.width} / ${g.height}` }}>
        <svg viewBox={`0 0 ${g.width} ${g.height}`} width="100%" height="100%" aria-hidden="true" focusable="false" style={{ display: 'block' }}>
          {g.grid.map((l) => (
            <line key={l.value} x1={g.padL} x2={g.width - g.padR} y1={l.y} y2={l.y} strokeWidth="1" style={{ stroke: COLOR.track }} />
          ))}
          {g.layers.map((l) => (
            <path key={l.name} data-series={l.name} d={l.path} style={{ fill: l.color, stroke: '#FFFFFF', strokeWidth: 1 }} />
          ))}
        </svg>
        <Etiquetas geometry={g} months={months} formatValue={formatValue} />
      </div>
      {showLegend && <Leyenda series={pintadas} />}
      {showTiles && <div style={{ marginTop: 12 }}><ShareTiles items={items.map((i) => ({ ...i, valueText: formatValue(i.value) }))} /></div>}
    </div>
  );
}
