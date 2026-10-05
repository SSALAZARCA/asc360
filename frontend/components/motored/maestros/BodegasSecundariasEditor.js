'use client';
/**
 * frontend/components/motored/maestros/BodegasSecundariasEditor.js
 *
 * Chips editor for a store's secondary bodega codes in the Sucursales form.
 * A code is added with Enter, a comma, the "Agregar" button or by leaving
 * the input; several can be pasted separated by commas. Codes are trimmed,
 * upper-cased and never repeated. The backend has the final word: a code of
 * another store, or another store's principal, is rejected on save.
 */
import { useState } from 'react';
import InfoTooltip from '../InfoTooltip';

const TOOLTIP = 'Otras bodegas de la misma tienda (por ejemplo, las de consignación MC...). Su inventario y sus ventas cuentan para esta sucursal. Una bodega solo puede ser de una tienda: para pasarla de otra tienda, quítela allá primero o use la carga masiva.';

const labelStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.7rem',
  color: 'var(--motored-text-muted, #5a5a5a)', minWidth: '220px', maxWidth: '100%',
};
const listStyle = {
  display: 'flex', flexWrap: 'wrap', gap: '0.3rem', listStyle: 'none', margin: 0, padding: 0,
};
const chipStyle = {
  display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.1rem 0.45rem',
  border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '999px',
  background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text, #1a1a18)', fontSize: '0.75rem',
};
const quitarStyle = {
  border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer',
  padding: 0, fontSize: '0.85rem', lineHeight: 1,
};

function separar(texto) {
  return texto.split(/[,;]/).map((c) => c.trim().toUpperCase()).filter(Boolean);
}

export default function BodegasSecundariasEditor({ value, onChange }) {
  const [texto, setTexto] = useState('');
  const codigos = value || [];

  const agregar = () => {
    const nuevos = separar(texto).filter((c, i, todos) => !codigos.includes(c) && todos.indexOf(c) === i);
    setTexto('');
    if (nuevos.length) onChange([...codigos, ...nuevos]);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      agregar();
    }
  };

  return (
    <div style={labelStyle}>
      <label htmlFor="bodegas-secundarias-input">
        Bodegas secundarias
        <InfoTooltip text={TOOLTIP} />
      </label>
      {codigos.length > 0 && (
        <ul style={listStyle}>
          {codigos.map((c) => (
            <li key={c} style={chipStyle}>
              <span>{c}</span>
              <button type="button" style={quitarStyle} aria-label={`Quitar ${c}`} title={`Quitar ${c}`}
                onClick={() => onChange(codigos.filter((x) => x !== c))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div style={{ display: 'flex', gap: '0.3rem' }}>
        <input
          id="bodegas-secundarias-input"
          type="text"
          value={texto}
          placeholder="ej: MC001"
          style={{ flex: 1, minWidth: 0 }}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={agregar}
        />
        <button type="button" className="motored-btn motored-btn-secondary" onClick={agregar}>
          Agregar
        </button>
      </div>
    </div>
  );
}
