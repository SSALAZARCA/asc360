import { COLOR } from '../tokens';
import { NUM, ROTULO, TARJETA } from '../ventas/estilos';
import { comisionDe } from './comision';
import { gaugeDe, mesNombre } from './detalle';

const VALOR = { fontSize: 30, fontWeight: 700, color: COLOR.ink, margin: '6px 0 0', ...NUM, letterSpacing: '-.01em' };
const PIE = { fontSize: 12.5, color: COLOR.muted, margin: '8px 0 0' };
const SUBTITULO = { fontSize: 13.5, fontWeight: 700, color: COLOR.ink, margin: 0 };
const AMBAR = COLOR.mid;
// Room left on each side of the arc for the labels outside it (kept equal so the arc stays centered).
const MARGEN_ETIQUETAS = 'clamp(44px, 12%, 64px)';

function Corte({ c }) {
  const ancho = c.meta ? 3 : 2;
  return (
    <g>
      <title>{c.tip}</title>
      <line x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2} strokeWidth={ancho} style={{ stroke: COLOR.ink }} />
      <line x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2} strokeWidth="12" strokeOpacity="0" style={{ stroke: COLOR.ink }} />
    </g>
  );
}

function EtiquetaCorte({ c }) {
  const fuera = c.lado === 'fuera';
  return (
    <span
      title={c.tip}
      style={{
        position: 'absolute', left: c.lx, top: c.ly, transform: fuera ? 'translate(6px, -50%)' : 'translate(-100%, -50%)', width: 52, textAlign: fuera ? 'left' : 'right',
        fontSize: 11.5, fontWeight: 700, lineHeight: 1.1, color: c.color, cursor: 'help',
      }}
    >
      {c.label}
    </span>
  );
}

function Gauge({ g }) {
  return (
    <>
      <div style={{ flex: '1 1 auto', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: `0 ${MARGEN_ETIQUETAS}`, boxSizing: 'border-box' }}>
        <div style={{ position: 'relative', width: '100%', maxWidth: 440 }}>
          <svg viewBox="0 0 200 128" role="img" aria-label={g.aria} style={{ display: 'block', width: '100%', height: 'auto' }}>
            <path d="M20 104 A80 80 0 0 1 180 104" fill="none" strokeWidth="18" strokeLinecap="round" style={{ stroke: COLOR.track }} />
            <path d="M20 104 A80 80 0 0 1 180 104" fill="none" strokeWidth="18" strokeLinecap="round" strokeDasharray={g.arco} style={{ stroke: g.color }} />
            {g.cortes.map((c) => <Corte key={c.label} c={c} />)}
            <text x="20" y="124" textAnchor="middle" fontSize="10" style={{ fill: COLOR.soft }}>0</text>
            <text x="180" y="124" textAnchor="middle" fontSize="10" style={{ fill: COLOR.soft }}>120%</text>
          </svg>
          {g.cortes.map((c) => <EtiquetaCorte key={c.label} c={c} />)}
        </div>
      </div>
      <p style={{ ...VALOR, marginTop: 0, fontSize: 48, lineHeight: 1.1 }}>{g.texto}</p>
      <p style={{ ...PIE, textAlign: 'center', fontSize: 15, ...NUM }}>{g.pie}</p>
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

function Ganados({ lineas }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {lineas.map((l) => (
        <div key={l.linea} data-testid="bono-ganado" style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 10px', alignItems: 'baseline', justifyContent: 'space-between', fontSize: 13 }}>
            <span>{l.texto}</span>
            <strong style={{ ...NUM, color: AMBAR }}>{l.monto}</strong>
          </span>
          <span aria-hidden="true" style={{ display: 'block', height: 4, borderRadius: 999, background: AMBAR, width: '100%' }} />
        </div>
      ))}
    </div>
  );
}

function ParaBonos({ b }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <p title={b.tip} style={{ ...SUBTITULO, cursor: 'help' }}>Para ganar más bonos</p>
      {b.filas.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: '4px 14px', alignItems: 'baseline' }}>
          {b.filas.map((f) => (
            <div key={f.linea} data-testid="bono-pendiente" style={{ display: 'contents' }}>
              <span style={{ fontSize: 12.5, color: COLOR.ink2, minWidth: 0 }}>{f.etiqueta}</span>
              <span style={{ ...NUM, fontSize: 12, color: COLOR.muted, textAlign: 'right', whiteSpace: 'nowrap' }}>{f.falta}</span>
              <strong style={{ ...NUM, fontSize: 12.5, color: AMBAR, textAlign: 'right', whiteSpace: 'nowrap' }}>{f.bono}</strong>
            </div>
          ))}
        </div>
      )}
      {b.mensaje && <p style={{ ...NUM, margin: 0, fontSize: 12.5, color: COLOR.muted }}>{b.mensaje}</p>}
    </div>
  );
}

function Para100({ p }) {
  if (!p.texto) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <p style={SUBTITULO}>Para llegar al 100%</p>
      <p style={{ margin: 0, fontSize: p.ok ? 13 : 12.5, fontWeight: p.ok ? 700 : 400, color: p.ok ? COLOR.goodInk : COLOR.muted }}>{p.texto}</p>
    </div>
  );
}

function TarjetaComision({ data }) {
  const c = comisionDe(data);
  if (!c) return null;
  return (
    <section aria-label="Comisión estimada" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <p style={ROTULO}>{c.titulo}</p>
        <p style={{ ...VALOR, margin: 0 }}>{c.valor}</p>
        {c.desglose && <p style={{ ...PIE, margin: 0, ...NUM }}>{c.desglose}</p>}
        <span style={{ alignSelf: 'flex-start', fontSize: 11.5, fontWeight: 700, color: '#FFFFFF', background: c.chip.color, borderRadius: 999, padding: '2px 10px' }}>{c.chip.texto}</span>
      </div>
      {c.ganados.length > 0 && <Ganados lineas={c.ganados} />}
      {c.paraBonos && <ParaBonos b={c.paraBonos} />}
      <Para100 p={c.para100} />
      {c.datos && <p style={{ margin: 0, fontSize: 12, color: COLOR.soft }}>{c.datos}</p>}
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
