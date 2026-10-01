'use client';
/** Sections of the corrida detail as tabs (`tabs` = [{ id, label }]); `onChange` receives the id. */
const tabStyle = (activa) => ({
  padding: '0.5rem 0.9rem', border: 'none', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 700,
  minHeight: '44px', background: 'transparent',
  color: activa ? 'var(--motored-primary, #e20714)' : 'var(--motored-text-muted, #5a5a5a)',
  borderBottom: activa ? '3px solid var(--motored-primary, #e20714)' : '3px solid transparent',
});

export default function CorridaTabs({ tabs, value, onChange }) {
  return (
    <div role="tablist" style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', borderBottom: '1px solid var(--motored-border, #e4e4e7)' }}>
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={value === t.id} style={tabStyle(value === t.id)} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
