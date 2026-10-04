import { useState } from 'react';
import { BarList, DivergingBars, SegmentedToggle, StackedBar100 } from '../charts';
import { periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { CABECERA, NUM, TARJETA, TITULO } from '../ventas/estilos';
import { filasMezcla, lineasMezcla, rankingCrecimiento, rankingVenta } from './datos';

const VISTAS = [{ id: 'venta', label: 'Venta' }, { id: 'crec', label: 'Crecimiento' }, { id: 'mezcla', label: 'Mezcla' }];
const ALTO = 420;
const NOMBRE = 210;

function Crecimiento({ data }) {
  const items = rankingCrecimiento(data);
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', gap: 8, fontSize: 11, color: COLOR.soft }}>
        <span style={{ width: NOMBRE, flex: 'none' }} />
        <span style={{ flex: 1, textAlign: 'right', paddingRight: 6 }}>▼ cae</span>
        <span style={{ flex: 1, paddingLeft: 6 }}>crece ▲</span>
      </div>
      <div style={{ marginTop: 6 }}><DivergingBars items={items} nameWidth={NOMBRE} maxHeight={ALTO} /></div>
    </div>
  );
}

function Mezcla({ data }) {
  const lineas = lineasMezcla(data);
  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 14 }}>
        {lineas.map((l) => (
          <span key={l.id} data-testid="mezcla-leyenda" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: COLOR.ink2 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: l.color }} />{l.name}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12, maxHeight: ALTO, overflowY: 'auto', paddingRight: 8 }}>
        {filasMezcla(data).map((f) => (
          <div key={f.id} data-testid="mezcla-fila" style={{ display: 'grid', gridTemplateColumns: `minmax(120px, ${NOMBRE}px) minmax(0, 1fr) 54px`, gap: 10, alignItems: 'center' }}>
            <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</span>
            <StackedBar100 segments={f.segments} height={20} />
            <span style={{ ...NUM, fontSize: 12, fontWeight: 700, textAlign: 'right' }}>{f.rep}</span>
          </div>
        ))}
      </div>
    </>
  );
}

/** "Ranking de tiendas": sales bars, growth diverging bars or the mix of each store, each with its own scroll. */
export default function RankingTiendas({ data }) {
  const [vista, setVista] = useState('venta');
  return (
    <section aria-label="Ranking de tiendas" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Ranking de tiendas · {periodoCorto(data.meses)}</h2>
        <SegmentedToggle options={VISTAS} value={vista} onChange={setVista} />
      </div>
      {vista === 'venta' && <div style={{ marginTop: 14 }}><BarList items={rankingVenta(data)} maxHeight={ALTO} /></div>}
      {vista === 'crec' && <Crecimiento data={data} />}
      {vista === 'mezcla' && <Mezcla data={data} />}
    </section>
  );
}
