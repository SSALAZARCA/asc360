'use client';
/**
 * Per-line bonuses of the asesores (comision_lineas): one row per line with
 * its sales-mix goal (%), the bonus in COP, an on/off switch and a remove
 * button; below, a select that adds a line not used yet. `spec.lineas` (the
 * configured lineas_comerciales, attached by the Comisiones tab) feeds the
 * select; without it the seven default lines are offered. TECNIRED is always
 * offered. The rule messages are shown live.
 */
import { Trash2 } from 'lucide-react';
import { etiquetaLinea } from './etiquetas';
import Mensajes from './Mensajes';
import { columnaStyle, controlStyle, filaStyle, mutedStyle, optionStyle, touchStyle } from './styles';
import { validarBonosLinea } from './validaciones';

export const LINEAS_POR_DEFECTO = ['REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS'];
export const TECNIRED = 'TECNIRED';

/** Goal and bonus a newly added line starts with (the backend defaults). */
const VALORES_POR_DEFECTO = {
  LUBRICANTES: { pct_meta: '21', bono: '35000' },
  CASCOS: { pct_meta: '6', bono: '30000' },
  ACCESORIOS: { pct_meta: '3', bono: '25000' },
  LLANTAS: { pct_meta: '1', bono: '25000' },
  BATERIAS: { pct_meta: '1', bono: '25000' },
  TECNIRED: { pct_meta: '6', bono: '25000' },
};

/** Every line a bonus can be set for: the configured ones (or the defaults) plus TECNIRED. */
export function lineasDisponibles(configuradas) {
  const base = configuradas && configuradas.length ? configuradas : LINEAS_POR_DEFECTO;
  return [...new Set([...base, TECNIRED])];
}

/** The lines the "Agregar línea" select offers: available and not used yet. */
export function opcionesParaAgregar(configuradas, filas) {
  const usadas = new Set(filas.map((f) => f.linea));
  return lineasDisponibles(configuradas).filter((l) => !usadas.has(l));
}

const filaNueva = (linea) => ({ linea, pct_meta: '', bono: '', ...VALORES_POR_DEFECTO[linea], activo: true });

function Campo({ etiqueta, valor, sufijo, ancho, modo, onChange }) {
  return (
    <span style={{ ...filaStyle, gap: '0.25rem', flexWrap: 'nowrap' }}>
      {sufijo === '$' && <span aria-hidden="true">$</span>}
      <input
        type="text" inputMode={modo} aria-label={etiqueta} value={valor}
        style={{ ...controlStyle, width: ancho }} onChange={(e) => onChange(e.target.value)}
      />
      {sufijo === '%' && <span aria-hidden="true">%</span>}
    </span>
  );
}

function Interruptor({ nombre, activo, onChange }) {
  return (
    <label style={{ ...filaStyle, ...touchStyle, gap: '0.25rem', cursor: 'pointer' }}>
      <input
        type="checkbox" aria-label={`Pagar bono de ${nombre}`} checked={activo}
        style={{ width: '24px', height: '24px', margin: '10px' }} onChange={(e) => onChange(e.target.checked)}
      />
      <span style={{ fontSize: '0.8rem' }}>{activo ? 'Activo' : 'Apagado'}</span>
    </label>
  );
}

function Fila({ fila, onCambiar, onQuitar }) {
  const nombre = etiquetaLinea(fila.linea);
  return (
    <li style={{ ...filaStyle, borderBottom: '1px solid var(--motored-border, #e4e4e7)', paddingBottom: '0.5rem' }}>
      <span style={{ minWidth: '9rem', fontWeight: 600, fontSize: '0.85rem' }}>{nombre}</span>
      <Campo
        etiqueta={`Meta de ${nombre} (%)`} valor={fila.pct_meta} sufijo="%" ancho="5rem" modo="decimal"
        onChange={(v) => onCambiar({ pct_meta: v })}
      />
      <Campo
        etiqueta={`Bono de ${nombre} (COP)`} valor={fila.bono} sufijo="$" ancho="8rem" modo="numeric"
        onChange={(v) => onCambiar({ bono: v })}
      />
      <Interruptor nombre={nombre} activo={fila.activo} onChange={(v) => onCambiar({ activo: v })} />
      <button
        type="button" aria-label={`Quitar ${nombre}`} className="motored-btn motored-btn-secondary"
        style={{ ...touchStyle, minWidth: '44px' }} onClick={onQuitar}
      >
        <Trash2 size={14} aria-hidden="true" />
      </button>
    </li>
  );
}

function AgregarLinea({ opciones, onAgregar }) {
  if (!opciones.length) return <p style={mutedStyle}>Todas las líneas ya tienen bono.</p>;
  return (
    <select aria-label="Agregar línea" value="" style={{ ...controlStyle, width: '16rem' }} onChange={(e) => onAgregar(e.target.value)}>
      <option value="" style={optionStyle}>Agregar línea...</option>
      {opciones.map((l) => <option key={l} value={l} style={optionStyle}>{etiquetaLinea(l)}</option>)}
    </select>
  );
}

export default function EditorBonosLinea({ spec, borrador, onChange }) {
  const cambiar = (i, parche) => onChange(borrador.map((f, j) => (j === i ? { ...f, ...parche } : f)));
  const agregar = (linea) => { if (linea) onChange([...borrador, filaNueva(linea)]); };
  return (
    <div style={columnaStyle}>
      {!borrador.length && <p style={mutedStyle}>Sin líneas: no se paga ningún bono por línea.</p>}
      <ul style={{ ...columnaStyle, listStyle: 'none', margin: 0, padding: 0 }}>
        {borrador.map((fila, i) => (
          <Fila
            key={`${fila.linea}-${i}`} fila={fila} onCambiar={(p) => cambiar(i, p)}
            onQuitar={() => onChange(borrador.filter((_, j) => j !== i))}
          />
        ))}
      </ul>
      <AgregarLinea opciones={opcionesParaAgregar(spec.lineas, borrador)} onAgregar={agregar} />
      <Mensajes mensajes={validarBonosLinea(borrador, lineasDisponibles(spec.lineas))} />
    </div>
  );
}
