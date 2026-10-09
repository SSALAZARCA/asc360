'use client';
/** "Valor del inventario por mes": bars at cost per month-end valued corte, with the days chip below each. */
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { barrasTendencia } from './datos';
import { PUNTO, SUBTITULO, TARJETA_COLUMNA } from './estilos';

const MESES_MAX = 12;
const ANCHO_COLUMNA = 80;

function Leyenda({ cortes }) {
  const items = [
    { texto: `Días ≤ ${cortes.verde_hasta}`, fondo: COLOR.goodSoft, borde: COLOR.good },
    { texto: `${cortes.verde_hasta + 1} a ${cortes.ambar_hasta}`, fondo: COLOR.midSoft, borde: COLOR.mid },
    { texto: `Más de ${cortes.ambar_hasta}`, fondo: COLOR.badSoft, borde: COLOR.bad },
  ];
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 12, color: COLOR.muted }}>
      {items.map((i) => (
        <span key={i.texto} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ ...PUNTO(i.fondo, 999), border: `1px solid ${i.borde}` }} />{i.texto}
        </span>
      ))}
    </div>
  );
}

export default function TendenciaInventario({ data }) {
  const barras = barrasTendencia(data);
  const n = barras.length;
  // With few months the columns keep a sensible width instead of stretching one bar across the card.
  const rejilla = { display: 'grid', gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, gap: 8, maxWidth: n < MESES_MAX ? n * ANCHO_COLUMNA : undefined };
  const encabezado = (
    <div>
      <h2 style={TITULO}>Valor del inventario por mes</h2>
      <p style={SUBTITULO}>A costo, al cierre de cada mes · debajo, los días de inventario de ese mes</p>
    </div>
  );
  // The selected corte can fall outside every month that has a point, so an empty trend is possible.
  if (n === 0) {
    return (
      <section aria-label="Valor del inventario por mes" style={{ ...TARJETA, ...TARJETA_COLUMNA }}>
        {encabezado}
        <p style={{ margin: 0, fontSize: 13, color: COLOR.muted }}>Todavía no hay cierres de mes con costo para graficar.</p>
      </section>
    );
  }
  return (
    <section aria-label="Valor del inventario por mes" style={{ ...TARJETA, ...TARJETA_COLUMNA }}>
      {encabezado}
      <div
        role="img" aria-label={`Valor del inventario de ${barras[0].mes} a ${barras[n - 1].mes}`}
        style={{ ...rejilla, alignItems: 'end', height: 220, borderBottom: `1px solid ${COLOR.track}` }}
      >
        {barras.map((m) => (
          <div key={m.mes + m.valor} data-testid="barra-mes" title={m.tip} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 4, height: '100%' }}>
            <span style={{ ...NUM, fontSize: 10.5, fontWeight: 700, color: COLOR.ink2 }}>{m.valor}</span>
            <div style={{ width: '100%', maxWidth: 38, height: m.alto, background: m.color, borderRadius: '6px 6px 0 0' }} />
          </div>
        ))}
      </div>
      <div style={rejilla}>
        {barras.map((m) => (
          <div key={m.mes + m.valor} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 11, color: COLOR.muted }}>{m.mes}</span>
            <span data-testid="dias-mes" style={{ ...NUM, fontSize: 11, fontWeight: 700, color: m.luz.fg, background: m.luz.bg, borderRadius: 999, padding: '1px 7px' }}>{m.dias}</span>
          </div>
        ))}
      </div>
      <Leyenda cortes={data.cortes_color} />
      {n < MESES_MAX && <p style={{ margin: 0, fontSize: 12, color: COLOR.muted }}>La gráfica se va llenando con el cierre de cada mes</p>}
    </section>
  );
}
