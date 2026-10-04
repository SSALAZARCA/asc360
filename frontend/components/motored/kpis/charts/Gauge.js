import { pct } from '../format';
import { COLOR, TONO } from '../tokens';
import { gaugeGeometry, semaforoTone } from './geometry';

/**
 * Semicircle gauge with a needle. `value` is a fraction (0.78 = 78%), `cortes` the semaforo cuts in
 * percentage points ({verde_desde, ambar_desde}); `label` goes below ("$1.554 M de $1.993 M").
 */
export default function Gauge({ value, cortes, title = 'Cumplimiento', label = '', maxWidth = 260 }) {
  const tone = semaforoTone(Number.isFinite(value) ? value * 100 : null, cortes);
  const g = gaugeGeometry(value);
  const texto = pct(value);
  const resumen = [`${title}: ${texto}`, label].filter(Boolean).join('. ');
  return (
    <div style={{ width: '100%', maxWidth, margin: '0 auto', textAlign: 'center' }}>
      <div role="img" aria-label={resumen} data-tone={tone} style={{ position: 'relative' }}>
        <svg viewBox="0 0 200 120" width="100%" aria-hidden="true" focusable="false" style={{ display: 'block' }}>
          <path d="M20 104 A80 80 0 0 1 180 104" fill="none" strokeWidth="18" strokeLinecap="round" style={{ stroke: COLOR.track }} />
          {g.ratio > 0 && (
            <path
              d="M20 104 A80 80 0 0 1 180 104" fill="none" strokeWidth="18" strokeLinecap="round"
              strokeDasharray={`${g.dash.toFixed(1)} ${g.arc.toFixed(1)}`} style={{ stroke: TONO[tone].color }}
            />
          )}
          <line x1="100" y1="104" x2={g.needleX} y2={g.needleY} strokeWidth="3" strokeLinecap="round" style={{ stroke: COLOR.ink }} />
          <circle cx="100" cy="104" r="5" style={{ fill: COLOR.ink }} />
        </svg>
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: '-2%', fontSize: 28, fontWeight: 700, color: COLOR.ink }}>
          {texto}
        </div>
      </div>
      {label && <p style={{ margin: '14px 0 0', fontSize: 12.5, color: COLOR.muted }}>{label}</p>}
    </div>
  );
}
