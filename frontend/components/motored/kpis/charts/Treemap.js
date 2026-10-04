import { COLOR } from '../tokens';
import { heatLevel, squarify } from './geometry';

const LIENZO = 100;

/** Default tile color: `colorValue` is a ratio against the average (1 = average), colored like the heatmap. */
const ESCALA = (ratio) => heatLevel(ratio);

function Teja({ tile, color, area }) {
  return (
    <div
      data-testid="treemap-tile" data-area={area} title={tile.tip ?? [tile.label, tile.valueText, tile.sub].filter(Boolean).join(' · ')}
      style={{
        position: 'absolute', left: `${tile.left}%`, top: `${tile.top}%`, width: `${tile.width}%`, height: `${tile.height}%`,
        boxSizing: 'border-box', padding: 1,
      }}
    >
      <div style={{ width: '100%', height: '100%', background: color.bg, color: color.fg, borderRadius: 6, padding: '6px 8px', overflow: 'hidden', boxSizing: 'border-box', lineHeight: 1.25 }}>
        <div style={{ fontSize: 12, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tile.label}</div>
        {tile.valueText && <div style={{ fontSize: 11.5, fontVariantNumeric: 'tabular-nums' }}>{tile.valueText}</div>}
        {tile.sub && <div style={{ fontSize: 10.5, opacity: 0.85 }}>{tile.sub}</div>}
      </div>
    </div>
  );
}

/**
 * Squarified treemap. `items` [{id, label, value, colorValue, valueText, sub, tip}] (`tip` replaces the default tooltip); tile area is proportional to
 * `value`. `colorScale(colorValue, item)` returns {bg, fg} (default: heatmap levels over a ratio).
 * `aspect` is width / height of the box; the box scales to its container width.
 */
export default function Treemap({ items, colorScale = ESCALA, aspect = 2, ariaLabel = 'Mapa de áreas' }) {
  const ancho = LIENZO * aspect;
  const tiles = squarify(items, ancho, LIENZO);
  return (
    <div role="img" aria-label={ariaLabel} style={{ position: 'relative', width: '100%', aspectRatio: String(aspect), background: COLOR.wash, borderRadius: 8 }}>
      {tiles.map((t) => (
        <Teja
          key={t.id ?? t.label}
          tile={{ ...t, left: (t.x / ancho) * 100, top: t.y, width: (t.w / ancho) * 100, height: t.h }}
          area={Number(((t.w * t.h) / (ancho * LIENZO) * 100).toFixed(2))}
          color={colorScale(t.colorValue, t)}
        />
      ))}
    </div>
  );
}
