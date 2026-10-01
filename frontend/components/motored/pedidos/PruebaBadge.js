/** "PRUEBA" badge of a scenario corrida, with its help tooltip. */
import InfoTooltip from '../InfoTooltip';

const PRUEBA_TEXTO = 'PRUEBA: corrida de escenario para comparar contra la real. No se cierra, no se exporta y no se envía.';
const pruebaStyle = {
  display: 'inline-block', padding: '2px 8px', borderRadius: 'var(--motored-radius-pill, 999px)',
  fontSize: '0.65rem', fontWeight: 700, background: 'var(--motored-brand-soft, #fde8ea)',
  color: 'var(--motored-primary, #e20714)',
};

export default function PruebaBadge() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center' }}>
      <span style={pruebaStyle}>PRUEBA</span>
      <InfoTooltip text={PRUEBA_TEXTO} />
    </span>
  );
}
