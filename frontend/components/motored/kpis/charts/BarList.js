import { COLOR } from '../tokens';
import Chip from './Chip';
import { barPlacement } from './geometry';
import RankBadge from './RankBadge';

const ENCIMA = { color: COLOR.ink2, position: 'absolute', left: 'calc(100% + 6px)' };
const DENTRO = { color: '#FFFFFF', textShadow: '0 1px 1px rgba(0,0,0,.3)' };

function Barra({ item, maximo, color, reference }) {
  const ancho = Math.min(Math.max((item.value / maximo) * 100, 0.6), 100);
  const sitio = barPlacement(ancho);
  return (
    <div style={{ position: 'relative', height: 20, background: COLOR.wash, borderRadius: 5 }}>
      <div
        style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: `${ancho}%`, background: item.color || color, borderRadius: 5,
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 7, boxSizing: 'border-box',
        }}
      >
        <span
          data-label={sitio}
          style={{ fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', ...(sitio === 'inside' ? DENTRO : ENCIMA) }}
        >
          {item.valueText}
        </span>
      </div>
      {reference && <LineaReferencia reference={reference} maximo={maximo} />}
    </div>
  );
}

function LineaReferencia({ reference, maximo }) {
  const izquierda = Number(((reference.at / maximo) * 100).toFixed(2));
  return (
    <>
      <span
        data-testid="reference-line" data-left={izquierda}
        style={{ position: 'absolute', left: `${izquierda}%`, top: -3, bottom: -3, width: 2, marginLeft: -1, background: COLOR.ink }}
      />
      {reference.label && (
        <span style={{ position: 'absolute', left: `${izquierda}%`, top: -17, transform: 'translateX(-50%)', fontSize: 10.5, fontWeight: 700, color: COLOR.ink }}>
          {reference.label}
        </span>
      )}
    </>
  );
}

function Fila({ item, rank, ranked, maximo, color, reference }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      {ranked && <RankBadge rank={rank} />}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, paddingTop: reference?.label ? 12 : 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.name}</span>
          <span style={{ display: 'inline-flex', gap: 4, flex: 'none' }}>
            {(item.chips || []).map((c) => <Chip key={c.text} text={c.text} variant={c.variant} />)}
          </span>
        </div>
        <Barra item={item} maximo={maximo} color={color} reference={reference} />
        {item.sub && (
          <span style={{ fontSize: 11.5, color: COLOR.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.sub}</span>
        )}
      </div>
    </div>
  );
}

/**
 * Horizontal bars with a rank badge. `items` [{name, sub, value, valueText, color, chips:[{text, variant}]}];
 * `maxValue` is the full width (default the largest value); `reference` {at, label} draws a line
 * (e.g. the 100% goal) in the same scale; `maxHeight` makes the list scroll inside its own box.
 */
export default function BarList({ items, maxValue, color = COLOR.info, reference, ranked = true, maxHeight }) {
  const maximo = maxValue || Math.max(1, ...items.map((i) => i.value));
  const scroll = maxHeight ? { maxHeight, overflowY: 'auto', paddingRight: 4 } : {};
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, ...scroll }}>
      {items.map((item, i) => (
        <Fila key={item.id ?? item.name} item={item} rank={i + 1} ranked={ranked} maximo={maximo} color={color} reference={reference} />
      ))}
    </div>
  );
}
