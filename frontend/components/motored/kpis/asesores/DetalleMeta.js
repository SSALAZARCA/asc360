import { COLOR } from '../tokens';
import { ROTULO, TARJETA } from '../ventas/estilos';
import { comisionDe, gaugeDe, mesNombre } from './detalle';

const VALOR = { fontSize: 30, fontWeight: 700, color: COLOR.ink, margin: '6px 0 0', fontVariantNumeric: 'tabular-nums', letterSpacing: '-.01em' };
const PIE = { fontSize: 12.5, color: COLOR.muted, margin: '8px 0 0' };

function Gauge({ g }) {
  return (
    <>
      <svg viewBox="0 0 200 128" width={240} height={154} role="img" aria-label={g.aria} style={{ maxWidth: '100%' }}>
        <path d="M20 104 A80 80 0 0 1 180 104" fill="none" strokeWidth="18" strokeLinecap="round" style={{ stroke: COLOR.track }} />
        <path d="M20 104 A80 80 0 0 1 180 104" fill="none" strokeWidth="18" strokeLinecap="round" strokeDasharray={g.arco} style={{ stroke: g.color }} />
        {g.cortes.map((c) => (
          <g key={c.label}>
            <line x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2} strokeWidth="2" style={{ stroke: COLOR.ink }} />
            <text x={c.tx} y={c.ty} textAnchor="middle" fontSize="9.5" fontWeight="700" style={{ fill: COLOR.ink }}>{c.label}</text>
          </g>
        ))}
        <text x="20" y="124" textAnchor="middle" fontSize="10" style={{ fill: COLOR.soft }}>0</text>
        <text x="180" y="124" textAnchor="middle" fontSize="10" style={{ fill: COLOR.soft }}>120%</text>
      </svg>
      <p style={{ ...VALOR, marginTop: 0 }}>{g.texto}</p>
      <p style={{ ...PIE, textAlign: 'center' }}>{g.pie}</p>
    </>
  );
}

function TarjetaGauge({ data }) {
  const g = gaugeDe(data);
  return (
    <section aria-label="Cumplimiento de su meta" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <p style={{ ...ROTULO, alignSelf: 'flex-start' }}>Cumplimiento de su meta · {mesNombre(data)}</p>
      {g ? <Gauge g={g} /> : <p style={{ ...PIE, margin: '24px 0' }}>Sin presupuesto cargado para {mesNombre(data)}.</p>}
    </section>
  );
}

function Siguiente({ s }) {
  return (
    <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, fontSize: 12.5 }}>
        <span style={{ fontWeight: 700 }}>{s.titulo}</span>
        <span style={{ color: COLOR.muted, fontVariantNumeric: 'tabular-nums' }}>{s.meta}</span>
      </div>
      <div style={{ position: 'relative', height: 12, background: COLOR.track, borderRadius: 999 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${s.avance}%`, background: s.color, borderRadius: 999 }} />
        <span style={{ position: 'absolute', left: '100%', top: -4, bottom: -4, width: 2, marginLeft: -2, background: s.colorMeta }} />
      </div>
    </div>
  );
}

function TarjetaComision({ data }) {
  const c = comisionDe(data);
  if (!c) return null;
  return (
    <section aria-label="Comisión estimada" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <p style={ROTULO}>{c.titulo}</p>
      <p style={{ ...VALOR, margin: 0 }}>{c.valor}</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#FFFFFF', background: c.chip.color, borderRadius: 999, padding: '2px 8px' }}>{c.chip.texto}</span>
        <span style={{ ...PIE, margin: 0 }}>{c.base}</span>
      </div>
      {c.siguiente && <Siguiente s={c.siguiente} />}
      <p style={{ ...PIE, margin: 0 }}>{c.nota}</p>
    </section>
  );
}

/** Goal gauge of her month and the estimated commission (the card is left out when she is not liquidated). */
export default function DetalleMeta({ data }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
      <TarjetaGauge data={data} />
      <TarjetaComision data={data} />
    </div>
  );
}
