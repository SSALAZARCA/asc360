'use client';
/** Small pieces shared by the two "pendientes" cards of the asesor view (invoices and transfers). */
const PILDORA = { fontFamily: 'inherit', fontSize: 11.5, fontWeight: 700, height: 26, padding: '0 10px', borderRadius: 999, cursor: 'pointer', whiteSpace: 'nowrap' };

/** Toggle answer pill: filled when it is the selected answer. */
export function Pildora({ texto, color, activo, ocupada, onClick }) {
  return (
    <button
      type="button" aria-pressed={activo} disabled={ocupada} onClick={onClick}
      style={{ ...PILDORA, border: `1.5px solid ${color}`, background: activo ? color : '#FFFFFF', color: activo ? '#FFFFFF' : color }}
    >
      {texto}
    </button>
  );
}

/** The (i) button of a card footer; the explanation is its tooltip. */
export function BotonInfo({ ayuda, color }) {
  return (
    <button type="button" aria-label="Más información" title={ayuda} style={{ appearance: 'none', border: 0, background: 'transparent', color, width: 18, height: 18, padding: 0, cursor: 'help', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
      </svg>
    </button>
  );
}
