'use client';
/**
 * One month of budgets: header (version, origin, loaded date, grand total) and
 * one flat table of every asesor with their per-line bonus minimums (see
 * `TablaPresupuestos`). Per-asesor edit and remove actions call back into the tab.
 */
import { formatCOP } from '../../../../lib/motored/formatCOP';
import InfoTooltip from '../../InfoTooltip';
import TablaPresupuestos from './TablaPresupuestos';
import { panelStyle, mesLegible, origenLegible, fechaLegible } from './formato';

const TOOLTIP_VERSION = 'Cada carga o cambio crea una versión nueva del mes. Los indicadores usan siempre la última versión.';
const TOOLTIP_ORIGEN = 'Excel: el mes salió de un archivo cargado. Manual: alguien agregó, cambió o quitó un asesor a mano.';

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
      {detalle.lineas.length > 0 && (
        <TablaPresupuestos detalle={detalle} onEditar={onEditar} onQuitar={onQuitar} />
      )}
    </div>
  );
}
