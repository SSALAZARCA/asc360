import { COLOR } from '../tokens';
import { barPlacement } from './geometry';

const MINIMO = 22;

function Valor({ lado, ancho, texto }) {
  const sitio = barPlacement(ancho, MINIMO);
  const dentro = sitio === 'inside';
  const color = dentro ? '#FFFFFF' : lado === 'neg' ? COLOR.badInk : COLOR.goodInk;
  const posicion = lado === 'neg'
    ? { right: dentro ? 6 : `calc(${ancho.toFixed(1)}% + 5px)` }
    : { left: dentro ? 6 : `calc(${ancho.toFixed(1)}% + 5px)` };
  return (
    <span
      data-side={lado} data-label={sitio}
      style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', color, ...posicion }}
    >
      {texto}
    </span>
  );
}

function Mitad({ lado, ancho, texto }) {
  const color = lado === 'neg' ? COLOR.bad : COLOR.good;
  return (
    <div style={{ flex: 1, position: 'relative', height: 18, display: 'flex', justifyContent: lado === 'neg' ? 'flex-end' : 'flex-start' }}>
      {ancho > 0 && <div style={{ width: `${ancho}%`, background: color, borderRadius: lado === 'neg' ? '4px 0 0 4px' : '0 4px 4px 0' }} />}
      {ancho > 0 && <Valor lado={lado} ancho={ancho} texto={texto} />}
    </div>
  );
}

/** Negative values go left (violet), positive right (teal), around a centre line. `items` [{name, value, valueText}]. */
export default function DivergingBars({ items, maxAbs, nameWidth = 150, maxHeight }) {
  const maximo = maxAbs || Math.max(1e-9, ...items.map((i) => Math.abs(i.value)));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, ...(maxHeight ? { maxHeight, overflowY: 'auto' } : {}) }}>
      {items.map((item) => {
        const ancho = (Math.abs(item.value) / maximo) * 100;
        const negativo = item.value < 0;
        return (
          <div key={item.id ?? item.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span data-testid="diverging-name" style={{ width: nameWidth, flex: 'none', fontSize: 12.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.name}</span>
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', minWidth: 0 }}>
              <Mitad lado="neg" ancho={negativo ? ancho : 0} texto={item.valueText} />
              <span style={{ width: 2, height: 24, background: COLOR.ink, flex: 'none' }} />
              <Mitad lado="pos" ancho={negativo ? 0 : ancho} texto={item.valueText} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
