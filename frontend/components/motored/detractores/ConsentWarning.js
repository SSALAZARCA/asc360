/** Prominent banner shown when the customer answered "No" to data consent. */
import { TriangleAlert } from 'lucide-react';

export default function ConsentWarning() {
  return (
    <div
      role="alert"
      style={{
        display: 'flex', gap: '0.75rem', alignItems: 'flex-start', padding: '1rem 1.25rem',
        background: 'var(--motored-danger-bg, #fdecea)', border: '2px solid var(--motored-danger, #c0392b)',
        borderRadius: 'var(--motored-radius-md, 8px)', color: 'var(--motored-danger, #c0392b)',
      }}
    >
      <TriangleAlert size={24} style={{ flexShrink: 0 }} />
      <div>
        <strong style={{ display: 'block', fontSize: '1rem' }}>Cliente NO autorizó tratamiento de datos</strong>
        <span style={{ fontSize: '0.85rem', color: 'var(--motored-text, #1a1a18)' }}>
          Respondió «No» a la autorización de datos en la encuesta. Tenlo en cuenta antes de contactarlo.
        </span>
      </div>
    </div>
  );
}
