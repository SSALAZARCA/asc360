'use client';
/**
 * References x tiendas matrix (consolidated network view). The first column
 * (code and name) stays in view while the 47 tienda columns scroll sideways
 * inside the box; the header row stays in view while the references scroll.
 * Each column shows the state of its tienda and, in the footer, what that
 * tienda orders over the WHOLE corrida (not only this page). A tienda without
 * calculation (FALLIDA, OMITIDA) is flagged and has no figures.
 */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import { formatCOP } from '../../../lib/motored/formatCOP';
import EncabezadoTienda, { ANCHO_TIENDA, sinPedido } from './ConsolidadoColumna';
import { unidades, valorCompacto } from './formato';
import { numStyle, stickyColStyle, stickyHeadStyle, tablaStyle, tdCompactStyle, thCompactStyle } from './styles';

const ANCHO_PRIMERA = 180;
const ANCHO_TOTAL = 76;
const TOTAL_TEXTO = 'Total: lo que se pide de la referencia en todas las tiendas (cantidad a pedir, no el sugerido).';

// The sticky first column casts a soft shadow on the cells that scroll under it.
const sombra = { boxShadow: '6px 0 8px -6px rgba(0, 0, 0, 0.18)' };
const izquierda = { textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
const pegadaEncabezado = { ...stickyColStyle, ...sombra, zIndex: 4, top: 0 };
const celdaNumero = { ...tdCompactStyle, ...numStyle, padding: '6px 2px' };

function EncabezadoPrimera() {
  return <th style={{ ...thCompactStyle, ...stickyHeadStyle, ...pegadaEncabezado, width: `${ANCHO_PRIMERA}px` }}><div style={izquierda}>Referencia</div></th>;
}

function EncabezadoTotal() {
  return (
    <th style={{ ...thCompactStyle, ...stickyHeadStyle, width: `${ANCHO_TOTAL}px`, padding: '0 2px 8px' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>Total<InfoTooltip text={TOTAL_TEXTO} /></span>
    </th>
  );
}

function FilaReferencia({ fila, tiendas }) {
  return (
    <tr>
      <td style={{ ...tdCompactStyle, ...stickyColStyle, ...sombra, width: `${ANCHO_PRIMERA}px` }}>
        <div style={izquierda} title={`${fila.codigo} ${fila.nombre || ''}`.trim()}>
          <strong>{fila.codigo}</strong>
          <div style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.nombre}</div>
        </div>
      </td>
      <td style={{ ...celdaNumero, fontWeight: 700 }}>{unidades(fila.total)}</td>
      {tiendas.map((t) => {
        const cantidad = fila.celdas[t.sucursal_id];
        return <td key={t.sucursal_id} style={celdaNumero}>{cantidad ? unidades(cantidad) : null}</td>;
      })}
    </tr>
  );
}

function Pie({ tiendas, totales }) {
  const base = { ...celdaNumero, fontWeight: 700, borderTop: '1px solid var(--motored-border, #e4e4e7)' };
  const etiqueta = { ...base, ...stickyColStyle, ...sombra, width: `${ANCHO_PRIMERA}px` };
  return (
    <tfoot>
      <tr>
        <td style={etiqueta}><div style={izquierda}>Unidades</div></td>
        <td style={base}>{unidades(totales.unidades)}</td>
        {tiendas.map((t) => <td key={t.sucursal_id} style={base}>{sinPedido(t) ? '—' : unidades(t.unidades)}</td>)}
      </tr>
      <tr>
        <td style={{ ...etiqueta, borderTop: 'none' }}><div style={izquierda}>Valor</div></td>
        <td style={{ ...base, borderTop: 'none' }} title={formatCOP(totales.valor)}>{valorCompacto(totales.valor)}</td>
        {tiendas.map((t) => (
          <td key={t.sucursal_id} style={{ ...base, borderTop: 'none', fontSize: '0.7rem' }} title={sinPedido(t) ? undefined : `Valor de ${t.nombre}: ${formatCOP(t.valor)}`}>
            {sinPedido(t) ? '—' : valorCompacto(t.valor)}
          </td>
        ))}
      </tr>
    </tfoot>
  );
}

export default function ConsolidadoMatrix({ tiendas, filas, totales }) {
  const ancho = ANCHO_PRIMERA + ANCHO_TOTAL + ANCHO_TIENDA * tiendas.length;
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table aria-label="Consolidado de la red" style={{ ...tablaStyle, width: `${ancho}px`, tableLayout: 'fixed', borderCollapse: 'collapse', fontSize: '13px' }}>
        <colgroup>
          <col style={{ width: `${ANCHO_PRIMERA}px` }} />
          <col style={{ width: `${ANCHO_TOTAL}px` }} />
          {tiendas.map((t) => <col key={t.sucursal_id} style={{ width: `${ANCHO_TIENDA}px` }} />)}
        </colgroup>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <EncabezadoPrimera />
            <EncabezadoTotal />
            {tiendas.map((t) => <EncabezadoTienda key={t.sucursal_id} tienda={t} />)}
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => <FilaReferencia key={f.referencia_id} fila={f} tiendas={tiendas} />)}
        </tbody>
        <Pie tiendas={tiendas} totales={totales} />
      </table>
    </MotoredTableScroll>
  );
}
