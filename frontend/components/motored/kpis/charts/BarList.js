import { useLayoutEffect, useRef, useState } from 'react';
import { COLOR } from '../tokens';
import Chip from './Chip';
import { valuePlacement } from './geometry';
import RankBadge from './RankBadge';

const ENCIMA = { color: '#3D3D3A', position: 'absolute', left: 'calc(100% + 6px)' };
const DENTRO = { color: '#FFFFFF', textShadow: '0 1px 1px rgba(0,0,0,.3)' };

const PISTA_POR_DEFECTO = 300;

/** Width in px of the track: measured when the browser can, else the given estimate. */
function usePista(estimado) {
  const ref = useRef(null);
  const [medido, setMedido] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const leer = () => setMedido(el.offsetWidth || 0);
    leer();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const obs = new ResizeObserver(leer);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, px: medido || estimado };
}

const anchoDe = (item, maximo) => Math.min(Math.max((item.value / maximo) * 100, 0.6), 100);

function Barra({ item, ancho, sitio, pistaRef, reference, maximo, color }) {
  return (
    <div ref={pistaRef} style={{ position: 'relative', height: 20, background: COLOR.wash, borderRadius: 5 }}>
      <div
        style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: `${ancho}%`, background: item.color || color, borderRadius: 5,
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 7, boxSizing: 'border-box',
        }}
      >
        {sitio !== 'sub' && (
          <span
            data-label={sitio}
            style={{ fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', ...(sitio === 'inside' ? DENTRO : ENCIMA) }}
          >
            {item.valueText}
          </span>
        )}
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

function Fila({ item, rank, ranked, maximo, color, reference, trackWidth }) {
  const pista = usePista(trackWidth);
  const ancho = anchoDe(item, maximo);
  const sitio = valuePlacement({ widthPct: ancho, text: item.valueText, trackPx: pista.px });
  const sub = sitio === 'sub' ? [item.valueText, item.sub].filter(Boolean).join(' · ') : item.sub;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      {ranked && <RankBadge rank={rank} colors={item.badge} />}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, paddingTop: reference?.label ? 12 : 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.name}</span>
          <span style={{ display: 'inline-flex', gap: 4, flex: 'none' }}>
            {(item.chips || []).map((c) => <Chip key={c.text} text={c.text} variant={c.variant} />)}
          </span>
        </div>
        <Barra item={item} ancho={ancho} sitio={sitio} pistaRef={pista.ref} maximo={maximo} color={color} reference={reference} />
        {sub && (
          <span title={item.tip} style={{ fontSize: 11.5, color: COLOR.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</span>
        )}
      </div>
    </div>
  );
}

/**
 * Horizontal bars with a rank badge. `items` [{name, sub, value, valueText, color, chips:[{text, variant}]}];
 * `badge` {bg, fg} recolors the rank badge; `tip` is the tooltip of the sub-line; `maxValue` is the full width (default the largest value); `reference` {at, label} draws a line
 * (e.g. the 100% goal) in the same scale; `maxHeight` makes the list scroll inside its own box; `trackWidth` is the px estimate of the track when it cannot be measured.
 */
export default function BarList({ items, maxValue, color = COLOR.info, reference, ranked = true, maxHeight, trackWidth = PISTA_POR_DEFECTO }) {
  const maximo = maxValue || Math.max(1, ...items.map((i) => i.value));
  const scroll = maxHeight ? { maxHeight, overflowY: 'auto', paddingRight: 4 } : {};
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, ...scroll }}>
      {items.map((item, i) => (
        <Fila key={item.id ?? item.name} item={item} rank={i + 1} ranked={ranked} maximo={maximo} color={color} reference={reference} trackWidth={trackWidth} />
      ))}
    </div>
  );
}
