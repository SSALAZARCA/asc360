'use client';
/** Three separate stat boxes with the totals of the whole corrida, styled like the KPI indicator tiles; they wrap on a tablet. */
import InfoTooltip from '../InfoTooltip';
import { COLOR } from '../kpis/tokens';
import { cifrasTotales } from './totales';

const filaStyle = { display: 'flex', flexWrap: 'wrap', gap: 10 };
const cajaStyle = { flex: '1 1 180px', background: COLOR.wash, borderRadius: 10, padding: '10px 12px', minWidth: 0 };
const etiquetaStyle = {
  margin: 0, display: 'inline-flex', alignItems: 'center', fontSize: 11.5, fontWeight: 500,
  letterSpacing: '.04em', textTransform: 'uppercase', color: COLOR.muted,
};
const cifraStyle = { margin: '4px 0 0', fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: COLOR.ink };

export default function TotalesCorrida({ totales }) {
  return (
    <div style={filaStyle}>
      {cifrasTotales(totales).map((cifra) => (
        <div key={cifra.clave} role="group" aria-label={cifra.label} style={cajaStyle}>
          <p style={etiquetaStyle}>
            {cifra.label}
            <InfoTooltip text={cifra.ayuda} />
          </p>
          <p style={cifraStyle}>{cifra.valor}</p>
        </div>
      ))}
    </div>
  );
}
