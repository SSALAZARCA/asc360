'use client';
/**
 * ERP inventory types discarded on a VENTAS load (ventas_tipos_excluidos):
 * one row per code with its match mode ("Empieza por" = prefijo, "Exacto")
 * and a remove button; below, "Agregar código". Codes are written in
 * capitals as they are typed. The rule messages are shown live.
 */
import { Plus, Trash2 } from 'lucide-react';
import Mensajes from './Mensajes';
import { columnaStyle, controlStyle, filaStyle, mutedStyle, optionStyle, touchStyle } from './styles';
import { ETIQUETA_MODO_TIPO, validarTiposExcluidos } from './validaciones';

const FILA_NUEVA = { codigo: '', modo: 'exacto' };

function Fila({ fila, numero, onCambiar, onQuitar }) {
  return (
    <li style={filaStyle}>
      <input
        type="text" aria-label={`Código ${numero}`} value={fila.codigo}
        style={{ ...controlStyle, width: '10rem', textTransform: 'uppercase' }}
        onChange={(e) => onCambiar({ codigo: e.target.value.toUpperCase() })}
      />
      <select
        aria-label={`Modo del código ${numero}`} value={fila.modo} style={{ ...controlStyle, width: '10rem' }}
        onChange={(e) => onCambiar({ modo: e.target.value })}
      >
        {Object.entries(ETIQUETA_MODO_TIPO).map(([modo, etiqueta]) => (
          <option key={modo} value={modo} style={optionStyle}>{etiqueta}</option>
        ))}
      </select>
      <button
        type="button" aria-label={`Quitar código ${numero}`} className="motored-btn motored-btn-secondary"
        style={{ ...touchStyle, minWidth: '44px' }} onClick={onQuitar}
      >
        <Trash2 size={14} aria-hidden="true" />
      </button>
    </li>
  );
}

export default function EditorTiposExcluidos({ borrador, onChange }) {
  const cambiar = (i, parche) => onChange(borrador.map((f, j) => (j === i ? { ...f, ...parche } : f)));
  return (
    <div style={columnaStyle}>
      {!borrador.length && <p style={mutedStyle}>Sin códigos: no se descarta ninguna fila por tipo.</p>}
      <ul style={{ ...columnaStyle, listStyle: 'none', margin: 0, padding: 0 }}>
        {borrador.map((fila, i) => (
          <Fila
            // eslint-disable-next-line react/no-array-index-key
            key={i} fila={fila} numero={i + 1} onCambiar={(p) => cambiar(i, p)}
            onQuitar={() => onChange(borrador.filter((_, j) => j !== i))}
          />
        ))}
      </ul>
      <div>
        <button
          type="button" className="motored-btn motored-btn-secondary" style={touchStyle}
          onClick={() => onChange([...borrador, { ...FILA_NUEVA }])}
        >
          <Plus size={14} aria-hidden="true" />
          {' Agregar código'}
        </button>
      </div>
      <Mensajes mensajes={validarTiposExcluidos(borrador)} />
    </div>
  );
}
