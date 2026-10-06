/** Inicio: a small state pill (text plus its tone colors). */
import { TONOS } from './textos';

export default function Chip({ tono, children }) {
  const colores = TONOS[tono] || TONOS.neutro;
  return (
    <span
      style={{
        alignSelf: 'flex-start', fontSize: '11px', fontWeight: 800, padding: '4px 10px', whiteSpace: 'nowrap',
        borderRadius: 'var(--motored-radius-pill, 999px)', background: colores.fondo, color: colores.tinta,
      }}
    >
      {children}
    </span>
  );
}
