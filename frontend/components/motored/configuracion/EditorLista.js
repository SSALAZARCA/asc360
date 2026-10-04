'use client';
/**
 * List of texts as chips (add / remove). The draft is the same text the
 * plain list control uses (one item per line), so `valor.js` is unchanged.
 * `digitos` accepts only digits (NIT); `mayusculas` writes items in capitals.
 */
import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import { controlStyle, errorStyle, filaStyle, touchStyle } from './styles';

export const itemsDe = (borrador) => String(borrador || '').split('\n').map((x) => x.trim()).filter(Boolean);

function Chip({ valor, onQuitar }) {
  return (
    <span style={{ ...filaStyle, gap: '0.25rem', border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '999px', paddingLeft: '0.75rem' }}>
      <span style={{ fontSize: '0.8rem' }}>{valor}</span>
      <button
        type="button" aria-label={`Quitar ${valor}`} className="motored-btn motored-btn-secondary"
        style={{ ...touchStyle, minWidth: '44px' }} onClick={onQuitar}
      >
        <X size={14} aria-hidden="true" />
      </button>
    </span>
  );
}

function problemaAlAgregar(nuevo, items, digitos) {
  if (!nuevo) return 'Escriba un valor antes de agregar.';
  if (digitos && !/^[0-9]+$/.test(nuevo)) return `«${nuevo}» debe tener sólo dígitos.`;
  if (items.includes(nuevo)) return `«${nuevo}» ya está en la lista.`;
  return '';
}

export default function EditorLista({ borrador, onChange, digitos = false, mayusculas = false }) {
  const [nuevo, setNuevo] = useState('');
  const [problema, setProblema] = useState('');
  const items = itemsDe(borrador);

  const agregar = () => {
    const valor = mayusculas ? nuevo.trim().toUpperCase() : nuevo.trim();
    const error = problemaAlAgregar(valor, items, digitos);
    setProblema(error);
    if (error) return;
    onChange([...items, valor].join('\n'));
    setNuevo('');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={filaStyle}>
        {items.map((v) => <Chip key={v} valor={v} onQuitar={() => onChange(items.filter((x) => x !== v).join('\n'))} />)}
      </div>
      <div style={filaStyle}>
        <input
          type="text" aria-label="Nuevo valor" value={nuevo} inputMode={digitos ? 'numeric' : 'text'}
          style={{ ...controlStyle, width: '14rem' }}
          onChange={(e) => { setNuevo(e.target.value); setProblema(''); }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); agregar(); } }}
        />
        <button type="button" className="motored-btn motored-btn-secondary" style={touchStyle} onClick={agregar}>
          <Plus size={14} aria-hidden="true" />
          {' '}
          Agregar
        </button>
      </div>
      {problema && <p role="alert" style={errorStyle}>{problema}</p>}
    </div>
  );
}
