import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { explicacionDe } from './comision';

const SUBTITULO = { fontSize: 13.5, fontWeight: 700, color: COLOR.ink, margin: 0 };

function Info({ claro }) {
  return (
    <span data-testid="info-paso" aria-hidden="true" style={{ position: 'absolute', top: 6, right: 6, display: 'flex', color: claro ? 'rgba(255,255,255,.85)' : '#8A8A84' }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="M12 16v-5M12 8h.01" />
      </svg>
    </span>
  );
}

// Look of each tile: [background, border, label color, value color].
const estiloDe = (p) => {
  if (p.estilo === 'total') return [COLOR.good, COLOR.good, '#FFFFFF', '#FFFFFF'];
  if (p.estilo === 'tramo') return [COLOR.surface, p.color, p.color, p.color];
  if (p.estilo === 'bono') return [COLOR.surface, COLOR.mid, COLOR.mid, COLOR.mid];
  return ['#F7F7F5', COLOR.track, COLOR.muted, COLOR.ink];
};

function Paso({ p }) {
  const [fondo, borde, rotulo, valor] = estiloDe(p);
  const total = p.estilo === 'total';
  return (
    <div title={p.tip} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flex: '1 1 auto', minWidth: 112, cursor: 'help' }}>
      <div style={{ position: 'relative', background: fondo, border: `${fondo === '#F7F7F5' ? 1 : 2}px solid ${borde}`, borderRadius: 12, padding: '12px 18px', width: '100%', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, textAlign: 'center' }}>
        <Info claro={total} />
        <span style={{ fontSize: 11.5, fontWeight: 700, color: rotulo }}>{p.label}</span>
        <strong style={{ ...NUM, fontSize: total ? 22 : 20, lineHeight: 1.15, color: valor }}>{p.valor}</strong>
      </div>
      {p.caption && <span style={{ fontSize: 11.5, color: COLOR.muted, textAlign: 'center' }}>{p.caption}</span>}
    </div>
  );
}

function Ecuacion({ pasos }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, flex: '2 1 560px', minWidth: 0 }}>
      <p style={SUBTITULO}>Paso a paso</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: 10 }}>
        {pasos.map((p) => (
          <div key={p.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, flex: '1 1 150px', minWidth: 0 }}>
            {p.operador && <span style={{ fontSize: 30, fontWeight: 700, color: COLOR.gray400, paddingTop: 18, lineHeight: 1, flex: 'none' }}>{p.operador}</span>}
            <Paso p={p} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Escalera({ e }) {
  const n = e.tramos.length;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: '1 1 300px', minWidth: 0 }}>
      <p style={SUBTITULO}>Tramos</p>
      <div style={{ display: 'flex', gap: 3, fontSize: 11.5 }}>
        {e.tramos.map((t, i) => (
          <div
            key={t.nombre}
            style={{
              flex: '1 1 0', minWidth: 0, background: t.color, color: i === 0 ? COLOR.ink : '#FFFFFF', padding: '6px 8px', display: 'flex', flexDirection: 'column', gap: 1,
              borderRadius: `${i === 0 ? 8 : 0}px ${i === n - 1 ? 8 : 0}px ${i === n - 1 ? 8 : 0}px ${i === 0 ? 8 : 0}px`,
              boxShadow: t.actual ? `0 0 0 2px #FFFFFF, 0 0 0 4px ${t.color}` : 'none',
            }}
          >
            <strong>{t.tasa ? `${t.nombre} · ${t.tasa}` : t.nombre}</strong><span>{t.desde}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 3 }}>
        {e.tramos.map((t) => (
          <div key={t.nombre} style={{ flex: '1 1 0', minWidth: 0, display: 'flex', justifyContent: 'center' }}>
            {t.actual && <span style={{ fontSize: 12, fontWeight: 700, color: COLOR.goodInk, background: COLOR.goodSoft, borderRadius: 6, padding: '3px 8px', whiteSpace: 'nowrap' }}>{e.marcador}</span>}
          </div>
        ))}
      </div>
      <p style={{ margin: 0, fontSize: 12.5, fontWeight: 700 }}>{e.siguiente}</p>
      <p style={{ margin: 0, fontSize: 11.5, color: COLOR.soft }}>{e.nota}</p>
    </div>
  );
}

/** Last section of the single-asesor view: how the commission is built, tile by tile, and the tier ladder. */
export default function DetalleComision({ data }) {
  const e = explicacionDe(data);
  if (!e) return null;
  return (
    <section aria-label={e.titulo} style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <p style={TITULO}>{e.titulo}</p>
        <p style={{ margin: '2px 0 0', fontSize: 12.5, color: COLOR.muted }}>{e.sub}</p>
        <p style={{ margin: '8px 0 0', fontSize: 12, color: COLOR.soft, display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }} aria-hidden="true">
            <circle cx="12" cy="12" r="10" /><path d="M12 16v-5M12 8h.01" />
          </svg>
          {e.pista}
        </p>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 28 }}>
        <Ecuacion pasos={e.pasos} />
        <Escalera e={e} />
      </div>
    </section>
  );
}
