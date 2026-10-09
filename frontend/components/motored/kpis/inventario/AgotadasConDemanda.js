'use client';
/** "Agotadas con demanda": stockouts with their 3-month demand and how much of it the stock in transit covers. */
import { useState } from 'react';
import { miles } from '../format';
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { filasAgotadas } from './datos';
import { PUNTO, SUBTITULO } from './estilos';

const TOP = 8;
const LILA = '#DCC6F0';

function Chips({ a }) {
  const chip = (texto, color, fondo) => (
    <span key={texto} style={{ fontSize: 12, fontWeight: 700, color, background: fondo, borderRadius: 999, padding: '4px 10px' }}>{texto}</span>
  );
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {chip(`${miles(a.total)} agotadas`, COLOR.ink, COLOR.wash)}
      {chip(`${miles(a.en_transito)} en tránsito`, COLOR.info, '#E7EEF7')}
      {chip(`${miles(a.sin_pedir)} sin pedir`, COLOR.bad, COLOR.badSoft)}
    </div>
  );
}

function FilaAgotada({ a }) {
  return (
    <div data-testid="fila-agotada" title={a.tip} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12.5 }}>
        <span style={{ fontWeight: 700, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {a.referencia} <span style={{ fontWeight: 500, color: COLOR.muted }}>· {a.nombre}</span>
        </span>
        <span style={{ color: COLOR.muted, whiteSpace: 'nowrap' }}>{a.tienda}</span>
      </div>
      <span style={{ ...NUM, fontSize: 11.5, color: COLOR.muted }}>{a.detalle}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ flex: 1, height: 22 }}>
          <div style={{ width: `${a.ancho}%`, height: 22, display: 'flex', borderRadius: 6, overflow: 'hidden' }}>
            <div data-testid="barra-cubierta" style={{ width: `${a.cubierto}%`, background: COLOR.info }} />
            <div style={{ flex: 1, background: LILA }} />
          </div>
        </div>
        <span style={{ ...NUM, minWidth: 112, textAlign: 'right', fontSize: 11.5, fontWeight: 700, color: a.enTransito ? COLOR.info : COLOR.bad }}>{a.etiqueta}</span>
      </div>
    </div>
  );
}

export default function AgotadasConDemanda({ data }) {
  const [todas, setTodas] = useState(false);
  const { agotadas: ag } = data;
  const filas = filasAgotadas(ag.items);
  return (
    <section aria-label="Agotadas con demanda" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h2 style={TITULO}>Agotadas con demanda</h2>
        <p style={SUBTITULO}>Referencias que se venden y hoy están en cero · demanda = vendidas + ventas perdidas · cuánto cubre lo que viene en camino</p>
      </div>
      <Chips a={ag} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 12, color: COLOR.muted }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={PUNTO(COLOR.info)} />Unidades en tránsito</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={PUNTO(LILA)} />Demanda sin cubrir</span>
        <span>Largo de la barra = demanda de 3 meses (vendidas + ventas perdidas)</span>
      </div>
      <div role="img" aria-label="Agotadas con demanda y cuánto cubre lo que viene en tránsito" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(todas ? filas : filas.slice(0, TOP)).map((a) => <FilaAgotada key={a.id} a={a} />)}
      </div>
      {filas.length > TOP && (
        <button type="button" className="inv-link" aria-expanded={todas} onClick={() => setTodas((v) => !v)} style={{ alignSelf: 'flex-start' }}>
          {todas ? 'Ver menos' : `Ver todas (${filas.length})`}
        </button>
      )}
    </section>
  );
}
