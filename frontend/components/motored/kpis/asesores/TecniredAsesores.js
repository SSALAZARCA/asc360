import { Treemap } from '../charts';
import { pct } from '../format';
import { periodoCorto } from '../periodo';
import { CATEGORIA, COLOR } from '../tokens';
import { CABECERA, NUM, TARJETA, TITULO } from '../ventas/estilos';
import { tecniredAsesores, tonoTecnired } from './datos';

function Fichas({ kpis }) {
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
      {kpis.map((k) => (
        <span key={k.label} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '6px 10px', borderRadius: 10, background: COLOR.infoSoft }}>
          <strong style={{ ...NUM, fontSize: 15, color: '#1A4577' }}>{k.value}</strong>
          <span style={{ fontSize: 11.5, color: COLOR.ink2 }}>{k.label}</span>
        </span>
      ))}
    </div>
  );
}

function Mapa({ tiles }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', fontSize: 11.5, color: COLOR.muted, marginBottom: 6 }}>
        <span>Tamaño = venta a Tecnired</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          % de su venta <span style={{ width: 60, height: 8, borderRadius: 999, background: `linear-gradient(90deg, ${CATEGORIA[6]}, ${CATEGORIA[0]})` }} />
        </span>
      </div>
      <Treemap items={tiles} colorScale={tonoTecnired} aspect={1.6} ariaLabel="Venta a Tecnired por asesor" />
    </div>
  );
}

function Barras({ filas, promedio, maximo }) {
  const izquierda = promedio === null ? null : `${Math.min((promedio / maximo) * 100, 100).toFixed(1)}%`;
  return (
    <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>% de la venta que va a Tecnired</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 300, overflowY: 'auto', paddingRight: 6 }}>
        {filas.map((f) => (
          <div key={f.id} data-testid="tecnired-fila" style={{ display: 'grid', gridTemplateColumns: 'minmax(100px, 150px) minmax(0, 1fr) 46px', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</span>
            <div style={{ position: 'relative', height: 12, background: COLOR.wash, borderRadius: 999 }}>
              <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min((f.pct / maximo) * 100, 100).toFixed(1)}%`, background: tonoTecnired(f.pct).bg, borderRadius: 999 }} />
              {izquierda && <span data-testid="tecnired-promedio" style={{ position: 'absolute', left: izquierda, top: -4, bottom: -4, width: 2, background: COLOR.ink }} />}
            </div>
            <span style={{ ...NUM, fontSize: 12, fontWeight: 700, textAlign: 'right' }}>{pct(f.pct)}</span>
          </div>
        ))}
      </div>
      {promedio !== null && (
        <span style={{ fontSize: 11.5, color: COLOR.muted, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 2, height: 12, background: COLOR.ink }} />Promedio de la red {pct(promedio)}
        </span>
      )}
    </div>
  );
}

/** "Tecnired por asesor": chips, treemap of the sales to Tecnired and the share of each asesor's sales. */
export default function TecniredAsesores({ data }) {
  const t = tecniredAsesores(data);
  return (
    <section aria-label="Tecnired por asesor" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Tecnired por asesor · {periodoCorto(data.meses)}</h2>
        <Fichas kpis={t.kpis} />
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 18, marginTop: 14 }}>
        <div style={{ flex: '1.5 1 340px', minWidth: 0 }}><Mapa tiles={t.tiles} /></div>
        <div style={{ flex: '1 1 280px', minWidth: 0 }}><Barras filas={t.filas} promedio={t.promedio} maximo={t.maximo} /></div>
      </div>
    </section>
  );
}
