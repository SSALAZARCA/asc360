/** Asesores tab, in the design's order: goal donut + figures, zone strip, top/bottom 10, Tecnired and groups. */
import { COLOR } from '../tokens';
import CumplenTop from './CumplenTop';
import DestacadosYApoyar from './DestacadosYApoyar';
import GrupoVendedores from './GrupoVendedores';
import TecniredAsesores from './TecniredAsesores';
import ZonaAsesores from './ZonaAsesores';

/** The hint of the "everyone" view: the detail is one click away (the filter or any name of the lists). */
function Pista() {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: '#1A4577', background: COLOR.infoSoft, borderRadius: 999, padding: '6px 12px' }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="8" r="4" /><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
        </svg>
        Elegí un asesor para ver su detalle
      </span>
      <span style={{ fontSize: 12.5, color: COLOR.muted }}>Desde el filtro Asesor o tocando cualquier nombre de las listas.</span>
    </div>
  );
}

export default function AsesoresTab({ data, onAsesor }) {
  return (
    <section aria-label="Asesores" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      {onAsesor && <Pista />}
      <CumplenTop data={data} />
      <ZonaAsesores data={data} />
      <DestacadosYApoyar data={data} onAsesor={onAsesor} />
      <TecniredAsesores data={data} onAsesor={onAsesor} />
      <GrupoVendedores data={data} />
    </section>
  );
}
