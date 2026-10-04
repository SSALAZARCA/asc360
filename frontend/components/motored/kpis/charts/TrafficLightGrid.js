import { pct } from '../format';
import { COLOR, TONO } from '../tokens';
import { semaforoTone } from './geometry';

function Celda({ item, cortes }) {
  const tone = semaforoTone(Number.isFinite(item.pct) ? item.pct * 100 : null, cortes);
  const t = TONO[tone];
  return (
    <div
      data-testid="traffic-cell" data-tone={tone} title={`${item.name}: ${pct(item.pct)}${item.detail ? ` · ${item.detail}` : ''}`}
      style={{ display: 'flex', alignItems: 'center', gap: 10, background: t.soft, borderRadius: 10, padding: '10px 12px', minWidth: 0 }}
    >
      <span style={{ width: 14, height: 14, borderRadius: 999, background: t.color, boxShadow: `0 0 0 4px ${t.ring}`, flex: 'none' }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: 'block', fontSize: 12.5, fontWeight: 500, color: COLOR.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {item.name}
        </span>
        {item.detail && <span style={{ display: 'block', fontSize: 10.5, color: COLOR.muted }}>{item.detail}</span>}
      </span>
      <strong style={{ fontSize: 14, color: t.ink, fontVariantNumeric: 'tabular-nums' }}>{pct(item.pct)}</strong>
    </div>
  );
}

/** The "Semáforo" grid. `items` [{id, name, pct (fraction or null), detail}]; color by `cortes` {verde_desde, ambar_desde}. */
export default function TrafficLightGrid({ items, cortes }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
      {items.map((item) => <Celda key={item.id ?? item.name} item={item} cortes={cortes} />)}
    </div>
  );
}
