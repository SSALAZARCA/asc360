/**
 * "PRUEBA" pill on the pair screens of a test conteo (odd/tasks/motored-conteo-prueba.md),
 * so a pair rehearsing a count knows it is not the real one.
 */
import { C } from './estilos';

export default function PruebaBadge() {
  return (
    <span
      title="Conteo de prueba"
      style={{
        display: 'inline-block', fontSize: 12, fontWeight: 800, letterSpacing: '0.06em', padding: '3px 10px',
        borderRadius: 999, background: C.alertaFondo, color: C.alerta, whiteSpace: 'nowrap',
      }}
    >
      PRUEBA
    </span>
  );
}
