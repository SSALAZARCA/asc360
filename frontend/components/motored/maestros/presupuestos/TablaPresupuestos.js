'use client';
/**
 * The month's budgets as one flat table: one row per asesor (sorted by tienda,
 * then asesor), one column per active bonus line with the asesor's minimum
 * sale for that line, and a totals row. Edit and remove call back into the tab.
 */
import { formatCOP } from '../../../../lib/motored/formatCOP';
import MotoredTableScroll from '../../MotoredTableScroll';
import InfoTooltip from '../../InfoTooltip';
import { tablaStyle, thStyle, tdStyle, filaStyle } from './formato';

// Tienda and asesor names must stay readable when the table scrolls sideways.
const nombreStyle = { ...tdStyle, whiteSpace: 'nowrap', minWidth: '8rem' };
const montoStyle = { ...tdStyle, whiteSpace: 'nowrap', textAlign: 'right' };
const montoThStyle = { ...thStyle, whiteSpace: 'nowrap', textAlign: 'right' };
const totalStyle = { ...filaStyle, fontWeight: 600 };

const porcentaje = (valor) => Number(valor).toLocaleString('es-CO', { maximumFractionDigits: 2 });

/** Lines sorted by tienda, then asesor, without mutating the server's list. */
export function ordenarLineas(lineas) {
  return [...lineas].sort((a, b) => a.tienda.localeCompare(b.tienda, 'es')
    || a.asesor.localeCompare(b.asesor, 'es'));
}

/** Help text of one bonus line column: how the minimum is computed and when the bonus applies. */
export function textoAyudaLinea(lineaBono, umbral) {
  const u = porcentaje(umbral);
  const meta = porcentaje(lineaBono.pct_meta);
  return [
    `Venta mínima de la línea para ganar el bono si el asesor cumple justo el ${u} % de su presupuesto: presupuesto × ${u} % × ${meta} %.`,
    `Si vende más, la meta real es el ${meta} % de su venta total.`,
    `Solo se activa con cumplimiento ≥ ${u} %. Bono: ${formatCOP(lineaBono.bono)}.`,
  ].join(' ');
}

function Encabezado({ lineasBono, umbral }) {
  return (
    <thead>
      <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        <th style={thStyle}>Tienda</th>
        <th style={thStyle}>Asesor</th>
        <th style={thStyle}>Cédula</th>
        <th style={montoThStyle}>Presupuesto</th>
        {lineasBono.map((lb) => (
          <th key={lb.linea} style={montoThStyle}>
            {lb.etiqueta}
            <InfoTooltip text={textoAyudaLinea(lb, umbral)} />
          </th>
        ))}
        <th style={thStyle}>Acciones</th>
      </tr>
    </thead>
  );
}

function FilaAsesor({ linea, lineasBono, onEditar, onQuitar }) {
  const minimos = linea.minimos || {};
  return (
    <tr style={filaStyle}>
      <td style={nombreStyle}>{linea.tienda}</td>
      <td style={nombreStyle}>{linea.asesor}</td>
      <td style={tdStyle}>{linea.cedula}</td>
      <td style={montoStyle}>{formatCOP(linea.monto)}</td>
      {lineasBono.map((lb) => (
        <td key={lb.linea} style={montoStyle}>{formatCOP(minimos[lb.linea])}</td>
      ))}
      <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
        <button type="button" className="motored-btn motored-btn-tertiary"
          aria-label={`Editar ${linea.asesor}`} onClick={() => onEditar(linea)}>Editar</button>
        <button type="button" className="motored-btn motored-btn-tertiary"
          aria-label={`Quitar ${linea.asesor}`} onClick={() => onQuitar(linea)}>Quitar</button>
      </td>
    </tr>
  );
}

function FilaTotal({ detalle, lineasBono }) {
  const totales = detalle.totales_minimos || {};
  return (
    <tfoot>
      <tr style={totalStyle}>
        <td style={nombreStyle}>Total</td>
        <td style={tdStyle} />
        <td style={tdStyle} />
        <td style={montoStyle}>{formatCOP(detalle.total)}</td>
        {lineasBono.map((lb) => (
          <td key={lb.linea} style={montoStyle}>{formatCOP(totales[lb.linea])}</td>
        ))}
        <td style={tdStyle} />
      </tr>
    </tfoot>
  );
}

export default function TablaPresupuestos({ detalle, onEditar, onQuitar }) {
  const lineasBono = detalle.lineas_bono || [];
  return (
    <MotoredTableScroll>
      <table style={tablaStyle} aria-label="Presupuestos del mes">
        <Encabezado lineasBono={lineasBono} umbral={detalle.umbral_bono_pct} />
        <tbody>
          {ordenarLineas(detalle.lineas).map((l) => (
            <FilaAsesor key={l.cedula} linea={l} lineasBono={lineasBono} onEditar={onEditar} onQuitar={onQuitar} />
          ))}
        </tbody>
        <FilaTotal detalle={detalle} lineasBono={lineasBono} />
      </table>
    </MotoredTableScroll>
  );
}
