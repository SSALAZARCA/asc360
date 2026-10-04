import { pct } from '../format';
import { COLOR } from '../tokens';
import { shares } from './geometry';

/** Tiles with the share (%) and the value of each item. `items` [{name, value, color, valueText}]. */
export function ShareTiles({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8 }}>
      {shares(items).map((item) => (
        <div key={item.name} style={{ background: COLOR.wash, borderRadius: 10, padding: '10px 12px', minWidth: 0 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: COLOR.muted }}>
            <span style={{ width: 10, height: 10, borderRadius: 999, background: item.color, flex: 'none' }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
          </span>
          <strong style={{ display: 'block', fontSize: 18, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>{pct(item.fraction)}</strong>
          {item.valueText && <span style={{ fontSize: 12, color: COLOR.muted }}>{item.valueText}</span>}
        </div>
      ))}
    </div>
  );
}

/** A single horizontal bar of 100% split in `segments` [{label, value, color}]; tooltips carry the share. */
export function StackedBar100({ segments, height = 22 }) {
  const items = shares(segments);
  const resumen = items.map((s) => `${s.label} ${pct(s.fraction)}`).join(', ');
  return (
    <div role="img" aria-label={resumen} style={{ display: 'flex', height, borderRadius: 6, overflow: 'hidden', background: COLOR.wash }}>
      {items.filter((s) => s.fraction > 0).map((s) => (
        <div
          key={s.label} data-testid="segment" data-width={Number((s.fraction * 100).toFixed(2))}
          title={`${s.label} ${pct(s.fraction)}`} style={{ width: `${s.fraction * 100}%`, background: s.color }}
        />
      ))}
    </div>
  );
}
