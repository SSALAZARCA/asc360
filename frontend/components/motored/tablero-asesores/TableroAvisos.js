'use client';
/** Warnings and notes above the table: venta without a known line, and the cost date. */
import { fechaCorta, pesos, porcentajeTexto } from './formato';

const avisoStyle = {
  margin: 0, padding: '0.6rem 0.8rem', fontSize: '0.8rem', borderRadius: 'var(--motored-radius-sm, 4px)',
  color: 'var(--motored-warning, #d97706)', background: 'var(--motored-warning-bg, #fef3e2)',
};
const notaStyle = { margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };

export default function TableroAvisos({ data }) {
  const sinLinea = Number(data.venta_sin_linea) > 0;
  return (
    <>
      {sinLinea && (
        <p role="alert" style={avisoStyle}>
          {porcentajeTexto(data.pct_venta_sin_linea)} de la venta no tiene línea comercial reconocida y no se incluye
          ({pesos(data.venta_sin_linea)}). Revise la línea comercial de las referencias.
        </p>
      )}
      <p style={notaStyle}>
        {data.fecha_corte_costos
          ? `Costos calculados con el inventario del ${fechaCorta(data.fecha_corte_costos)}.`
          : 'No hay inventario cargado: el tablero no tiene costos ni margen.'}
      </p>
    </>
  );
}
