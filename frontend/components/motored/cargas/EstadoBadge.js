'use client';
/**
 * frontend/components/motored/cargas/EstadoBadge.js
 *
 * Chip de color para `carga_archivo.estado` (sdd/motored-pedidos-ingesta,
 * Phase 10). Estaba duplicado en `CargasHistoryTable.js` y `CargaDetalle.js`
 * (gga-driven fix) -- una sola fuente acá, sobre `coloresEstado` de
 * `tiposCarga.js`.
 */
import { coloresEstado } from './tiposCarga';

export default function EstadoBadge({ estado, size = 'md' }) {
  const { fg, bg } = coloresEstado(estado);
  const padding = size === 'sm' ? '2px 8px' : '2px 10px';
  const fontSize = size === 'sm' ? '0.7rem' : '0.75rem';
  return (
    <span
      style={{
        display: 'inline-block', padding, borderRadius: 'var(--motored-radius-pill, 999px)',
        fontSize, fontWeight: 700, color: fg, background: bg,
      }}
    >
      {estado}
    </span>
  );
}
