'use client';
/**
 * Cargo -> group map: one row per cargo with its name (always in capitals,
 * as the tablero compares them) and a select with the groups. The draft is
 * the same row list the generic map control uses.
 */
import { Plus, Trash2 } from 'lucide-react';
import { columnaStyle, controlStyle, filaStyle, optionStyle, touchStyle } from './styles';
import { etiquetaDe } from './etiquetas';

function Fila({ fila, opciones, onCambiar, onQuitar }) {
  return (
    <div style={filaStyle}>
      <input
        type="text" aria-label="Nombre del cargo" value={fila.clave} style={{ ...controlStyle, width: '18rem' }}
        onChange={(e) => onCambiar({ clave: e.target.value.toUpperCase() })}
      />
      <select aria-label="Grupo del cargo" value={fila.valor} style={controlStyle} onChange={(e) => onCambiar({ valor: e.target.value })}>
        {opciones.map((o) => <option key={o} value={o} style={optionStyle}>{etiquetaDe(o)}</option>)}
      </select>
      <button type="button" aria-label="Quitar cargo" className="motored-btn motored-btn-secondary" style={touchStyle} onClick={onQuitar}>
        <Trash2 size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

export default function EditorMapaCargos({ spec, borrador, onChange }) {
  const cambiar = (i, parche) => onChange(borrador.map((f, j) => (j === i ? { ...f, ...parche } : f)));
  const quitar = (i) => onChange(borrador.filter((_, j) => j !== i));
  const agregar = () => onChange([...borrador, { clave: '', valor: spec.opciones[spec.opciones.length - 1] }]);
  return (
    <div style={columnaStyle}>
      {borrador.map((fila, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <Fila key={i} fila={fila} opciones={spec.opciones} onCambiar={(p) => cambiar(i, p)} onQuitar={() => quitar(i)} />
      ))}
      <div>
        <button type="button" className="motored-btn motored-btn-secondary" style={touchStyle} onClick={agregar}>
          <Plus size={14} aria-hidden="true" />
          {' '}
          Agregar cargo
        </button>
      </div>
    </div>
  );
}
