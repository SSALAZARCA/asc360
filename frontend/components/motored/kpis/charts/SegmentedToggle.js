import { COLOR } from '../tokens';

/** "Semáforo | Barras" selector. `options` [{id, label}], `value` the active id, `onChange(id)`. */
export default function SegmentedToggle({ options, value, onChange, ariaLabel = 'Vista' }) {
  return (
    <div role="group" aria-label={ariaLabel} style={{ display: 'inline-flex', background: COLOR.wash, borderRadius: 10, padding: 3 }}>
      {options.map((o) => {
        const activo = o.id === value;
        return (
          <button
            key={o.id} type="button" aria-pressed={activo} onClick={() => onChange(o.id)}
            style={{
              appearance: 'none', border: 0, fontFamily: 'inherit', fontSize: 12.5, fontWeight: 700, padding: '8px 14px',
              minHeight: 36, borderRadius: 8, cursor: 'pointer',
              ...(activo ? { background: COLOR.surface, color: COLOR.ink, boxShadow: '0 1px 2px rgba(0,0,0,.12)' } : { background: 'transparent', color: COLOR.muted }),
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
