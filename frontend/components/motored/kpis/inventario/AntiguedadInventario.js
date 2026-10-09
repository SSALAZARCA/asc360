'use client';
/** "Antigüedad del inventario": stacked bar + legend rows by days since the last sale, with the idle callout. */
import InfoTooltip from '../../InfoTooltip';
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { bandasEdad, pesosM, TIP_HISTORIAL } from './datos';
import { PUNTO, SUBTITULO, TARJETA_COLUMNA } from './estilos';

function FilaBanda({ banda, historial }) {
  return (
    <div data-testid="banda-edad" style={{ display: 'grid', gridTemplateColumns: '12px minmax(0, 1fr) auto 52px', gap: 10, alignItems: 'center' }}>
      <span style={{ ...PUNTO(banda.color), width: 12, height: 12 }} />
      <span style={{ fontSize: 13, color: COLOR.ink }}>
        {banda.label} {banda.ultima && <InfoTooltip text={TIP_HISTORIAL(historial)} />}
      </span>
      <span style={{ ...NUM, fontSize: 13, fontWeight: 700 }}>{banda.valor}</span>
      <span style={{ ...NUM, fontSize: 12, color: COLOR.muted, textAlign: 'right' }}>{banda.pct}</span>
    </div>
  );
}

export default function AntiguedadInventario({ data }) {
  const bandas = bandasEdad(data);
  const historial = data.antiguedad.historial_desde;
  const { sin_movimiento: quieto } = data.tarjetas;
  return (
    <section aria-label="Antigüedad del inventario" style={{ ...TARJETA, ...TARJETA_COLUMNA }}>
      <div>
        <h2 style={TITULO}>Antigüedad del inventario</h2>
        <p style={SUBTITULO}>Días desde la última venta de cada referencia en la tienda</p>
      </div>
      <div role="img" aria-label="Distribución del inventario por antigüedad" style={{ display: 'flex', height: 22, borderRadius: 8, overflow: 'hidden' }}>
        {bandas.map((b) => (
          <div key={b.label} title={`${b.label}: ${b.valor}${b.ultima ? ` · ${TIP_HISTORIAL(historial)}` : ''}`} style={{ width: b.ancho, background: b.color }} />
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {bandas.map((b) => <FilaBanda key={b.label} banda={b} historial={historial} />)}
      </div>
      {quieto.valor > 0 && (
        <p style={{ margin: 0, fontSize: 12.5, color: COLOR.ink2, background: COLOR.badSoft, borderRadius: 10, padding: '10px 12px' }}>
          <strong>{pesosM(quieto.valor)}</strong> llevan más de {data.sin_movimiento_umbral_dias} días sin venderse: candidatos a traslado entre tiendas o liquidación.
        </p>
      )}
    </section>
  );
}
