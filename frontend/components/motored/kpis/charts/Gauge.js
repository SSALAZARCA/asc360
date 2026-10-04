import { pct } from '../format';
import { COLOR, TONO } from '../tokens';
import { gaugeGeometry, semaforoTone } from './geometry';

/**
 * Semicircle gauge with a needle. `value` is a fraction (0.78 = 78%), `cortes` the semaforo cuts in
 * percentage points ({verde_desde, ambar_desde}); `label` goes below ("$1.554 M de $1.993 M").
 */
const aFraccion = (v) => (v === null || v === undefined || v === '' || typeof v === 'boolean' || !Number.isFinite(Number(v)) ? null : Number(v));

export default function Gauge({ value: crudo, cortes, title = 'Cumplimiento', label = '', maxWidth = 260 }) {
  const value = aFraccion(crudo);
  const tone = semaforoTone(value === null ? null : value * 100, cortes);
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
        {[['10%', '0'], ['90%', '100%']].map(([left, texto]) => (
          <span key={texto} style={{ position: 'absolute', left, top: '88%', transform: 'translateX(-50%)', fontSize: 10, color: COLOR.soft }}>{texto}</span>
        ))}
      </div>
      <p style={{ margin: 0, fontSize: 30, fontWeight: 700, letterSpacing: '-.01em', color: COLOR.ink, fontVariantNumeric: 'tabular-nums' }}>{texto}</p>
      {label && <p style={{ margin: '8px 0 0', fontSize: 12.5, color: COLOR.muted }}>{label}</p>}
    </div>
  );
}
