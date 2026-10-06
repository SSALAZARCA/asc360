import { COLOR } from '../tokens';

const ESTILO_CHIP = {
  cumple: { background: COLOR.good, color: '#FFFFFF', border: `1px solid ${COLOR.good}` },
  'sin-compuerta': { background: COLOR.good, color: '#FFFFFF', border: `1px solid ${COLOR.good}`, opacity: 0.45 },
  'no-cumple': { background: 'transparent', color: COLOR.muted, border: `1px solid ${COLOR.line}` },
  apagado: { background: COLOR.track, color: COLOR.soft, border: `1px solid ${COLOR.track}` },
};

/** Small pill of one bonus line; its look says met / not met / met without the gate / off. */
export default function ChipBono({ chip }) {
  return (
    <span data-testid="chip-bono" data-estado={chip.estado} title={chip.tip} style={{ ...ESTILO_CHIP[chip.estado], fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '1px 7px', whiteSpace: 'nowrap' }}>
      {chip.texto}
    </span>
  );
}
