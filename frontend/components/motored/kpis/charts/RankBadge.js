import { MEDALLA } from '../tokens';

/** Round rank badge: black, dark gray and gray for the podium, light gray for the rest; `colors` {bg, fg} overrides it. */
export default function RankBadge({ rank, size = 28, colors }) {
  const medal = rank <= 3 ? String(rank) : 'rest';
  const { bg, fg } = colors ?? MEDALLA[medal];
  return (
    <span
      data-testid="rank-badge" data-medal={medal}
      style={{
        width: size, height: size, flex: 'none', borderRadius: 999, display: 'inline-flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 12.5, fontWeight: 700, fontVariantNumeric: 'tabular-nums', background: bg, color: fg,
      }}
    >
      {rank}
    </span>
  );
}
