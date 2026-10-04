/** Tiendas tab, in the design's order: trend + figures, zone strip, ranking, monthly heatmap and sales vs margin. */
import ZonaTiendas from '../ventas/ZonaTiendas';
import RankingTiendas from './RankingTiendas';
import TendenciaTop from './TendenciaTop';
import VentaMensualYMargen from './VentaMensualYMargen';

export default function TiendasTab({ data }) {
  return (
    <section aria-label="Tiendas" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      <TendenciaTop data={data} />
      <ZonaTiendas data={data} />
      <RankingTiendas data={data} />
      <VentaMensualYMargen data={data} />
    </section>
  );
}
