/** Asesores tab, in the design's order: goal donut + figures, zone strip, top/bottom 10, Tecnired and groups. */
import CumplenTop from './CumplenTop';
import DestacadosYApoyar from './DestacadosYApoyar';
import GrupoVendedores from './GrupoVendedores';
import TecniredAsesores from './TecniredAsesores';
import ZonaAsesores from './ZonaAsesores';

export default function AsesoresTab({ data }) {
  return (
    <section aria-label="Asesores" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      <CumplenTop data={data} />
      <ZonaAsesores data={data} />
      <DestacadosYApoyar data={data} />
      <TecniredAsesores data={data} />
      <GrupoVendedores data={data} />
    </section>
  );
}
