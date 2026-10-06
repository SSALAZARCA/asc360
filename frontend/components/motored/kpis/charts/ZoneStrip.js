import { COLOR } from '../tokens';
import { zoneStripLayout } from './geometry';

/**
 * "Where each one falls": a colored lane (`zones` [{hasta, bg}]) with vertical `lines`, one dot per item
 * (`dots` [{value, color, tip}], stacked when they collide) and the axis `ticks` [{value, label, strong}].
 * `highlight` {value, label, color, tip} draws one bigger dot on the lane with a label above it (the asesor
 * of the single view among the others).
 */
const posicion = (valor, min, max) => `${(Math.min(Math.max((valor - min) / (max - min), 0), 1) * 100).toFixed(2)}%`;

function Destacado({ highlight, min, max }) {
  const left = posicion(highlight.value, min, max);
  const color = highlight.color || COLOR.info;
  return (
    <>
      <span
        title={highlight.tip} data-testid="strip-highlight"
        style={{
          position: 'absolute', left, top: 29, width: 18, height: 18, marginLeft: -9, borderRadius: 999, background: color,
          border: '3px solid #FFFFFF', boxShadow: `0 0 0 2px ${color}`, boxSizing: 'border-box',
        }}
      />
      <span
        style={{
          position: 'absolute', left, top: -22, transform: 'translateX(-50%)', whiteSpace: 'nowrap', fontSize: 12, fontWeight: 700,
          color: '#FFFFFF', background: color, borderRadius: 6, padding: '3px 8px',
        }}
      >
        {highlight.label}
      </span>
    </>
  );
}

export default function ZoneStrip({ dots, min, max, zones, lines, ticks, highlight, ariaLabel = 'Distribución' }) {
  const layout = zoneStripLayout({ dots, min, max, zones, lines, ticks });
  return (
    <div role="img" aria-label={ariaLabel}>
      <div style={{ position: 'relative', marginTop: highlight ? 34 : 22, height: 76 }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: 28, height: 20, display: 'flex', borderRadius: 6, overflow: 'hidden' }}>
          {layout.zones.map((z, i) => (
            <div key={i} style={{ width: `${z.widthPct}%`, background: z.bg }} />
          ))}
        </div>
        {layout.lines.map((left, i) => (
          <span key={i} style={{ position: 'absolute', left: `${left}%`, top: 18, bottom: 18, width: 2, marginLeft: -1, background: COLOR.ink }} />
        ))}
        {layout.dots.map((d, i) => (
          <span
            key={i} title={d.tip} data-level={d.level}
            style={{
              position: 'absolute', left: `${d.leftPct}%`, top: d.top, width: 12, height: 12, marginLeft: -6, borderRadius: 999,
              background: d.color, border: '2px solid #FFFFFF', boxShadow: '0 0 0 1px rgba(0,0,0,.15)',
            }}
          />
        ))}
        {highlight && <Destacado highlight={highlight} min={min} max={max} />}
      </div>
      <div style={{ position: 'relative', height: 16, fontSize: 11, color: COLOR.soft }}>
        {layout.ticks.map((t, i) => (
          <span
            key={i}
            style={{
              position: 'absolute', left: `${t.leftPct}%`, transform: t.transform,
              color: t.strong ? COLOR.ink : COLOR.soft, fontWeight: t.strong ? 700 : 500,
            }}
          >
            {t.label}
          </span>
        ))}
      </div>
    </div>
  );
}
