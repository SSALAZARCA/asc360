'use client';
/**
 * The advisor table: one row per person or consolidated group plus a TOTAL row.
 * The first three columns (punto de venta, asesor, cargo) stay fixed while the
 * rest scrolls sideways inside `MotoredTableScroll`. On a tablet (under
 * 1024px) three fixed columns (610px) would leave no room for the data, so
 * there only the asesor stays fixed (and goes first); the other two scroll.
 */
import { useEffect, useState } from 'react';
import MotoredTableScroll from '../MotoredTableScroll';
import InfoTooltip from '../InfoTooltip';
import { construirGrupos } from './columnas';

const FIJAS = ['Punto de venta', 'Asesor / grupo', 'Cargo'];
const CONSULTA_ESTRECHA = '(max-width: 1023px)';
// `orden` indexes FIJAS; `fija` and `anchos` follow `orden`.
const DISPOSICION_ANCHA = { orden: [0, 1, 2], fija: [true, true, true], anchos: [150, 250, 210] };
const DISPOSICION_ESTRECHA = { orden: [1, 0, 2], fija: [true, false, false], anchos: [140, 110, 170] };

const consultarEstrecha = () => (
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(CONSULTA_ESTRECHA) : null
);

/** The table only mounts after the data loads (client side), so the first render can already read the media query. */
function useEsEstrecha() {
  const [estrecha, setEstrecha] = useState(() => Boolean(consultarEstrecha()?.matches));
  useEffect(() => {
    const consulta = consultarEstrecha();
    if (!consulta) return undefined;
    const actualizar = () => setEstrecha(consulta.matches);
    consulta.addEventListener('change', actualizar);
    return () => consulta.removeEventListener('change', actualizar);
  }, []);
  return estrecha;
}

const base = { padding: '6px 10px', whiteSpace: 'nowrap', textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontSize: '0.75rem' };
const fondo = 'var(--motored-surface, #ffffff)';
const borde = '1px solid var(--motored-border, #e4e4e7)';

/** Style of the fixed-block cell at `posicion` (0 = leftmost) for the given layout. */
function fijaStyle(disposicion, posicion, extra = {}) {
  const ancho = disposicion.anchos[posicion];
  const recortado = { width: ancho, minWidth: ancho, maxWidth: ancho, overflow: 'hidden', textOverflow: 'ellipsis' };
  if (!disposicion.fija[posicion]) return { ...base, textAlign: 'left', background: fondo, ...recortado, ...extra };
  const izquierda = disposicion.anchos.slice(0, posicion).reduce((suma, a, i) => suma + (disposicion.fija[i] ? a : 0), 0);
  return { ...base, textAlign: 'left', position: 'sticky', left: izquierda, zIndex: 2, background: fondo, ...recortado, ...extra };
}

function Encabezado({ grupos, disposicion }) {
  return (
    <thead>
      <tr>
        {disposicion.orden.map((indice, posicion) => (
          <th key={FIJAS[indice]} rowSpan={2} style={fijaStyle(disposicion, posicion, { zIndex: 4, borderBottom: borde })}>
            {FIJAS[indice]}
          </th>
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

function Fila({ fila, grupos, disposicion }) {
  const total = fila.tipo === 'TOTAL';
  const estilo = total ? { fontWeight: 700, background: 'var(--motored-surface-alt, #f4f4f5)' } : {};
  const textos = [fila.punto_venta || '', fila.nombre, fila.cargo || ''];
  return (
    <tr style={estilo}>
      {disposicion.orden.map((indice, posicion) => (
        <td key={FIJAS[indice]} title={textos[indice]} style={fijaStyle(disposicion, posicion, { ...estilo, borderBottom: borde })}>
          {textos[indice]}
        </td>
      ))}
      {grupos.flatMap((g) => g.columnas.map((c, i) => (
        <td key={c.id} style={{ ...base, borderBottom: borde, borderLeft: i === 0 ? borde : undefined }}>{c.render(fila)}</td>
      )))}
    </tr>
  );
}

export default function TableroTable({ filas, total, meses }) {
  const grupos = construirGrupos(meses);
  const disposicion = useEsEstrecha() ? DISPOSICION_ESTRECHA : DISPOSICION_ANCHA;
  return (
    <MotoredTableScroll>
      <table style={{ borderCollapse: 'separate', borderSpacing: 0, background: fondo }}>
        <Encabezado grupos={grupos} disposicion={disposicion} />
        <tbody>
          {filas.map((fila) => <Fila key={fila.clave} fila={fila} grupos={grupos} disposicion={disposicion} />)}
          <Fila fila={total} grupos={grupos} disposicion={disposicion} />
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
