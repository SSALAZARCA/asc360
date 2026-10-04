'use client';
import { COLOR } from '../tokens';
import { HMCL_OPCIONES, etiquetaHmcl, opcionHmcl } from '../periodo';
import FilterPopover from './FilterPopover';
import { TITULO_POPOVER, chip } from './estilos';

export default function HmclFilter({ filtros, onChange, abierto, onToggle, onClose }) {
  return (
    <FilterPopover
      rotulo="HMCL" valor={etiquetaHmcl(filtros.hmcl)} dialogo="Ventas a HMCL" ancho={260}
      abierto={abierto} onToggle={onToggle} onClose={onClose} resumen={opcionHmcl(filtros.hmcl).desc}
    >
      <div style={{ ...TITULO_POPOVER, color: COLOR.soft }}>Ventas a HMCL (garantías)</div>
      <div role="radiogroup" aria-label="Ventas a HMCL" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {HMCL_OPCIONES.map((o) => (
          <button
            key={o.id} type="button" role="radio" aria-checked={filtros.hmcl === o.id} onClick={() => onChange({ hmcl: o.id })}
            style={{ ...chip(filtros.hmcl === o.id), textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 2, padding: '8px 10px' }}
          >
            <span style={{ fontWeight: 700 }}>{o.label}</span>
            <span style={{ fontSize: 11.5, fontWeight: 500, opacity: 0.8 }}>{o.desc}</span>
          </button>
        ))}
      </div>
    </FilterPopover>
  );
}
