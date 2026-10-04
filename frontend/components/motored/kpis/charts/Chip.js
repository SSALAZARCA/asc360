import { COLOR } from '../tokens';

const VARIANTES = {
  up: { background: COLOR.goodSoft, color: COLOR.goodInk },
  down: { background: COLOR.badSoft, color: COLOR.badInk },
  flat: { background: COLOR.track, color: COLOR.muted },
};

/** Pill with a short text: `up` (teal), `down` (violet) or `flat` (gray). */
export default function Chip({ text, variant = 'flat' }) {
  const estilo = VARIANTES[variant] || VARIANTES.flat;
  return (
    <span
      data-variant={variant}
      style={{
        display: 'inline-block', fontSize: 12, fontWeight: 700, borderRadius: 999, padding: '2px 8px',
        whiteSpace: 'nowrap', ...estilo,
      }}
    >
      {text}
    </span>
  );
}
