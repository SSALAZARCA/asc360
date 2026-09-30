'use client';
/** Estado tabs with counts (from `conteo_por_estado`). */
import { ESTADO_LABELS } from './labels';

const TABS = [
  { estado: 'ABIERTO', label: 'Abiertos' },
  { estado: 'EN_GESTION', label: ESTADO_LABELS.EN_GESTION },
  { estado: 'CERRADO', label: 'Cerrados' },
  { estado: '', label: 'Todos' },
];

function countOf(conteo, estado) {
  if (!conteo) return null;
  return estado ? conteo[estado] : Object.values(conteo).reduce((a, b) => a + b, 0);
}

function tabStyle(active) {
  return {
    padding: '0.5rem 0.9rem', border: 'none', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 700,
    background: 'transparent', color: active ? 'var(--motored-primary, #e20714)' : 'var(--motored-text-muted, #5a5a5a)',
    borderBottom: active ? '3px solid var(--motored-primary, #e20714)' : '3px solid transparent',
  };
}

export default function DetractoresTabs({ value, conteo, onChange }) {
  return (
    <div role="tablist" style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', borderBottom: '1px solid var(--motored-border, #e4e4e7)' }}>
      {TABS.map((t) => {
        const count = countOf(conteo, t.estado);
        return (
          <button
            key={t.label} type="button" role="tab" aria-selected={value === t.estado}
            style={tabStyle(value === t.estado)} onClick={() => onChange(t.estado)}
          >
            {t.label}{count !== null && ` (${count})`}
          </button>
        );
      })}
    </div>
  );
}
