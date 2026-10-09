'use client';
/** "Inventario por línea": value at cost, share bar, days chip, rotation and availability of each line. */
import { pct } from '../format';
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { diasTexto, luzDias, pesosM, rotacionTexto } from './datos';
import { SUBTITULO, TARJETA_COLUMNA } from './estilos';

export function ChipDias({ dias, cortes }) {
  const luz = luzDias(dias, cortes);
  return <span style={{ ...NUM, fontSize: 12, fontWeight: 700, color: luz.fg, background: luz.bg, borderRadius: 999, padding: '2px 8px' }}>{diasTexto(dias)}</span>;
}

function FilaLinea({ fila, tope, cortes }) {
  return (
    <div data-testid="fila-linea" className="inv-lrow" style={{ fontSize: 13, padding: '6px 0', borderTop: '1px solid #F0F0EE' }}>
      <span style={{ fontWeight: 700 }}>{fila.linea}</span>
      <span style={NUM}>{pesosM(fila.valor)}</span>
      <span className="inv-oc" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ flex: 1, height: 8, background: '#ECECE9', borderRadius: 999 }}>
          <span style={{ display: 'block', width: `${((fila.valor / tope) * 100).toFixed(1)}%`, height: 8, background: COLOR.info, borderRadius: 999 }} />
        </span>
        <span style={{ ...NUM, fontSize: 12, color: COLOR.muted, width: 40, textAlign: 'right' }}>{pct(fila.pct, 1)}</span>
      </span>
      <span style={{ textAlign: 'right' }}><ChipDias dias={fila.dias} cortes={cortes} /></span>
      <span className="inv-oc" style={{ ...NUM, textAlign: 'right' }}>{rotacionTexto(fila.rotacion)}</span>
      <span className="inv-oc" style={{ ...NUM, textAlign: 'right' }}>{pct(fila.disponibilidad_pct, 1)}</span>
    </div>
  );
}

const CABECERA_LINEA = { fontSize: 11, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase', color: COLOR.muted };

export default function InventarioPorLinea({ data }) {
  const tope = Math.max(...data.lineas.map((l) => l.valor), 1);
  return (
    <section aria-label="Inventario por línea" style={{ ...TARJETA, ...TARJETA_COLUMNA }}>
      <div>
        <h2 style={TITULO}>Inventario por línea</h2>
        <p style={SUBTITULO}>Valor a costo, participación y días de inventario de cada línea comercial</p>
      </div>
      <div className="inv-lrow inv-thead" style={CABECERA_LINEA}>
        <span>Línea</span><span>Valor</span><span className="inv-oc">Participación</span>
        <span style={{ textAlign: 'right' }}>Días</span>
        <span className="inv-oc" style={{ textAlign: 'right' }}>Rotación</span>
        <span className="inv-oc" style={{ textAlign: 'right' }}>Disponib.</span>
      </div>
      {data.lineas.map((l) => <FilaLinea key={l.linea} fila={l} tope={tope} cortes={data.cortes_color} />)}
    </section>
  );
}
