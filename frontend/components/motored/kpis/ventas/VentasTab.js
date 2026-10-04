/** Ventas tab, in the design's order: gauge + figures, zone strip, compliance per store, sales by line, Tecnired. */
import CumplimientoPorTienda from './CumplimientoPorTienda';
import CumplimientoTop from './CumplimientoTop';
import TecniredSection from './TecniredSection';
import VentaPorLinea from './VentaPorLinea';
import ZonaTiendas from './ZonaTiendas';

export default function VentasTab({ data }) {
  return (
    <section aria-label="Ventas" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      <CumplimientoTop data={data} />
      <ZonaTiendas data={data} />
      <CumplimientoPorTienda data={data} />
      <VentaPorLinea data={data} />
      <TecniredSection data={data} />
    </section>
  );
}
