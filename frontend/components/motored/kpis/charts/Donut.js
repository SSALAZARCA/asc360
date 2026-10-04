import { miles, pct } from '../format';
import { COLOR } from '../tokens';
import { donutSegments, shares } from './geometry';

const RADIO = 66;

function Leyenda({ items, formatValue }) {
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minWidth: 140 }}>
      {items.map((item) => (
        <li key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span style={{ width: 10, height: 10, borderRadius: 999, background: item.color, flex: 'none' }} />
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</span>
          <strong style={{ fontVariantNumeric: 'tabular-nums' }}>{formatValue(item.value)}</strong>
          <span style={{ color: COLOR.muted, fontVariantNumeric: 'tabular-nums', minWidth: 44, textAlign: 'right' }}>
            {pct(item.fraction)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Donut of `segments` [{label, value, color}] with a title/subtitle in the centre and an optional legend. */
export default function Donut({ segments, centerTitle, centerSubtitle, legend = false, formatValue = miles, size = 160 }) {
  const items = shares(segments);
  const resumen = items.map((s) => `${s.label} ${formatValue(s.value)} (${pct(s.fraction)})`).join(', ');
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 20 }}>
      <div role="img" aria-label={`Distribución: ${resumen}`} style={{ position: 'relative', width: size, maxWidth: '100%', flex: 'none' }}>
        <svg viewBox="0 0 180 180" width="100%" aria-hidden="true" focusable="false" style={{ display: 'block' }}>
          <circle cx="90" cy="90" r={RADIO} fill="none" strokeWidth="26" style={{ stroke: COLOR.wash }} />
          <g transform="rotate(-90 90 90)">
            {donutSegments(segments, RADIO).map((s) => (
              <circle
                key={s.label} data-segment={s.label} cx="90" cy="90" r={RADIO} fill="none" strokeWidth="26"
                strokeDasharray={`${s.len.toFixed(2)} ${s.gap.toFixed(2)}`} strokeDashoffset={s.offset.toFixed(2)}
                style={{ stroke: s.color }}
              >
                <title>{`${s.label} ${formatValue(s.value)} (${pct(s.fraction)})`}</title>
              </circle>
            ))}
          </g>
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          {centerTitle && <span style={{ fontSize: 22, fontWeight: 700, color: COLOR.ink }}>{centerTitle}</span>}
          {centerSubtitle && <span style={{ fontSize: 11.5, color: COLOR.muted }}>{centerSubtitle}</span>}
        </div>
      </div>
      {legend && <Leyenda items={items} formatValue={formatValue} />}
    </div>
  );
}
