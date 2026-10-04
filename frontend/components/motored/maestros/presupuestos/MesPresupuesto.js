'use client';
/**
 * One month of budgets: header (version, origin, loaded date, grand total) and
 * the lines grouped by tienda, each group with its total. Per-asesor edit and
 * remove actions call back into the tab.
 */
import { formatCOP } from '../../../../lib/motored/formatCOP';
import MotoredTableScroll from '../../MotoredTableScroll';
import InfoTooltip from '../../InfoTooltip';
import {
  tablaStyle, thStyle, tdStyle, filaStyle, panelStyle, mesLegible, origenLegible, fechaLegible,
} from './formato';

const TOOLTIP_VERSION = 'Cada carga o cambio crea una versión nueva del mes. Los indicadores usan siempre la última versión.';
const TOOLTIP_ORIGEN = 'Excel: el mes salió de un archivo cargado. Manual: alguien agregó, cambió o quitó un asesor a mano.';

/** Lines grouped by tienda in the order of `por_tienda` (the server's), with each group's total. */
function agruparPorTienda(detalle) {
  return detalle.por_tienda.map((tienda) => ({
    ...tienda,
    lineas: detalle.lineas.filter((l) => l.sucursal_id === tienda.sucursal_id),
  }));
}

function GrupoTienda({ grupo, onEditar, onQuitar }) {
  return (
    <section aria-label={`Tienda ${grupo.tienda}`} style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
        <strong>{grupo.tienda}</strong>
        <span style={{ fontSize: '0.85rem' }}>
          <span>{formatCOP(grupo.total)}</span> · {grupo.asesores} {grupo.asesores === 1 ? 'asesor' : 'asesores'}
        </span>
      </div>
      <MotoredTableScroll>
        <table style={tablaStyle}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
              {['Asesor', 'Cédula', 'Presupuesto', ''].map((t) => <th key={t || 'acc'} style={thStyle}>{t}</th>)}
            </tr>
          </thead>
          <tbody>
            {grupo.lineas.map((l) => (
              <tr key={l.cedula} style={filaStyle}>
                <td style={tdStyle}>{l.asesor}</td>
                <td style={tdStyle}>{l.cedula}</td>
                <td style={tdStyle}>{formatCOP(l.monto)}</td>
                <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                  <button type="button" className="motored-btn motored-btn-tertiary"
                    aria-label={`Editar ${l.asesor}`} onClick={() => onEditar(l)}>Editar</button>
                  <button type="button" className="motored-btn motored-btn-tertiary"
                    aria-label={`Quitar ${l.asesor}`} onClick={() => onQuitar(l)}>Quitar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
    </section>
  );
}

export default function MesPresupuesto({ detalle, onEditar, onQuitar }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', minWidth: 0 }}>
      <div style={{ ...panelStyle, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1rem' }}>{mesLegible(detalle.mes)}</h3>
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <span>Versión {detalle.version}</span>
            <InfoTooltip text={TOOLTIP_VERSION} />
            {' · Origen: '}
            <span data-testid="presupuesto-origen">{origenLegible(detalle.origen)}</span>
            <InfoTooltip text={TOOLTIP_ORIGEN} />
            {` · Cargado el ${fechaLegible(detalle.created_at)}`}
          </p>
        </div>
        <div data-testid="presupuesto-total" style={{ textAlign: 'right' }}>
          <strong style={{ fontSize: '1.1rem' }}>{formatCOP(detalle.total)}</strong>
          <span style={{ display: 'block', fontSize: '0.75rem' }}>
            {detalle.asesores} {detalle.asesores === 1 ? 'asesor' : 'asesores'}
          </span>
        </div>
      </div>
      {detalle.lineas.length === 0 && (
        <p style={{ margin: 0, fontSize: '0.85rem' }}>Esta versión no tiene asesores.</p>
      )}
      {agruparPorTienda(detalle).map((g) => (
        <GrupoTienda key={g.sucursal_id} grupo={g} onEditar={onEditar} onQuitar={onQuitar} />
      ))}
    </div>
  );
}
