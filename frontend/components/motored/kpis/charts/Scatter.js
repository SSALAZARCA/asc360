import { COLOR } from '../tokens';
import { placeLabels } from './geometry';

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

const TICK = { position: 'absolute', whiteSpace: 'nowrap', fontSize: 10.5, color: COLOR.soft, fontVariantNumeric: 'tabular-nums' };
const ESQUINA = { position: 'absolute', fontSize: 11, fontWeight: 700 };

const LINEA = 14;
const CHAR_PX = 6;

/** Reserved boxes of the corner captions, in chart units, so point labels never cover them. */
function cajasEsquina(corner) {
  const { width, height, padL, padR, padT, padB } = CAJA;
  const cajas = [];
  if (corner?.topRight) { const w = corner.topRight.length * CHAR_PX; cajas.push({ left: width - padR - 6 - w, top: padT + 6, w, h: LINEA }); }
  if (corner?.bottomLeft) cajas.push({ left: padL + 6, top: height - padB - 6 - LINEA, w: corner.bottomLeft.length * CHAR_PX, h: LINEA });
  return cajas;
}

function Ejes({ x, y, xTicks, yTicks, corner }) {
  const { width, height, padL, padR, padT, padB } = CAJA;
  return (
    <>
      {yTicks.map((t) => (
        <span key={`y${t.value}`} style={{ ...TICK, left: 0, width: porCien(padL - 6, width), textAlign: 'right', top: porCien(y(t.value), height), transform: 'translateY(-50%)' }}>{t.label}</span>
      ))}
      {xTicks.map((t) => (
        <span key={`x${t.value}`} style={{ ...TICK, left: porCien(x(t.value), width), top: porCien(height - padB + 6, height), transform: 'translateX(-50%)' }}>{t.label}</span>
      ))}
      {corner?.topRight && <span style={{ ...ESQUINA, right: porCien(padR + 6, width), top: porCien(padT + 6, height), color: COLOR.goodInk }}>{corner.topRight}</span>}
      {corner?.bottomLeft && <span style={{ ...ESQUINA, left: porCien(padL + 6, width), bottom: porCien(padB + 6, height), color: COLOR.badInk }}>{corner.bottomLeft}</span>}
    </>
  );
}

/**
 * x/y scatter with optional quadrant lines. `points` [{id, x, y, r, color, tip, label}]; only `highlight` ids get a
 * label (`label`, or `tip` when absent). `xTicks`/`yTicks` [{value, label}] and `cornerLabels` {topRight, bottomLeft}
 * are optional. Axis titles and labels are HTML overlays; dots and lines are SVG (the box keeps its aspect ratio, so dots stay round).
 */
export default function Scatter({
  points, xDomain, yDomain, quadrant, xLabel, yLabel, xTicks = [], yTicks = [], cornerLabels, highlight = [], ariaLabel = 'Dispersión',
}) {
  const { x, y } = escalas(dominio(xDomain, points.map((p) => p.x).filter(finito)), dominio(yDomain, points.map((p) => p.y).filter(finito)));
  const { width, height, padL, padR, padT, padB } = CAJA;
  const sitios = placeLabels({
    labels: points.filter((p) => highlight.includes(p.id)).map((p) => ({ id: p.id, cx: x(p.x), cy: y(p.y), r: p.r || 5, text: p.label ?? p.tip })),
    dots: points.map((p) => ({ cx: x(p.x), cy: y(p.y), r: p.r || 5 })),
    obstacles: cajasEsquina(cornerLabels),
    bounds: { x: padL, y: padT, w: width - padL - padR, h: height - padT - padB },
  });
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
      {points.filter((p) => highlight.includes(p.id) && sitios[p.id]).map((p) => (
        <span
          key={p.id} data-testid={`point-label-${p.id}`}
          style={{
            position: 'absolute', left: porCien(sitios[p.id].left, width), top: porCien(sitios[p.id].top, height), height: porCien(LINEA, height),
            lineHeight: `${LINEA}px`, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', color: COLOR.ink,
          }}
        >
          {p.label ?? p.tip}
        </span>
      ))}
      <Ejes x={x} y={y} xTicks={xTicks} yTicks={yTicks} corner={cornerLabels} />
      {xLabel && <span style={{ position: 'absolute', left: '50%', bottom: 0, transform: 'translateX(-50%)', fontSize: 11.5, color: COLOR.muted }}>{xLabel}</span>}
      {yLabel && <span style={{ position: 'absolute', left: 0, top: 0, fontSize: 11.5, color: COLOR.muted }}>{yLabel}</span>}
    </div>
  );
}
