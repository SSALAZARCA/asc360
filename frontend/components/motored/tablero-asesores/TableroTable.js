'use client';
/**
 * The advisor table: one row per person or consolidated group plus a TOTAL
 * row. The first three columns (punto de venta, asesor, cargo) stay fixed
 * while the rest scrolls sideways inside `MotoredTableScroll`.
 */
import MotoredTableScroll from '../MotoredTableScroll';
import InfoTooltip from '../InfoTooltip';
import { construirGrupos } from './columnas';

const ANCHOS = [150, 250, 210];
const IZQUIERDA = [0, ANCHOS[0], ANCHOS[0] + ANCHOS[1]];
const FIJAS = ['Punto de venta', 'Asesor / grupo', 'Cargo'];

const base = { padding: '6px 10px', whiteSpace: 'nowrap', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem' };
const fondo = 'var(--motored-surface, #ffffff)';
const borde = '1px solid var(--motored-border, #e4e4e7)';

const fijaStyle = (i, extra = {}) => ({
  ...base, textAlign: 'left', position: 'sticky', left: IZQUIERDA[i], zIndex: 2, background: fondo,
  width: ANCHOS[i], minWidth: ANCHOS[i], maxWidth: ANCHOS[i], overflow: 'hidden', textOverflow: 'ellipsis', ...extra,
});

function Encabezado({ grupos }) {
  return (
    <thead>
      <tr>
        {FIJAS.map((texto, i) => (
          <th key={texto} rowSpan={2} style={fijaStyle(i, { zIndex: 4, borderBottom: borde })}>{texto}</th>
        ))}
        {grupos.map((g) => (
          <th key={g.id} colSpan={g.columnas.length} style={{ ...base, textAlign: 'center', borderLeft: borde, borderBottom: borde }}>
            {g.label}
          </th>
        ))}
      </tr>
      <tr>
        {grupos.flatMap((g) => g.columnas.map((c, i) => (
          <th key={c.id} style={{ ...base, borderBottom: borde, borderLeft: i === 0 ? borde : undefined, fontWeight: 600 }}>
            {c.label}
            {c.tip && <>{' '}<InfoTooltip text={c.tip} /></>}
          </th>
        )))}
      </tr>
    </thead>
  );
}

function Fila({ fila, grupos }) {
  const total = fila.tipo === 'TOTAL';
  const estilo = total ? { fontWeight: 700, background: 'var(--motored-surface-alt, #f4f4f5)' } : {};
  const textos = [fila.punto_venta || '', fila.nombre, fila.cargo || ''];
  return (
    <tr style={estilo}>
      {textos.map((texto, i) => (
        <td key={FIJAS[i]} title={texto} style={fijaStyle(i, { ...estilo, borderBottom: borde })}>{texto}</td>
      ))}
      {grupos.flatMap((g) => g.columnas.map((c, i) => (
        <td key={c.id} style={{ ...base, borderBottom: borde, borderLeft: i === 0 ? borde : undefined }}>{c.render(fila)}</td>
      )))}
    </tr>
  );
}

export default function TableroTable({ filas, total, meses }) {
  const grupos = construirGrupos(meses);
  return (
    <MotoredTableScroll>
      <table style={{ borderCollapse: 'separate', borderSpacing: 0, background: fondo }}>
        <Encabezado grupos={grupos} />
        <tbody>
          {filas.map((fila) => <Fila key={fila.clave} fila={fila} grupos={grupos} />)}
          <Fila fila={total} grupos={grupos} />
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
