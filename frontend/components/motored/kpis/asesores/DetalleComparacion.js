import { Chip, ZoneStrip } from '../charts';
import { COLOR } from '../tokens';
import { CABECERA, NUM, ROTULO, TARJETA, TITULO } from '../ventas/estilos';
import { colorDeTramo, comparacionDe, mesNombre, stripDe, tecniredDe, tramoActual, tramosDe } from './detalle';

const CELDA = { padding: 10, textAlign: 'right', borderBottom: `1px solid ${COLOR.wash}`, ...NUM };
const ENCABEZADO = { ...ROTULO, fontSize: 11, fontWeight: 700, textAlign: 'right', padding: '8px 10px', borderBottom: `1px solid ${COLOR.track}` };

function TarjetaStrip({ data }) {
  const s = stripDe(data);
  const tramo = tramoActual(data);
  const color = tramo ? colorDeTramo(tramo, tramosDe(data)) : COLOR.info;
  return (
    <section aria-label="Dónde está frente a sus compañeros" style={TARJETA}>
      <div style={CABECERA}>
        <h3 style={TITULO}>Dónde está frente a sus compañeros · cumplimiento {mesNombre(data)}</h3>
        <span style={{ fontSize: 12.5, color: COLOR.muted }}>{s.total} asesores de la red · cada punto es una persona</span>
      </div>
      <ZoneStrip
        dots={s.otros.map((v) => ({ value: v * 100, color: COLOR.line, tip: `${(v * 100).toFixed(1).replace('.', ',')}%` }))}
        min={s.min} max={s.max} zones={s.zonas} lines={s.cortes} ticks={s.ticks} ariaLabel="Cumplimiento de sus compañeros"
        highlight={s.yo ? { value: s.yo.value, label: `Este asesor · ${s.yo.label}`, color, tip: `${data.asesor.nombre} · ${s.yo.label}` } : undefined}
      />
      <p style={{ margin: '10px 0 0', fontSize: 12.5, color: COLOR.muted }}>{s.texto}</p>
    </section>
  );
}

function TarjetaComparacion({ data }) {
  const c = comparacionDe(data);
  return (
    <section aria-label="Comparación con su tienda" style={TARJETA}>
      <h3 style={TITULO}>Comparación con su tienda</h3>
      <p style={{ margin: '4px 0 0', fontSize: 12.5, color: COLOR.muted }}>{c.sub}</p>
      <div style={{ overflowX: 'auto', marginTop: 10 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 380 }}>
          <thead>
            <tr>
              <th scope="col" style={{ ...ENCABEZADO, textAlign: 'left' }}>Indicador</th>
              <th scope="col" style={{ ...ENCABEZADO, color: '#1A4577' }}>Este asesor</th>
              <th scope="col" style={ENCABEZADO}>Prom. su tienda</th>
              <th scope="col" style={ENCABEZADO}>Prom. red</th>
            </tr>
          </thead>
          <tbody>
            {c.filas.map((f) => (
              <tr key={f.label}>
                <td style={{ ...CELDA, textAlign: 'left', fontWeight: 700 }}>{f.label}</td>
                <td style={{ ...CELDA, fontWeight: 700, color: '#1A4577' }}>{f.yo}</td>
                <td style={CELDA}>{f.tienda}</td>
                <td style={CELDA}>{f.red}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TarjetaTecnired({ data }) {
  const t = tecniredDe(data);
  return (
    <section aria-label="Clientes Tecnired atendidos" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ ...CABECERA, gap: 8 }}>
        <h3 style={TITULO}>Clientes Tecnired atendidos</h3>
        {t.chip && <Chip text={t.chip.text} variant={t.chip.variant} />}
      </div>
      {t.vacio ? <p style={{ margin: 0, fontSize: 12.5, color: COLOR.muted }}>En estos meses no le vendió a clientes Tecnired.</p> : (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {t.fichas.map((f) => (
              <span key={f.label} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '6px 10px', borderRadius: 10, background: COLOR.infoSoft }}>
                <strong style={{ ...NUM, fontSize: 15, color: '#1A4577' }}>{f.value}</strong>
                <span style={{ fontSize: 11.5, color: COLOR.ink2 }}>{f.label}</span>
              </span>
            ))}
          </div>
          {t.top.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: COLOR.soft, textTransform: 'uppercase', letterSpacing: '.04em' }}>Top {t.top.length} por venta</span>
              {t.top.map((c) => (
                <div key={c.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 90px 62px', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 12.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</span>
                  <div style={{ height: 10, background: COLOR.wash, borderRadius: 999 }}><div style={{ height: 10, width: c.w, background: '#3570B0', borderRadius: 999 }} /></div>
                  <span style={{ ...NUM, fontSize: 12.5, fontWeight: 700, textAlign: 'right' }}>{c.val}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** Her position among her peers, the comparison with her store and the Tecnired clients she attends. */
export default function DetalleComparacion({ data }) {
  return (
    <>
      <TarjetaStrip data={data} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))', gap: 16 }}>
        <TarjetaComparacion data={data} />
        <TarjetaTecnired data={data} />
      </div>
    </>
  );
}
