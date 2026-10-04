import { Heatmap, Scatter } from '../charts';
import { periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { CABECERA, LEYENDA, TARJETA, TITULO } from '../ventas/estilos';
import { dispersionVentaMargen, matrizMensual } from './datos';

const LEYENDA_PUNTOS = [['crece', COLOR.good], ['cae', COLOR.bad], ['nueva', COLOR.gray500]];

function MapaDeCalor({ data }) {
  const { columns, rows } = matrizMensual(data);
  return (
    <section aria-label="Venta mensual por tienda" style={TARJETA}>
      <div style={CABECERA}><h2 style={TITULO}>Venta mensual por tienda · vs su promedio</h2></div>
      <Heatmap columns={columns} rows={rows} maxHeight={420} nameWidth={150} rowHeader="Tienda" />
    </section>
  );
}

function Dispersion({ data }) {
  const d = dispersionVentaMargen(data);
  return (
    <section aria-label="Venta vs margen" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Venta vs margen</h2>
        <div style={{ ...LEYENDA, gap: 12, fontSize: 12 }}>
          {LEYENDA_PUNTOS.map(([texto, color]) => (
            <span key={texto} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 999, background: color }} />{texto}
            </span>
          ))}
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <Scatter
          points={d.puntos} xDomain={d.xDomain} yDomain={d.yDomain} quadrant={d.quadrant} highlight={d.destacados}
          xTicks={d.xTicks} yTicks={d.yTicks} xLabel={`Venta ${periodoCorto(data.meses)} →`} ariaLabel="Venta vs margen"
          cornerLabels={{ topRight: 'Alta venta · alto margen', bottomLeft: 'Baja venta · bajo margen' }}
        />
      </div>
      {d.sinCosto > 0 && (
        <p style={{ margin: '8px 0 0', fontSize: 11.5, color: COLOR.muted }}>
          {d.sinCosto} {d.sinCosto === 1 ? 'tienda sin costo no aparece' : 'tiendas sin costo no aparecen'} en el gráfico.
        </p>
      )}
    </section>
  );
}

/** Bottom grid: monthly sales against each store's own average, and sales against margin. */
export default function VentaMensualYMargen({ data }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16 }}>
      <MapaDeCalor data={data} />
      <Dispersion data={data} />
    </div>
  );
}
