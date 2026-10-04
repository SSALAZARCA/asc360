'use client';
/** Tab bar of the KPI's. The active tab carries the brand-red underline (the only brand-red use here). */
import { COLOR } from './tokens';

export const TABS = [
  { id: 'ventas', label: 'Ventas' },
  { id: 'tiendas', label: 'Tiendas' },
  { id: 'asesores', label: 'Asesores' },
];

const estilo = (activa) => ({
  appearance: 'none', border: 0, background: 'transparent', fontFamily: 'inherit', fontSize: 14, fontWeight: 500,
  color: activa ? COLOR.ink : COLOR.muted, padding: '12px 4px', minHeight: 44, cursor: 'pointer',
  borderBottom: `3px solid ${activa ? 'var(--motored-brand, #E20714)' : 'transparent'}`,
});

export default function KpiTabs({ value, onChange }) {
  return (
    <div role="tablist" aria-label="Secciones de KPI's" style={{ display: 'flex', flexWrap: 'wrap', gap: 26, borderBottom: `1px solid ${COLOR.track}` }}>
      {TABS.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)} style={estilo(value === t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
