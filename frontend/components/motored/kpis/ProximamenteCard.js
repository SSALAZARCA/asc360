import { COLOR } from './tokens';

/** Temporary content of a tab that is not built yet. */
export default function ProximamenteCard({ titulo }) {
  return (
    <section aria-label={titulo} style={{ background: COLOR.surface, border: `1px solid ${COLOR.track}`, borderRadius: 14, padding: 20 }}>
      <p style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{titulo}</p>
      <p style={{ margin: '4px 0 0', fontSize: 12.5, color: COLOR.muted }}>Próximamente</p>
    </section>
  );
}
