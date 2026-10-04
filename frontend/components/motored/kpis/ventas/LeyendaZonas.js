import { COLOR, TONO } from '../tokens';
import { LEYENDA, NUM } from './estilos';

/** "● ≥ 90% · 10" legend of the semaforo zones. */
export default function LeyendaZonas({ zonas }) {
  return (
    <div style={LEYENDA}>
      {zonas.leyenda.map((z) => (
        <span key={z.tone} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 999, background: TONO[z.tone].color }} />
          {z.label} · <strong style={{ ...NUM, color: COLOR.ink }}>{z.n}</strong>
        </span>
      ))}
    </div>
  );
}
