import { StackedArea } from '../charts';
import { millones, miles, moneda } from '../format';
import { CATEGORIA, COLOR } from '../tokens';
import { mesCorto, ventaPorLinea } from './datos';
import { CABECERA, NUM, TARJETA, TITULO } from './estilos';
import NotaVentana from './NotaVentana';

const TIP_TICKET = 'Venta promedio por factura que incluye esta línea';

function Leyenda({ lineas }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
      {lineas.map((l) => (
        <span key={l.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, color: COLOR.ink2 }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: l.color }} />{l.name}
        </span>
      ))}
    </div>
  );
}

function Fichas({ lineas }) {
  const total = lineas.reduce((t, l) => t + l.total, 0);
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10, marginTop: 14 }}>
      {lineas.map((l) => (
        <div key={l.id} style={{ padding: '10px 12px', borderRadius: 10, background: COLOR.wash, borderLeft: `4px solid ${l.color}` }}>
          <div style={{ fontSize: 11.5, fontWeight: 500, color: COLOR.muted }}>{l.name}</div>
          <div style={{ ...NUM, fontSize: 20, fontWeight: 700 }}>{total > 0 ? `${((l.total / total) * 100).toFixed(1).replace('.', ',')}%` : '—'}</div>
          <div title={TIP_TICKET} style={{ ...NUM, fontSize: 11.5, color: COLOR.muted }}>
            {`${millones(l.total)} · ticket ${l.ticket ? moneda(l.ticket) : '—'}`}
          </div>
        </div>
      ))}
    </div>
  );
}

/** "Venta mensual por línea": legend, share tiles and the stacked area (months x lines, blue scale). */
export default function VentaPorLinea({ data }) {
  const { meses, lineas } = ventaPorLinea(data);
  const pintadas = lineas.map((l, i) => ({ ...l, color: CATEGORIA[i % CATEGORIA.length] }));
  return (
    <section aria-label="Venta mensual por línea" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Venta mensual por línea</h2>
        <Leyenda lineas={pintadas} />
      </div>
      <NotaVentana />
      <Fichas lineas={pintadas} />
      <div style={{ overflowX: 'auto', marginTop: 12 }}>
        <div style={{ minWidth: 540 }}>
          <StackedArea months={meses.map(mesCorto)} series={pintadas} showLegend={false} formatValue={(v) => `$${miles(v)} M`} />
        </div>
      </div>
    </section>
  );
}
