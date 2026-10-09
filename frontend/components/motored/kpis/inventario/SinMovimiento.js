'use client';
/** "Mayor valor sin movimiento": horizontal bars of the idle references, shade by days without sale. */
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { filasQuietas } from './datos';
import { PUNTO, SUBTITULO } from './estilos';

const TRAMOS = (umbral) => [
  { texto: `${umbral + 1} a 270 días`, color: '#B9A0DA' },
  { texto: '271 a 365 días', color: '#8B5CC4' },
  { texto: 'Más de 365 días', color: '#5B1E93' },
];

function FilaQuieta({ q }) {
  return (
    <div data-testid="fila-quieta" title={q.tip} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12.5 }}>
        <span style={{ fontWeight: 700, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {q.referencia} <span style={{ fontWeight: 500, color: COLOR.muted }}>· {q.nombre}</span>
        </span>
        <span style={{ color: COLOR.muted, whiteSpace: 'nowrap' }}>{q.tienda}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ flex: 1, height: 22, background: '#F3F3F1', borderRadius: 6 }}>
          <div data-testid="barra-quieta" style={{ width: `${q.ancho}%`, height: 22, background: q.color, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', padding: '0 8px', boxSizing: 'border-box' }}>
            <span style={{ ...NUM, fontSize: 11.5, fontWeight: 700, color: '#FFFFFF', whiteSpace: 'nowrap' }}>{q.valorTexto}</span>
          </div>
        </div>
        <span style={{ ...NUM, minWidth: 92, textAlign: 'right', fontSize: 11.5, color: COLOR.ink2, whiteSpace: 'nowrap' }}>{q.diasTexto} · {q.existencia} und</span>
      </div>
    </div>
  );
}

export default function SinMovimiento({ data }) {
  const umbral = data.sin_movimiento_umbral_dias;
  return (
    <section aria-label="Mayor valor sin movimiento" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h2 style={TITULO}>Mayor valor sin movimiento</h2>
        <p style={SUBTITULO}>Referencias con más plata quieta (más de {umbral} días sin venta)</p>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 12, color: COLOR.muted }}>
        {TRAMOS(umbral).map((t) => (
          <span key={t.texto} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={PUNTO(t.color)} />{t.texto}</span>
        ))}
      </div>
      <div role="img" aria-label="Referencias con mayor valor sin movimiento" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {filasQuietas(data).map((q) => <FilaQuieta key={q.id} q={q} />)}
      </div>
    </section>
  );
}
