'use client';
/**
 * Commission tramos table: add, remove and reorder rows, with the rule
 * messages (first tramo at 0, strictly increasing, unique names) shown live.
 */
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { columnaStyle, controlStyle, filaStyle, touchStyle } from './styles';
import Mensajes from './Mensajes';
import { validarTramos } from './validaciones';

const VACIA = { nombre: '', desde_pct: '', tasa_pct: '' };

function Celda({ etiqueta, valor, ancho, modo, onChange }) {
  return (
    <input
      type="text" inputMode={modo} aria-label={etiqueta} value={valor}
      style={{ ...controlStyle, width: ancho }} onChange={(e) => onChange(e.target.value)}
    />
  );
}

function Boton({ icono: Icono, texto, onClick, desactivado = false }) {
  return (
    <button
      type="button" aria-label={texto} disabled={desactivado} className="motored-btn motored-btn-secondary"
      style={{ ...touchStyle, minWidth: '44px' }} onClick={onClick}
    >
      <Icono size={14} aria-hidden="true" />
    </button>
  );
}

function Fila({ fila, i, total, onCambiar, onMover, onQuitar }) {
  return (
    <div style={filaStyle}>
      <Celda etiqueta="Nombre del tramo" valor={fila.nombre} ancho="10rem" onChange={(v) => onCambiar({ nombre: v })} />
      <Celda etiqueta="Desde (%)" valor={fila.desde_pct} ancho="6rem" modo="decimal" onChange={(v) => onCambiar({ desde_pct: v })} />
      <Celda etiqueta="Tasa (%)" valor={fila.tasa_pct} ancho="6rem" modo="decimal" onChange={(v) => onCambiar({ tasa_pct: v })} />
      <Boton icono={ArrowUp} texto="Subir tramo" desactivado={i === 0} onClick={() => onMover(i, -1)} />
      <Boton icono={ArrowDown} texto="Bajar tramo" desactivado={i === total - 1} onClick={() => onMover(i, 1)} />
      <Boton icono={Trash2} texto="Quitar fila" onClick={onQuitar} />
    </div>
  );
}

export default function EditorTramos({ borrador, onChange }) {
  const cambiar = (i, parche) => onChange(borrador.map((f, j) => (j === i ? { ...f, ...parche } : f)));
  const mover = (i, paso) => {
    const copia = [...borrador];
    [copia[i], copia[i + paso]] = [copia[i + paso], copia[i]];
    onChange(copia);
  };
  return (
    <div style={columnaStyle}>
      {borrador.map((fila, i) => (
        <Fila
          // eslint-disable-next-line react/no-array-index-key
          key={i} fila={fila} i={i} total={borrador.length} onCambiar={(p) => cambiar(i, p)}
          onMover={mover} onQuitar={() => onChange(borrador.filter((_, j) => j !== i))}
        />
      ))}
      <div>
        <button type="button" className="motored-btn motored-btn-secondary" style={touchStyle} onClick={() => onChange([...borrador, VACIA])}>
          <Plus size={14} aria-hidden="true" />
          {' '}
          Agregar tramo
        </button>
      </div>
      <Mensajes mensajes={validarTramos(borrador)} />
    </div>
  );
}
