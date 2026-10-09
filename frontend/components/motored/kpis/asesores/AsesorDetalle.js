import { Chip } from '../charts';
import { COLOR } from '../tokens';
import { EtiquetaConTip } from '../ventas/CumplimientoTop';
import { NUM, ROTULO, TARJETA } from '../ventas/estilos';
import DetalleComision from './DetalleComision';
import DetalleComparacion from './DetalleComparacion';
import DetalleMeta from './DetalleMeta';
import DetalleTendencia from './DetalleTendencia';
import PendientesAsesor from './PendientesAsesor';
import { fichaDe, tilesDe } from './detalle';

function Ficha({ data }) {
  const f = fichaDe(data);
  return (
    <section aria-label="Ficha del asesor" style={{ ...TARJETA, display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', minWidth: 0 }}>
        <div
          aria-hidden="true"
          style={{ width: 56, height: 56, flex: 'none', borderRadius: 999, background: COLOR.infoSoft, color: '#1A4577', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 19, fontWeight: 700 }}
        >
          {f.iniciales}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-.01em' }}>{f.nombre}</h2>
            {f.tramo && <span style={{ fontSize: 12, fontWeight: 700, color: '#FFFFFF', background: f.tramo.color, borderRadius: 999, padding: '3px 10px' }}>{f.tramo.texto}</span>}
          </div>
          <p style={{ margin: 0, fontSize: 13, color: COLOR.muted }}>{f.partes.join(' · ')}</p>
        </div>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {f.puestos.map((p) => (
          <div key={p.label} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '10px 14px', borderRadius: 12, background: COLOR.wash, minWidth: 130 }}>
            <span style={{ ...ROTULO, fontSize: 11 }}><EtiquetaConTip label={p.label} tip={p.tip} /></span>
            <span style={{ ...NUM, fontSize: 18, fontWeight: 700 }}>{p.val}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Tiles({ data }) {
  return (
    <section aria-label="Indicadores del asesor" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 16 }}>
      {tilesDe(data).map((t) => (
        <div key={t.id} style={{ ...TARJETA, padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ ...ROTULO, fontSize: 11 }}><EtiquetaConTip label={t.label} tip={t.tip} /></span>
          <span style={{ ...NUM, fontSize: 22, fontWeight: 700 }}>{t.valor}</span>
          {t.chip && <span style={{ alignSelf: 'flex-start' }}><Chip text={t.chip.text} variant={t.chip.variant} /></span>}
          <span style={{ fontSize: 11.5, color: COLOR.muted }}>{t.ref}</span>
        </div>
      ))}
    </section>
  );
}

/** "Un asesor" view of the Asesores tab (`enlace` = `{ token, cedula }` on the public link, which also answers the pending invoices and transfers): ficha, goal gauge and commission, six figures, trend, lines, peers, store, Tecnired and how the commission is calculated. */
export default function AsesorDetalle({ data, enlace }) {
  return (
    <section aria-label="Detalle del asesor" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      <Ficha data={data} />
      <DetalleMeta data={data} />
      <PendientesAsesor data={data} enlace={enlace} />
      <Tiles data={data} />
      <DetalleTendencia data={data} />
      <DetalleComparacion data={data} />
      <DetalleComision data={data} />
    </section>
  );
}
