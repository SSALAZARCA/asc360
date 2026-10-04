import { COLOR } from '../tokens';

const CAJA = { width: 600, height: 320, padL: 52, padR: 20, padT: 16, padB: 40 };

const finito = (v) => Number.isFinite(v);

/** A usable [min, max]: the given one, or the points' extent; never zero-width or non-finite. */
function dominio(dado, valores) {
  const base = Array.isArray(dado) && dado.every(finito) ? dado : valores.length ? [Math.min(...valores), Math.max(...valores)] : [0, 1];
  return base[0] === base[1] ? [base[0] - 1, base[1] + 1] : base;
}

function escalas(xDomain, yDomain) {
  const { width, height, padL, padR, padT, padB } = CAJA;
  return {
    x: (v) => padL + ((v - xDomain[0]) / (xDomain[1] - xDomain[0])) * (width - padL - padR),
    y: (v) => height - padB - ((v - yDomain[0]) / (yDomain[1] - yDomain[0])) * (height - padT - padB),
  };
}

const porCien = (valor, total) => `${((valor / total) * 100).toFixed(2)}%`;

/**
 * x/y scatter with optional quadrant lines. `points` [{id, x, y, r, color, tip}]; only `highlight` ids get a label.
 * Axis titles and labels are HTML overlays; dots and lines are SVG (the box keeps its aspect ratio, so dots stay round).
 */
export default function Scatter({ points, xDomain, yDomain, quadrant, xLabel, yLabel, highlight = [], ariaLabel = 'Dispersión' }) {
  const { x, y } = escalas(dominio(xDomain, points.map((p) => p.x).filter(finito)), dominio(yDomain, points.map((p) => p.y).filter(finito)));
  const { width, height, padL, padR, padT, padB } = CAJA;
  return (
    <div role="img" aria-label={ariaLabel} style={{ position: 'relative', width: '100%', aspectRatio: `${width} / ${height}` }}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="100%" aria-hidden="true" focusable="false" style={{ display: 'block' }}>
        <rect x={padL} y={padT} width={width - padL - padR} height={height - padT - padB} fill="none" strokeWidth="1" style={{ stroke: COLOR.track }} />
        {quadrant?.x !== undefined && <line data-quadrant="x" x1={x(quadrant.x)} x2={x(quadrant.x)} y1={padT} y2={height - padB} strokeDasharray="4 4" style={{ stroke: COLOR.gray400 }} />}
        {quadrant?.y !== undefined && <line data-quadrant="y" x1={padL} x2={width - padR} y1={y(quadrant.y)} y2={y(quadrant.y)} strokeDasharray="4 4" style={{ stroke: COLOR.gray400 }} />}
        {points.map((p) => (
          <circle key={p.id} data-point={p.id} cx={x(p.x)} cy={y(p.y)} r={p.r || 5} strokeWidth="1.5" style={{ fill: p.color || COLOR.info, stroke: '#FFFFFF', fillOpacity: 0.9 }}>
            <title>{p.tip}</title>
          </circle>
        ))}
      </svg>
      {points.filter((p) => highlight.includes(p.id)).map((p) => (
        <span
          key={p.id} data-testid={`point-label-${p.id}`}
          style={{ position: 'absolute', left: porCien(x(p.x) + (p.r || 5) + 3, width), top: porCien(y(p.y), height), transform: 'translateY(-50%)', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', color: COLOR.ink }}
        >
          {p.tip}
        </span>
      ))}
      {xLabel && <span style={{ position: 'absolute', left: '50%', bottom: 0, transform: 'translateX(-50%)', fontSize: 11.5, color: COLOR.muted }}>{xLabel}</span>}
      {yLabel && <span style={{ position: 'absolute', left: 0, top: 0, fontSize: 11.5, color: COLOR.muted }}>{yLabel}</span>}
    </div>
  );
}
