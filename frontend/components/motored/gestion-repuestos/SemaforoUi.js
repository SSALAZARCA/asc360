'use client';
import { PALETA, NORMAL, ATENCION, CRITICO, TEXTO_UMBRALES } from './semaforo';

/** Colored pill (soft background, dark ink: text contrast above 4.5:1). `nivel` null renders plain text. */
export function PildoraNivel({ nivel, children, title }) {
  if (!nivel) return <span title={title}>{children}</span>;
  const p = PALETA[nivel];
  return (
    <span
      data-nivel={nivel} title={title}
      style={{ display: 'inline-block', minWidth: 28, textAlign: 'center', fontSize: 12, fontWeight: 700, borderRadius: 999, padding: '2px 10px', whiteSpace: 'nowrap', background: p.soft, color: p.ink, border: `1px solid ${p.color}` }}
    >
      {children}
    </span>
  );
}

export function PuntoNivel({ nivel }) {
  return (
    <span
      aria-hidden="true" data-nivel={nivel}
      style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 999, marginRight: 8, background: PALETA[nivel].color }}
    />
  );
}

const Item = ({ nivel, texto }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center' }}>
    <PuntoNivel nivel={nivel} />{texto}
  </span>
);

export function LeyendaSemaforo() {
  return (
    <p aria-label="Leyenda de colores" title={TEXTO_UMBRALES} style={{ margin: 0, fontSize: 12.5, display: 'flex', flexWrap: 'wrap', gap: '4px 16px', alignItems: 'center' }}>
      <Item nivel={NORMAL} texto="≤7 días normal" />
      <Item nivel={ATENCION} texto="8–15 días atención" />
      <Item nivel={CRITICO} texto=">15 días o llegó sin ingresar: crítico" />
    </p>
  );
}
