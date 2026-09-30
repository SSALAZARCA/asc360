'use client';
/** Case header: back link, number, state, result, creation date, owner. */
import { ArrowLeft } from 'lucide-react';
import { EstadoBadge } from './badges';
import { RESULTADO_LABELS, formatFechaHora } from './labels';
import { mutedStyle } from './styles';

export default function DetalleHeader({ caso, onBack }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <button type="button" className="motored-btn motored-btn-tertiary" style={{ alignSelf: 'flex-start' }} onClick={onBack}>
        <ArrowLeft size={14} /> Volver a detractores
      </button>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <h1 className="motored-h-pantalla">Caso No. {caso.numero}</h1>
        <EstadoBadge estado={caso.estado} />
        {caso.resultado && (
          <span style={{ fontSize: '0.8rem' }}>Resultado: <strong>{RESULTADO_LABELS[caso.resultado]}</strong></span>
        )}
      </div>
      <p style={{ margin: 0, fontSize: '0.8rem', ...mutedStyle }}>
        Creado el {formatFechaHora(caso.created_at)} · Responsable: {caso.asignado_a?.nombre || 'Sin asignar'}
      </p>
    </div>
  );
}
