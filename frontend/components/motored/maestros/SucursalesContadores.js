'use client';
/**
 * frontend/components/motored/maestros/SucursalesContadores.js
 *
 * Two header counters for the Sucursales master screen, derived from the
 * already-loaded list (no extra request), so they follow create / edit /
 * deactivate / bulk upload automatically.
 *  - "Sucursales activas": rows with `activa` true.
 *  - "Tiendas principales": active rows with no `principal_id` (not
 *    associated to another store).
 */
import InfoTooltip from '../InfoTooltip';
import { COLOR } from '../kpis/tokens';

export function contarSucursales(sucursales) {
  const activas = (sucursales || []).filter((s) => s.activa);
  return {
    activas: activas.length,
    principales: activas.filter((s) => !s.principal_id).length,
  };
}

function Contador({ label, value, tooltip }) {
  return (
    <div
      data-contador
      style={{ background: COLOR.wash, borderRadius: 10, padding: '10px 14px', minWidth: 140, flex: '1 1 140px' }}
    >
      <p
        style={{
          margin: 0, display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 500,
          letterSpacing: '.04em', textTransform: 'uppercase', color: COLOR.muted,
        }}
      >
        <span>{label}</span>
        <InfoTooltip text={tooltip} />
      </p>
      <p
        data-testid="contador-valor"
        style={{
          margin: '4px 0 0', fontFamily: 'var(--motored-font-kpi)', fontSize: 24, fontWeight: 700,
          fontVariantNumeric: 'tabular-nums', color: COLOR.ink,
        }}
      >
        {value}
      </p>
    </div>
  );
}

export default function SucursalesContadores({ sucursales }) {
  const { activas, principales } = contarSucursales(sucursales);
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, minWidth: 0 }}>
      <Contador label="Sucursales activas" value={activas} tooltip="Total de sucursales en estado Activa." />
      <Contador
        label="Tiendas principales"
        value={principales}
        tooltip="Sucursales activas que tienen pedido propio; no cuenta las tiendas asociadas a otra."
      />
    </div>
  );
}
