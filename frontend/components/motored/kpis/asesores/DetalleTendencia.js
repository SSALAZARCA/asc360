import { Chip } from '../charts';
import { COLOR } from '../tokens';
import { CABECERA, LEYENDA, NUM, TARJETA, TITULO } from '../ventas/estilos';
import { periodoCorto } from '../periodo';
import NotaVentana from '../ventas/NotaVentana';
import { lineasDe, tendenciaDe } from './detalle';

const ROJO = COLOR.gray500;

function Leyenda({ items }) {
  return (
    <div style={LEYENDA}>
      {items.map((i) => <span key={i.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>{i.marca}{i.label}</span>)}
    </div>
  );
}

function Grafico({ t }) {
  return (
    <svg viewBox="0 0 560 250" width="100%" role="img" aria-label={t.aria} style={{ display: 'block', marginTop: 10 }}>
      {t.bandas.map((b) => <rect key={b.nombre} x="44" y={b.y} width="500" height={b.alto} style={{ fill: b.fill }} />)}
      {t.grid.map((g) => (
        <g key={g.label}>
          <line x1="44" x2="544" y1={g.y} y2={g.y} strokeWidth={g.corte ? 1.5 : 1} style={{ stroke: g.corte ? COLOR.ink : COLOR.track }} />
          <text x="38" y={g.ty} textAnchor="end" fontSize="11" fontWeight={g.corte ? 700 : 500} style={{ fill: g.corte ? COLOR.ink : COLOR.soft }}>{g.label}</text>
        </g>
      ))}
      {t.bandas.map((b) => <text key={b.nombre} x="540" y={b.yEtiqueta} textAnchor="end" fontSize="10.5" fontWeight="700" style={{ fill: b.color }}>{b.nombre}</text>)}
      {t.rojo && <path d={t.rojo} fill="none" strokeWidth="2" strokeDasharray="5 4" style={{ stroke: ROJO }} />}
      {t.linea && <path d={t.linea} fill="none" strokeWidth="3" strokeLinejoin="round" style={{ stroke: COLOR.info }} />}
      {t.puntos.map((p) => (
        <g key={p.m}>
          {p.y && <circle cx={p.x} cy={p.y} r="4.5" strokeWidth="2" style={{ fill: COLOR.info, stroke: '#FFFFFF' }} />}
          {p.val && <text x={p.x} y={p.ly} textAnchor="middle" fontSize="10.5" fontWeight="700" style={{ fill: COLOR.ink }}>{p.val}</text>}
          <text x={p.x} y="240" textAnchor="middle" fontSize="11" style={{ fill: COLOR.muted }}>{p.m}</text>
        </g>
      ))}
    </svg>
  );
}

function TarjetaTendencia({ data }) {
  const t = tendenciaDe(data);
  const marcas = [
    { marca: <span style={{ width: 16, height: 3, background: COLOR.info, borderRadius: 2 }} />, label: 'Su cumplimiento' },
    { marca: <span style={{ width: 16, height: 0, borderTop: `2px dashed ${ROJO}` }} />, label: 'Promedio red' },
  ];
  return (
    <section aria-label="Tendencia de cumplimiento" style={TARJETA}>
      <div style={CABECERA}>
        <h3 style={TITULO}>Tendencia de cumplimiento</h3>
        <Leyenda items={marcas} />
      </div>
      <NotaVentana />
      <Grafico t={t} />
      <p style={{ margin: '4px 0 0', fontSize: 12.5, color: COLOR.muted }}>{t.nota}</p>
    </section>
  );
}

function FilaLinea({ f }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '92px minmax(0, 1fr) 118px', gap: 10, alignItems: 'center' }}>
      <span style={{ fontSize: 12.5, fontWeight: 700 }}>{f.name}</span>
      <div style={{ position: 'relative', height: 14, background: COLOR.wash, borderRadius: 4 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: f.w, background: COLOR.info, borderRadius: 4 }} />
        {f.red && <span title={f.tip} style={{ position: 'absolute', left: f.red, top: -4, bottom: -4, width: 2, marginLeft: -1, background: COLOR.ink }} />}
      </div>
      <span style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'baseline', gap: 6 }}>
        <strong style={{ ...NUM, fontSize: 12.5 }}>{f.pct}</strong>
        {f.diff && <Chip text={f.diff} variant={f.variant} />}
      </span>
    </div>
  );
}

function TarjetaLineas({ data }) {
  const l = lineasDe(data);
  if (!l.filas.length) return null;
  const marcas = [
    { marca: <span style={{ width: 12, height: 10, borderRadius: 3, background: COLOR.info }} />, label: 'Su venta' },
    { marca: <span style={{ width: 2, height: 12, background: COLOR.ink }} />, label: 'Promedio red' },
  ];
  return (
    <section aria-label="Venta por línea vs la red" style={TARJETA}>
      <div style={CABECERA}>
        <h3 style={TITULO}>Venta por línea vs la red · {periodoCorto(data.meses)}</h3>
        <Leyenda items={marcas} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
        {l.filas.map((f) => <FilaLinea key={f.name} f={f} />)}
      </div>
      {l.nota && <p style={{ margin: '14px 0 0', fontSize: 12.5, color: COLOR.muted }}>{l.nota}</p>}
    </section>
  );
}

/** Monthly compliance trend and the share of each line against the network. */
export default function DetalleTendencia({ data }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16 }}>
      <TarjetaTendencia data={data} />
      <TarjetaLineas data={data} />
    </div>
  );
}
