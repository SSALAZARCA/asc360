'use client';
import { tarjeta } from './ingresosEstilos';
import { PALETA, NORMAL, CRITICO, nivelPorDias } from './semaforo';

const etiqueta = { margin: 0, fontSize: '12px', fontWeight: 500, letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--motored-text-muted, #595954)' };
const valorStyle = { margin: '6px 0 0', fontSize: '30px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', letterSpacing: '-.01em' };
const pie = { margin: '6px 0 0', fontSize: '12.5px', color: 'var(--motored-text-muted, #595954)' };

function Kpi({ nombre, valor, pista, nivel, ayuda }) {
  const p = nivel ? PALETA[nivel] : null;
  const estilo = p ? { ...tarjeta, border: `2px solid ${p.color}`, background: p.soft } : tarjeta;
  return (
    <div style={estilo} title={ayuda} data-nivel={nivel || undefined}>
      <p style={{ ...etiqueta, ...(p ? { color: p.ink, fontWeight: 700 } : {}) }}>{nombre}</p>
      <p style={{ ...valorStyle, ...(p ? { color: p.ink } : {}) }}>{valor}</p>
      <p style={{ ...pie, ...(p ? { color: p.ink } : {}) }}>{pista}</p>
    </div>
  );
}

export default function IngresosKpis({ resumen }) {
  const r = resumen || {};
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '14px' }}>
      <Kpi nombre="Pendientes" valor={r.pendientes ?? 0} pista="Facturas sin ingresar en la red" />
      <Kpi
        nombre="Llegaron sin ingresar" valor={r.llegaron_sin_ingresar ?? 0}
        pista="La tienda confirmó que llegaron · prioridad"
        nivel={(r.llegaron_sin_ingresar ?? 0) > 0 ? CRITICO : NORMAL}
        ayuda="Ya están físicamente en la tienda pero nadie las ha ingresado al inventario. Es lo primero que hay que resolver."
      />
      <Kpi nombre="Sin confirmar" valor={r.sin_confirmar ?? 0} pista="Nadie ha respondido todavía" />
      <Kpi nombre="Aún no llegan" valor={r.aun_no_llegan ?? 0} pista="La tienda dice que no ha llegado" />
      <Kpi
        nombre="Más antigua" valor={r.mas_antigua == null ? '—' : `${r.mas_antigua} días`}
        pista="Días desde la fecha de la factura" nivel={nivelPorDias(r.mas_antigua)}
      />
    </div>
  );
}
