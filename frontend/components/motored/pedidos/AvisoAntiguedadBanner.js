'use client';
/**
 * Early warning above the Pedidos screens: which pedido input (inventario,
 * backorder, facturas, ingresos) expires tomorrow or today, so it can be
 * uploaded before the corrida is blocked. Renders nothing without warnings.
 */
import { useState } from 'react';
import useAvisosAntiguedad from './useAvisosAntiguedad';
import { cardStyle } from './styles';

// dataset -> [noun phrase with article, verb, pronoun to upload it]
const FRASES = {
  inventario: ['El inventario', 'vence', 'Súbalo'],
  backorder: ['El backorder', 'vence', 'Súbalo'],
  facturas: ['Las facturas de pedidos', 'vencen', 'Súbalas'],
  ingresos: ['Los ingresos de facturas', 'vencen', 'Súbalos'],
};

const diaMes = (iso) => {
  const [, mes, dia] = String(iso || '').slice(0, 10).split('-');
  return mes && dia ? `${dia}/${mes}` : '—';
};

function frase(aviso) {
  const [sujeto, verbo] = FRASES[aviso.dataset] || [`Los datos de ${aviso.nombre}`, 'vencen'];
  const cuando = aviso.vence === 'hoy' ? 'hoy' : 'mañana';
  return `${sujeto} ${verbo} ${cuando} (cargado el ${diaMes(aviso.fecha_carga)}).`;
}

function invitacion(avisos) {
  if (avisos.length > 1) return 'Súbalos antes de lanzar el pedido.';
  const [, , pronombre] = FRASES[avisos[0].dataset] || [null, null, 'Súbalos'];
  return `${pronombre} antes de lanzar el pedido.`;
}

export default function AvisoAntiguedadBanner({ enabled }) {
  const avisos = useAvisosAntiguedad(enabled);
  const [oculto, setOculto] = useState(false);
  if (oculto || avisos.length === 0) return null;
  return (
    <div
      role="status" aria-label="Datos por vencer"
      style={{ ...cardStyle, flexDirection: 'row', alignItems: 'flex-start', gap: '1rem' }}
    >
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.85rem' }}>
        {avisos.map((aviso) => <span key={aviso.dataset} style={{ fontWeight: 600 }}>{frase(aviso)}</span>)}
        <span>{invitacion(avisos)}</span>
      </div>
      <button
        type="button" className="motored-row-action" style={{ minHeight: '44px' }}
        aria-label="Descartar aviso de datos por vencer" onClick={() => setOculto(true)}
      >
        Descartar
      </button>
    </div>
  );
}
