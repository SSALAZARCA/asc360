'use client';
/** Live progress of a corrida being calculated: "Sucursal 12 de 47". */
import useProgresoCorrida from './useProgresoCorrida';
import { errorStyle, mutedStyle } from './styles';

export default function ProgresoCorrida({ corridaId, estado, onTerminal }) {
  const { progreso, error } = useProgresoCorrida(corridaId, estado, onTerminal);
  if (error) return <span role="alert" style={errorStyle}>{error}</span>;
  if (!progreso) return <span role="status" style={mutedStyle}>Leyendo avance...</span>;
  if (progreso.estado === 'PENDIENTE' || !progreso.procesadas) {
    return <span role="status" style={mutedStyle}>En cola</span>;
  }
  return (
    <span role="status" style={{ display: 'inline-flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>{`Sucursal ${progreso.procesadas} de ${progreso.total}`}</span>
      {progreso.actual && <span style={mutedStyle}>{progreso.actual}</span>}
    </span>
  );
}
