/** The estado pill of a conteo (WU11). */
import { labelEstado } from './conteosFormato';
import { pildoraStyle } from './estilos';

const TONOS = {
  PROGRAMADO: ['var(--motored-info-soft, #eaf0f8)', 'var(--motored-info, #1d4e89)'],
  EN_CONTEO: ['var(--motored-success-bg, #ecfdf3)', 'var(--motored-success, #15803d)'],
  EN_RECONTEO: ['var(--motored-warning-bg, #fef3e2)', 'var(--motored-data-mid-ink, #8a4104)'],
  CERRADO: ['var(--motored-surface-alt, #f4f4f5)', 'var(--motored-text, #1a1a18)'],
  ANULADO: ['var(--motored-surface-alt, #f4f4f5)', 'var(--motored-text-muted, #5a5a5a)'],
};

export default function EstadoConteoBadge({ estado }) {
  const [fondo, texto] = TONOS[estado] || TONOS.CERRADO;
  return <span style={pildoraStyle(fondo, texto)}>{labelEstado(estado)}</span>;
}
