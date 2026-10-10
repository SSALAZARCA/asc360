/** The "PRUEBA" pill of a test conteo (odd/tasks/motored-conteo-prueba.md). */
import { pildoraStyle } from './estilos';

export default function PruebaBadge() {
  return (
    <span
      title="Conteo de prueba: solo lo ve el administrador y no se carga al ERP"
      style={pildoraStyle('var(--motored-warning-bg, #fef3e2)', 'var(--motored-data-mid-ink, #8a4104)')}
    >
      PRUEBA
    </span>
  );
}
