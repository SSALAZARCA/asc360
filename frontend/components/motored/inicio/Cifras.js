'use client';
/**
 * Inicio: the four stat boxes, styled like the KPI indicator tiles (the corrida totals boxes). A real
 * heading per box, a one-line tooltip, and a grid that wraps on tablet and phone. While loading, the
 * boxes keep their titles and show a skeleton bar instead of the figure.
 */
import InfoTooltip from '../InfoTooltip';
import { COLOR } from '../kpis/tokens';
import { NO_DISPONIBLE } from './textos';

const grilla = {
  display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))',
};
const cajaStyle = {
  display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0, minHeight: 112, boxSizing: 'border-box',
  background: COLOR.wash, borderRadius: 10, padding: '14px 16px',
};
const cabecera = { display: 'flex', alignItems: 'center', gap: 2 };
const tituloStyle = {
  margin: 0, fontSize: 11.5, fontWeight: 600, letterSpacing: '.04em', textTransform: 'uppercase',
  color: COLOR.muted,
};
const cifraStyle = {
  margin: '6px 0 0', fontSize: 26, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: COLOR.ink,
  overflowWrap: 'anywhere',
};
const subtituloStyle = { margin: 0, fontSize: 12.5, color: COLOR.muted };
const sinDatoStyle = { margin: '6px 0 0', fontSize: 14, color: COLOR.muted };
const esqueletoStyle = { marginTop: 10, height: 26, width: '70%', borderRadius: 6, background: COLOR.track };

function Valor({ figura, cargando }) {
  if (cargando) return <div aria-hidden="true" style={esqueletoStyle} />;
  if (figura.valor == null) return <p style={sinDatoStyle}>{NO_DISPONIBLE}</p>;
  return (
    <>
      <p style={cifraStyle}>{figura.valor}</p>
      {figura.subtitulo && <p style={subtituloStyle}>{figura.subtitulo}</p>}
    </>
  );
}

function Caja({ figura, cargando }) {
  const id = `inicio-${figura.id}`;
  return (
    <section aria-labelledby={id} style={cajaStyle}>
      <div style={cabecera}>
        <h2 id={id} style={tituloStyle}>{figura.titulo}</h2>
        <InfoTooltip text={figura.ayuda} />
      </div>
      <Valor figura={figura} cargando={cargando} />
    </section>
  );
}

export default function Cifras({ figuras, cargando }) {
  const estado = cargando
    ? { 'data-testid': 'inicio-cargando', 'aria-busy': 'true' }
    : { 'data-testid': 'inicio-cifras' };
  return (
    <div {...estado} style={grilla}>
      {figuras.map((figura) => <Caja key={figura.id} figura={figura} cargando={cargando} />)}
    </div>
  );
}
