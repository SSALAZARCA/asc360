import { COLOR } from '../tokens';
import Chip from './Chip';

/** Two-column grid of small figures. `items` [{label, value, chip, chipVariant: up|down|flat}]. */
export default function KpiMiniGrid({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
      {items.map((item) => (
        <div key={item.key ?? item.label} style={{ background: COLOR.wash, borderRadius: 10, padding: '10px 12px', minWidth: 0 }}>
          <p style={{ margin: 0, fontSize: 11.5, fontWeight: 500, letterSpacing: '.04em', textTransform: 'uppercase', color: COLOR.muted }}>{item.label}</p>
          <p style={{ margin: '4px 0 6px', fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{item.value}</p>
          {item.chip && <Chip text={item.chip} variant={item.chipVariant} />}
        </div>
      ))}
    </div>
  );
}
